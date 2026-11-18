"""Pruebas del motor de sesión (resolución de opciones y estado inicial)."""

from __future__ import annotations

import pytest

import interprete.audio as audio_pkg
from interprete.config import Config
from interprete.session import SessionOptions, make_state, resolve


@pytest.fixture
def devices(monkeypatch):
    monkeypatch.setattr(audio_pkg, "list_sink_names", lambda: ["meet_in", "meet_out", "hp"])
    monkeypatch.setattr(audio_pkg, "list_source_names", lambda: ["meet_mic", "mic"])
    monkeypatch.setattr(audio_pkg, "list_sink_names", lambda: ["meet_in", "meet_out", "hp"])
    monkeypatch.setattr(audio_pkg, "default_sink", lambda: "hp")
    monkeypatch.setattr(audio_pkg, "default_source", lambda: "mic")


def test_resolve_full_session(devices):
    res, errors = resolve(Config(), SessionOptions(mode="run"))
    assert errors == []
    assert res.sink_in == "meet_in"
    assert res.meet_out == "meet_out"
    assert res.mic == "mic"
    assert res.headphones == "hp"
    assert "meet_in" in res.listen_origin
    assert "mic" in res.speak_origin


def test_resolve_missing_sink(devices, monkeypatch):
    monkeypatch.setattr(audio_pkg, "list_sink_names", lambda: [])
    _, errors = resolve(Config(), SessionOptions(mode="listen"))
    assert any("no existe" in e for e in errors)


def test_resolve_rejects_virtual_mic(devices, monkeypatch):
    monkeypatch.setattr(audio_pkg, "default_source", lambda: "meet_mic")
    _, errors = resolve(Config(), SessionOptions(mode="speak"))
    assert any("micro virtual" in e for e in errors)


def test_resolve_replay_skips_device_checks(monkeypatch, tmp_path):
    # sin dispositivos disponibles: el replay no debe necesitarlos
    monkeypatch.setattr(audio_pkg, "list_sink_names", lambda: [])
    monkeypatch.setattr(audio_pkg, "list_source_names", lambda: [])
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    res, errors = resolve(Config(), SessionOptions(mode="listen", input_wav=str(wav)))
    assert errors == []
    assert "replay" in res.listen_origin


def test_resolve_missing_replay_file(devices):
    _, errors = resolve(Config(), SessionOptions(mode="listen", input_wav="/nope/x.wav"))
    assert any("no existe el fichero" in e for e in errors)


def test_make_state_run_mode(devices):
    cfg = Config()
    options = SessionOptions(mode="run", es_forward=True, ja_forward=True)
    res, _ = resolve(cfg, options)
    state = make_state(cfg, options, res)
    assert [c.key for c in state.channels] == ["listen", "speak"]
    assert state.flags["ja_forward"] is True
    assert state.flags["es_forward"] is True
    assert state.flags["speak_es"] is True
    assert state.channels[0].tts_on is True


def test_make_state_listen_only(devices):
    options = SessionOptions(mode="listen", speak_es=False)
    res, _ = resolve(Config(), options)
    state = make_state(Config(), options, res)
    assert [c.key for c in state.channels] == ["listen"]
    assert state.flags["speak_es"] is False
    assert state.channels[0].tts_on is False


def test_make_state_privacy_note():
    state = make_state(Config(), SessionOptions(mode="listen"), resolve(Config(), SessionOptions(mode="listen"))[0])
    assert "sale a" in state.privacy
