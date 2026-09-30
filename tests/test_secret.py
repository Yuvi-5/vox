import json
import sys

import pytest

import secret
import vox_core as core


def fake_backend():
    """Reversible stand-in for DPAPI so the config logic is testable on any OS."""
    return (lambda b: b[::-1], lambda b: b[::-1])


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(secret, "_backend", fake_backend())
    return tmp_path / "Vox"


def on_disk(appdata):
    return json.loads((appdata / "config.json").read_text(encoding="utf-8"))


def test_protect_round_trip_and_marker(monkeypatch):
    monkeypatch.setattr(secret, "_backend", fake_backend())
    p = secret.protect("gsk_abc")
    assert p.startswith("dpapi:") and "gsk_abc" not in p
    assert secret.unprotect(p) == "gsk_abc"


def test_protect_leaves_empty_and_already_protected_alone(monkeypatch):
    monkeypatch.setattr(secret, "_backend", fake_backend())
    assert secret.protect("") == ""
    p = secret.protect("k")
    assert secret.protect(p) == p


def test_plain_values_pass_through_unprotect():
    assert secret.unprotect("plain") == "plain"
    assert secret.unprotect("") == ""


def test_unreadable_protected_value_becomes_empty(monkeypatch):
    monkeypatch.setattr(secret, "_backend", (lambda b: b, lambda b: (_ for _ in ()).throw(OSError("other user"))))
    assert secret.unprotect("dpapi:AAAA") == ""


def test_without_a_backend_nothing_is_encrypted_or_opened(monkeypatch):
    monkeypatch.setattr(secret, "_backend", None)
    assert secret.protect("k") == "k"
    assert secret.unprotect("dpapi:AAAA") == ""
    assert not secret.available()


def test_save_config_stores_key_protected_and_load_config_returns_it_plain(appdata):
    core.save_config(dict(core.DEFAULT_CONFIG, api_key="gsk_secret"))
    stored = on_disk(appdata)["api_key"]
    assert stored.startswith("dpapi:") and "gsk_secret" not in stored
    assert core.load_config()["api_key"] == "gsk_secret"


def test_key_typed_by_hand_is_protected_on_first_load(appdata):
    appdata.mkdir(parents=True)
    (appdata / "config.json").write_text('{"api_key": "gsk_typed"}', encoding="utf-8")
    assert core.load_config()["api_key"] == "gsk_typed"
    assert on_disk(appdata)["api_key"].startswith("dpapi:")
    assert core.load_config()["api_key"] == "gsk_typed"


def test_empty_key_stays_empty_on_disk(appdata):
    core.save_config(dict(core.DEFAULT_CONFIG, api_key=""))
    assert on_disk(appdata)["api_key"] == ""


def test_other_settings_survive_the_round_trip(appdata):
    core.save_config(dict(core.DEFAULT_CONFIG, api_key="k", language="ur", keep_history=False))
    cfg = core.load_config()
    assert cfg["language"] == "ur" and cfg["keep_history"] is False


@pytest.mark.skipif(sys.platform != "win32", reason="real DPAPI exists only on Windows")
def test_real_dpapi_round_trip():
    p = secret.protect("gsk_real_test_value")
    assert p.startswith("dpapi:") and "gsk_real" not in p
    assert secret.unprotect(p) == "gsk_real_test_value"
