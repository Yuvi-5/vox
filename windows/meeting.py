"""Vox Notetaker: records your mic ("You") and the PC's audio ("Others") during a meeting,
transcribes both in chunks with Groq, and writes notes with a summary and action items.

No bot joins the call. Mic and system audio are transcribed separately, which gives a free
two-way speaker split (you vs everyone else).
"""
import json
import logging
import os
import queue
import re
import threading
import time
from datetime import datetime

import numpy as np
import requests

import vox_core as core

log = logging.getLogger("vox.meeting")

SR = 16000
CHUNK_SECONDS = 30          # audio sent to Groq per request, per source
SILENCE_RMS = 0.004         # chunks quieter than this are skipped (saves quota, avoids Whisper hallucinations)
DEFAULT_NOTES_MODEL = "openai/gpt-oss-120b"


def meetings_dir():
    d = os.path.join(core.data_dir(), "meetings")
    os.makedirs(d, exist_ok=True)
    return d


def notes_export_dir(cfg):
    d = cfg.get("notes_folder") or os.path.join(os.path.expanduser("~"), "Documents", "Vox Notes")
    os.makedirs(d, exist_ok=True)
    return d


def _llm(cfg, system, user, max_tokens=4096):
    model = cfg.get("notes_model") or DEFAULT_NOTES_MODEL
    body = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if "gpt-oss" in model:
        body["reasoning_effort"] = "medium"
        body["include_reasoning"] = False
    r = requests.post(f"{core.BASE}/chat/completions", headers={"Authorization": f"Bearer {cfg['api_key']}"},
                      json=body, timeout=180)
    return core.sanitize(core._check(r)["choices"][0]["message"].get("content", ""))


NOTES_PROMPT = """You write meeting notes from a transcript. Each line is "[mm:ss] Speaker: text". {me} is the note taker (always correct). Other speaker names were inferred from context and may be marked "(likely)"; "Others" means unidentified.
{context}
Write Markdown with exactly these sections:

# <short specific title, max 8 words>

## Summary
3 to 6 sentences on what the meeting covered and concluded.

## Key points
Bullets grouped by topic. Keep names, numbers, dates and technical terms exactly.

## Decisions
Bullets. Write "None recorded" if there were none.

## Action items
Checkbox bullets: "- [ ] Owner: task (due date if mentioned)". Use {me} for the note taker. Write "None recorded" if there were none.

## Open questions
Bullets of questions raised and not answered. Write "None" if there were none.

## Who said what
One bullet per speaker: "**Name**: their main points, proposals and commitments in 1 to 3 sentences". Keep "(likely)" for inferred names. Skip speakers with nothing substantive.

Rules: use only what is in the transcript, do not invent facts, owners or dates. No preamble. Plain, direct wording.
Spell these names and terms exactly: {terms}."""

ATTRIBUTE_PROMPT = """You label speakers in a meeting transcript. Lines tagged "You" are the note taker ({me}) and are always correct. Lines tagged "Others" come from the other participants through the computer's audio, possibly several different people.
{context}
For every line numbered in OTHERS, decide who most likely said it, using: people addressing each other by name ("thanks, Sara"), introductions, replies to a question aimed at someone, the attendee list, and topic continuity. Use a name from the attendee list when you can. If you cannot tell, use "Unknown".

Return only JSON: {{"speakers": {{"<line number>": "<name or Unknown>", ...}}}} with one entry for every OTHERS line number."""

CATCHUP_PROMPT = """The user stepped away from a live meeting. From the transcript excerpt, tell them what they missed in 3 to 6 short bullets: topics discussed, anything decided, anything asked of them ("You"). Then one line: "Now discussing: ...". Use only the transcript. No preamble."""


