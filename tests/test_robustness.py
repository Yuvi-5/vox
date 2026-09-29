import array
import struct

import pytest
import requests

import vox_core as core


class Resp:
    def __init__(self, status):
        self.status_code = status


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(core.time, "sleep", lambda s: None)


def script_posts(monkeypatch, outcomes):
    """Each call to requests.post returns (or raises) the next outcome."""
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        o = outcomes[min(len(calls), len(outcomes)) - 1]
        if isinstance(o, Exception):
            raise o
        return Resp(o)

    monkeypatch.setattr(core.requests, "post", fake_post)
    return calls


# ------------------------------------------------------------- post_with_retry

def test_retries_a_temporary_server_error_then_succeeds(monkeypatch):
    calls = script_posts(monkeypatch, [503, 502, 200])
    assert core.post_with_retry("http://x/v1").status_code == 200
    assert len(calls) == 3


def test_gives_up_after_the_retries_and_returns_the_last_response(monkeypatch):
    calls = script_posts(monkeypatch, [500, 500, 500, 200])
    assert core.post_with_retry("http://x/v1").status_code == 500
    assert len(calls) == 3


@pytest.mark.parametrize("status", [200, 400, 401, 404, 429])
def test_other_statuses_are_returned_at_once(monkeypatch, status):
    calls = script_posts(monkeypatch, [status, 200])
    assert core.post_with_retry("http://x/v1").status_code == status
    assert len(calls) == 1


def test_retries_a_dropped_connection(monkeypatch):
    calls = script_posts(monkeypatch, [requests.ConnectionError("reset"), 200])
    assert core.post_with_retry("http://x/v1").status_code == 200
    assert len(calls) == 2


def test_connection_error_is_raised_when_it_keeps_failing(monkeypatch):
    script_posts(monkeypatch, [requests.Timeout("slow")])
    with pytest.raises(requests.Timeout):
        core.post_with_retry("http://x/v1")


def test_uploaded_file_is_rewound_before_each_attempt(monkeypatch):
    import io
    buf = io.BytesIO(b"audio")
    positions = []

    def fake_post(url, **kw):
        positions.append(kw["files"]["file"][1].tell())
        kw["files"]["file"][1].read()
        return Resp(503 if len(positions) < 2 else 200)

    monkeypatch.setattr(core.requests, "post", fake_post)
    core.post_with_retry("http://x/v1", files={"file": ("a.wav", buf, "audio/wav")})
    assert positions == [0, 0]


# ------------------------------------------------------------------ is_silent

def pcm(samples):
    return struct.pack("<%dh" % len(samples), *samples)


def test_empty_audio_is_silent():
    assert core.is_silent(b"")
    assert core.is_silent(b"\x01")   # less than one sample


def test_digital_silence_and_low_noise_are_silent():
    assert core.is_silent(pcm([0] * 16000))
    assert core.is_silent(pcm([200, -300, 150, -250] * 4000))


def test_speech_level_audio_is_not_silent():
    assert not core.is_silent(pcm([0] * 8000 + [4000, -6000, 3000] + [0] * 8000))


def test_negative_peak_counts_too():
    assert not core.is_silent(pcm([0, -20000, 0]))
    assert not core.is_silent(pcm([0, -32768, 0]))


def test_threshold_is_the_loudest_sample():
    just_under = core.SILENCE_PEAK - 1
    assert core.is_silent(pcm([just_under, -just_under]))
    assert not core.is_silent(pcm([core.SILENCE_PEAK]))
    assert core.is_silent(pcm([100]), threshold=101) and not core.is_silent(pcm([101]), threshold=101)


def test_odd_trailing_byte_is_ignored():
    assert core.is_silent(pcm([10, 20]) + b"\xff")


def test_uses_array_of_shorts():
    assert array.array("h").itemsize == 2   # the silence gate assumes 16-bit samples
