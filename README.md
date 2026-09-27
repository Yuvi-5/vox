# Vox

Free voice dictation and meeting notes for Windows. Speak in any app and cleaned-up text appears where your cursor is. Uses Groq's free API with your own key.

## Download

1. Go to **Releases** and download `VoxSetup.exe`.
2. Run it. Windows SmartScreen may warn because the installer is not code-signed: click *More info* > *Run anyway*. No admin rights needed.
3. Vox opens and asks for **your own free Groq key**: sign in at https://console.groq.com, open **API Keys**, create a key, paste it into Vox.

Every person uses their own key, so everyone gets their own free limits. No key is included in this repo or the installer.

## Windows

| Action | How |
|---|---|
| Dictate | Hold **Ctrl + Win**, speak, release |
| Hands-free | **Double-tap Ctrl + Win**, speak, press it once more to finish (Esc cancels) |
| Open Vox | Double-click the tray icon, or Vox in the Start menu |
| Meeting notes | Vox > Notes > Start notes, or tray icon > Start meeting notes |

The shortcut can be changed in Settings (Right Ctrl, Right Alt, Ctrl + Alt, Ctrl + Shift).

### What the app has

- **Home:** words this week, total words, words per minute, time saved, searchable history.
- **Notes:** meeting notetaker. Records your mic and the PC's audio (no bot joins the call). Produces a transcript, summary, key points, decisions, action items, open questions and who said what. Notes are saved as Markdown in `Documents\Vox Notes`.
- **Dictionary:** your own words, people's names and forced replacements (`lume x r` → `LoomXR`). Used as spelling hints for dictation and meeting notes.
- **Styles:** tone per app (formal in Outlook, casual in WhatsApp, raw in code editors).
- **Settings:** Groq key with a test button, shortcut, language, AI cleanup, your name, start with Windows.

### Calendar

Vox > Notes > Calendar:

- **Connect Google Calendar:** sign in with Gmail or a school/work Google account. Read-only access to events. Google may show "Google hasn't verified this app": click *Advanced* > *Go to Vox*. Some school or work accounts block unverified apps; then use one of the options below.
- **iCal link:** Outlook (Settings > Calendar > Shared calendars > Publish > ICS link) or Google accounts that show a *Secret address in iCal format*. Never use a public address.
- **No calendar:** when you start notes, type the meeting title and who is in it.

Vox titles notes with the meeting name, uses attendee names to label speakers, and reminds you (or starts notes automatically) when a meeting with other people begins.

### Who said what

Your mic is recorded separately, so your lines are always labelled correctly. Other speakers come through the PC audio as one stream; Vox names them from context (people addressing each other, introductions, the attendee list) and marks those names "(likely)". Unclear lines stay "Others".

## Free limits (Groq free plan)

| | Limit |
|---|---|
| Speech-to-text | 2,000 requests/day, 8 hours of audio/day |
| Cleanup (gpt-oss-20b) | 1,000 requests/day |
| Meeting notes (gpt-oss-120b) | 1,000 requests/day, 200K tokens/day |

A meeting uses about 2 hours of audio quota per real hour (mic and PC audio are transcribed separately; silent stretches are skipped).

## Privacy

- Audio and text go to Groq under your own key. Nothing else leaves the device.
- Settings, history and meetings are stored in `%APPDATA%\Vox` on Windows.
- Tell people when you record a meeting. Recording laws differ by place.

## Building

- **Release:** push a tag (`git tag v1.0.0 && git push origin v1.0.0`). GitHub Actions builds `VoxSetup.exe` and attaches it to a Release.
- **Locally:** run `windows\build_app.bat` (needs Python 3.10+). It builds and installs to `%LOCALAPPDATA%\Programs\Vox`.

### Google sign-in for release builds (maintainer only)

1. In Google Cloud, create a project, enable the **Google Calendar API**, set up the OAuth consent screen (External, published), and create an OAuth client of type **Desktop app**.
2. Download its JSON. For local builds, save it as `windows/google_client.json` (ignored by git).
3. For GitHub releases, add a repository secret named `GOOGLE_CLIENT_JSON` with the file's contents. Without it, releases build without the Google button.

Your key, calendar link, history and meetings live in `%APPDATA%\Vox` on each PC, never in the repo. `windows/config.json` (a local copy with a key) is excluded by `.gitignore`. Never commit it.