class _Source(threading.Thread):
    """Records one audio source into 16 kHz mono float32 chunks of CHUNK_SECONDS."""

    def __init__(self, name, make_recorder, out_queue, meeting):
        super().__init__(daemon=True, name=f"rec-{name}")
        self.name_ = name
        self.make_recorder = make_recorder
        self.out = out_queue
        self.meeting = meeting
        self.error = None

    def run(self):
        try:
            with self.make_recorder() as rec:
                buf, start = [], self.meeting.elapsed()
                n = 0
                while self.meeting.active:
                    data = rec.record(numframes=SR // 5)[:, 0]   # 200 ms
                    buf.append(data.copy())
                    n += len(data)
                    if n >= SR * CHUNK_SECONDS:
                        self.out.put((self.name_, start, np.concatenate(buf)))
                        buf, n, start = [], 0, self.meeting.elapsed()
                if buf:
                    self.out.put((self.name_, start, np.concatenate(buf)))
        except Exception as e:
            self.error = str(e)
            log.exception("%s recorder failed", self.name_)


class Meeting:
    def __init__(self, get_cfg):
        self.get_cfg = get_cfg
        self.active = False
        self.processing = False
        self.id = None
        self.started = 0.0
        self.entries = []          # {"t": seconds, "who": "You"|"Others", "text": str}
        self.q = queue.Queue()
        self.sources = []
        self.worker = None
        self.last_error = ""
        self.event = None          # calendar event dict or None
        self.lock = threading.Lock()

    # ------------------------------------------------------------ status
    def elapsed(self):
        return time.time() - self.started if self.started else 0.0

    def status(self):
        with self.lock:
            return {
                "active": self.active, "processing": self.processing, "id": self.id,
                "title": (self.event or {}).get("title", ""), "attendees": (self.event or {}).get("attendees", []),
                "elapsed": round(self.elapsed()), "entries": list(self.entries), "error": self.last_error,
                "sources": {s.name_: (s.error or "ok") for s in self.sources},
            }

    # ------------------------------------------------------------- control
    def start(self, event=None):
        if self.active or self.processing:
            return False
        import soundcard as sc
        cfg = self.get_cfg()
        if not cfg.get("api_key"):
            self.last_error = "Add your Groq API key first"
            return False
        self.id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.started = time.time()
        self.entries = []
        self.last_error = ""
        self.event = event
        self.q = queue.Queue()
        self.active = True

        def mic():
            return sc.default_microphone().recorder(samplerate=SR, channels=1)

        def system():
            spk = sc.default_speaker()
            return sc.get_microphone(id=str(spk.name), include_loopback=True).recorder(samplerate=SR, channels=1)

        self.sources = [_Source("You", mic, self.q, self), _Source("Others", system, self.q, self)]
        for s in self.sources:
            s.start()
        self.worker = threading.Thread(target=self._transcribe_loop, daemon=True, name="meeting-stt")
        self.worker.start()
        log.info("meeting %s started (%s)", self.id, (event or {}).get("title", "no calendar event"))
        return True

    def stop(self):
        """Stops recording, finishes transcription, writes notes. Runs the slow part in a thread."""
        if not self.active:
            return False
        self.active = False
        self.processing = True
        threading.Thread(target=self._finish, daemon=True, name="meeting-finish").start()
        return True

    # ------------------------------------------------------- transcription
    def _transcribe_loop(self):
        while self.active or not self.q.empty() or any(s.is_alive() for s in self.sources):
            try:
                who, start, audio = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            rms = float(np.sqrt(np.mean(np.square(audio)))) if len(audio) else 0.0
            if rms < SILENCE_RMS or len(audio) < SR:
                continue
            pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
            segs = []
            names = ", ".join((self.event or {}).get("attendees", [])[:20])
            for attempt in range(3):
                try:
                    segs = core.transcribe_segments(self.get_cfg(), core.pcm_to_wav(pcm), names)
                    break
                except core.GroqError as e:
                    self.last_error = str(e)
                    log.warning("stt failed (%s), retry %s", e, attempt)
                    time.sleep(5 * (attempt + 1))
                except requests.RequestException as e:
                    self.last_error = f"Network: {e}"
                    time.sleep(3)
            new = [{"t": round(start + a), "who": who, "text": t} for a, _b, t in segs
                   if not core.is_silence_hallucination(t)]
            if new:
                with self.lock:
                    self.entries.extend(new)
                    self.entries.sort(key=lambda e: e["t"])
                self._save_transcript()

    def _me(self):
        return (self.get_cfg().get("your_name") or "").strip() or "You"

    def _label(self, e):
        if e["who"] == "You":
            return self._me()
        name = e.get("name")
        return f"{name} (likely)" if name and name != "Unknown" else "Others"

    def transcript_text(self, since=0, named=True):
        lines = []
        for e in self.entries:
            if e["t"] >= since:
                who = self._label(e) if named else e["who"]
                lines.append(f"[{e['t'] // 60:02d}:{e['t'] % 60:02d}] {who}: {e['text']}")
        return "\n".join(lines)

    def _context(self):
        ev = self.event or {}
        parts = []
        if ev.get("title"):
            parts.append(f"Meeting: {ev['title']}.")
        if ev.get("attendees"):
            parts.append("Attendees (other than the note taker): " + ", ".join(ev["attendees"]) + ".")
        if ev.get("organizer"):
            parts.append(f"Organizer: {ev['organizer']}.")
        return ("\n" + " ".join(parts) + "\n") if parts else ""

    def attribute_speakers(self):
        """Second pass: guess a name for every 'Others' line. Works in windows so long meetings fit."""
        cfg = self.get_cfg()
        idx = [i for i, e in enumerate(self.entries) if e["who"] == "Others"]
        if not idx:
            return
        win = 220
        for w0 in range(0, len(self.entries), win):
            lo, hi = max(0, w0 - 30), min(len(self.entries), w0 + win)
            lines, others = [], []
            for i in range(lo, hi):
                e = self.entries[i]
                lines.append(f"{i}. {e['who']}: {e['text']}")
                if e["who"] == "Others" and w0 <= i < hi:
                    others.append(str(i))
            if not others:
                continue
            user = "TRANSCRIPT\n" + "\n".join(lines) + "\n\nOTHERS: " + ", ".join(others)
            try:
                raw = _llm(cfg, ATTRIBUTE_PROMPT.format(me=self._me(), context=self._context()), user, max_tokens=4000)
                m = re.search(r"\{.*\}", raw, re.S)
                data = json.loads(m.group(0)) if m else {}
                for k, v in (data.get("speakers") or {}).items():
                    i = int(k)
                    if 0 <= i < len(self.entries) and self.entries[i]["who"] == "Others":
                        self.entries[i]["name"] = str(v).strip()[:60] or "Unknown"
            except Exception:
                log.exception("speaker attribution failed for window %s", w0)

    def catch_up(self, minutes=10):
        text = self.transcript_text(since=max(0, self.elapsed() - minutes * 60))
        if not text:
            return "Nothing transcribed yet in that window."
        return _llm(self.get_cfg(), CATCHUP_PROMPT + self._context(), text, max_tokens=1200)

    # --------------------------------------------------------------- saving
    def _folder(self):
        d = os.path.join(meetings_dir(), self.id)
        os.makedirs(d, exist_ok=True)
        return d

    def _save_transcript(self):
        with open(os.path.join(self._folder(), "transcript.json"), "w", encoding="utf-8") as f:
            json.dump({"id": self.id, "started": self.started, "entries": self.entries}, f, ensure_ascii=False)

    def _finish(self):
        try:
            for s in self.sources:
                s.join(timeout=5)
            if self.worker:
                self.worker.join(timeout=240)
            duration = round(self.elapsed())
            self._save_transcript()
            cfg = self.get_cfg()
            if self.entries:
                self.attribute_speakers()
                self._save_transcript()
            transcript = self.transcript_text()
            if transcript:
                terms = ", ".join(((self.event or {}).get("attendees", []) + core.dictionary_terms(cfg))[:150]) or "none"
                try:
                    notes = _llm(cfg, NOTES_PROMPT.format(terms=terms, me=self._me(), context=self._context()), transcript)
                except Exception as e:
                    log.exception("notes failed")
                    notes = f"# Meeting {self.id}\n\nNotes could not be generated ({e}). The transcript is below."
            else:
                notes = f"# Meeting {self.id}\n\nNo speech was captured."
            m = re.search(r"^#\s+(.+)$", notes, re.M)
            title = (self.event or {}).get("title") or (m.group(1).strip() if m else f"Meeting {self.id}")
            if m and (self.event or {}).get("title"):
                notes = notes.replace(m.group(0), f"# {title}", 1)
                m = re.search(r"^#\s+(.+)$", notes, re.M)
            when = datetime.fromtimestamp(self.started)
            who = ", ".join([self._me()] + (self.event or {}).get("attendees", []))
            header = f"*{when:%A %d %B %Y, %H:%M} · {duration // 60} min · {who}*\n\n"
            body = notes.replace(m.group(0), m.group(0) + "\n\n" + header, 1) if m else header + notes
            body = re.sub(r"\n{3,}", "\n\n", body)
            full = body.rstrip() + "\n\n## Transcript\n\n" + (transcript or "_empty_") + "\n"
            with open(os.path.join(self._folder(), "notes.md"), "w", encoding="utf-8") as f:
                f.write(full)
            meta = {"id": self.id, "title": title, "started": self.started, "duration": duration,
                    "words": sum(len(e["text"].split()) for e in self.entries),
                    "attendees": (self.event or {}).get("attendees", [])}
            with open(os.path.join(self._folder(), "meta.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f)
            safe = re.sub(r'[<>:"/\\|?*]+', "", title)[:60].strip() or "Meeting"
            export = os.path.join(notes_export_dir(cfg), f"{when:%Y-%m-%d %H%M} {safe}.md")
            with open(export, "w", encoding="utf-8") as f:
                f.write(full)
            meta["export"] = export
            with open(os.path.join(self._folder(), "meta.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f)
            log.info("meeting %s saved to %s", self.id, export)
        except Exception:
            log.exception("finishing meeting failed")
        finally:
            self.processing = False
            self.started = 0.0


def list_meetings():
    out = []
    for d in sorted(os.listdir(meetings_dir()), reverse=True):
        p = os.path.join(meetings_dir(), d, "meta.json")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    out.append(json.load(f))
            except ValueError:
                pass
    return out


def read_notes(mid):
    p = os.path.join(meetings_dir(), os.path.basename(mid), "notes.md")
    with open(p, encoding="utf-8") as f:
        return f.read()


def delete_meeting(mid):
    import shutil
    shutil.rmtree(os.path.join(meetings_dir(), os.path.basename(mid)), ignore_errors=True)


# ------------------------------------------------------------ meeting page data

def _folder_of(mid):
    return os.path.join(meetings_dir(), os.path.basename(mid))


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def detail(mid, cfg):
    """Everything the meeting page needs: meta, summary (without transcript), speaker-labelled lines, your notes."""
    d = _folder_of(mid)
    meta = _read_json(os.path.join(d, "meta.json"), {})
    notes = read_notes(mid)
    summary = notes.split("\n## Transcript", 1)[0].strip()
    # drop the title and the italic header line; the page shows them separately
    summary = re.sub(r"^#\s+.*\n+", "", summary, count=1)
    summary = re.sub(r"^\*[^\n]*\*\s*\n+", "", summary, count=1)
    tr = _read_json(os.path.join(d, "transcript.json"), {"entries": []})
    me = (cfg.get("your_name") or "").strip() or "You"
    lines = []
    for e in tr.get("entries", []):
        if e["who"] == "You":
            who, likely = me, False
        elif e.get("name") and e["name"] != "Unknown":
            who, likely = e["name"], True
        else:
            who, likely = "Others", False
        lines.append({"t": e["t"], "who": who, "me": e["who"] == "You", "likely": likely, "text": e["text"]})
    user = ""
    p = os.path.join(d, "my_notes.md")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            user = f.read()
    return {"meta": meta, "summary": summary, "lines": lines, "my_notes": user,
            "done": meta.get("done", []), "me": me}


def save_my_notes(mid, text):
    with open(os.path.join(_folder_of(mid), "my_notes.md"), "w", encoding="utf-8") as f:
        f.write(text)


def set_done(mid, index, done):
    p = os.path.join(_folder_of(mid), "meta.json")
    meta = _read_json(p, {})
    s = set(meta.get("done", []))
    (s.add if done else s.discard)(int(index))
    meta["done"] = sorted(s)
    _write_json(p, meta)


def rename(mid, title):
    p = os.path.join(_folder_of(mid), "meta.json")
    meta = _read_json(p, {})
    meta["title"] = title.strip()[:120] or meta.get("title", "")
    _write_json(p, meta)
    return meta["title"]


ASK_PROMPT = """You answer questions about the user's past meetings using only the meeting records below.
Each record starts with [M<n>] and the meeting title and date. Transcript lines look like "[mm:ss] Speaker: text".
Answer in a few sentences or bullets. After every fact, cite its source as [M<n> mm:ss] (or [M<n>] when it comes from the summary).
If the records do not contain the answer, say so plainly. No preamble."""


def _score(text, words):
    t = text.lower()
    return sum(t.count(w) for w in words)


def ask(cfg, question):
    """Search every meeting, send the most relevant ones to the notes model, return answer + sources."""
    words = [w for w in re.findall(r"[a-z0-9]{3,}", question.lower())
             if w not in {"the", "and", "did", "what", "who", "was", "were", "about", "with", "when", "that", "this", "have", "said", "say", "does"}]
    scored = []
    for m in list_meetings():
        try:
            text = read_notes(m["id"])
        except OSError:
            continue
        s = _score(m.get("title", ""), words) * 5 + _score(text, words)
        scored.append((s, m["started"], m, text))
    if not scored:
        return {"answer": "No meetings recorded yet.", "sources": []}
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    picked = [x for x in scored if x[0] > 0][:4] or scored[:2]   # nothing matched: use the latest two
    parts, sources = [], []
    for i, (_s, started, m, text) in enumerate(picked, 1):
        when = datetime.fromtimestamp(started).strftime("%a %d %b %Y %H:%M")
        parts.append(f"[M{i}] {m.get('title', '')} ({when})\n{text[:24000]}")
        sources.append({"ref": f"M{i}", "id": m["id"], "title": m.get("title", ""), "started": started})
    answer = _llm(cfg, ASK_PROMPT, "\n\n".join(parts) + f"\n\nQUESTION: {question}", max_tokens=1500)
    return {"answer": answer, "sources": sources}
