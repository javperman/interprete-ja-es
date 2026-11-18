"""Pruebas de las piezas puras de la GUI (sin abrir ninguna ventana)."""

from __future__ import annotations

from types import SimpleNamespace

import httpx

from interprete.gui import devices, voices


# ------------------------------------------------------------------ devices
def _fake_run(payload: str, returncode: int = 0):
    def _run(*args, **kwargs):
        return SimpleNamespace(returncode=returncode, stdout=payload, stderr="")

    return _run


def test_devices_list_parses_names_and_descriptions(monkeypatch):
    payload = """[
      {"index":0,"description":"Altavoces","properties":{"node.name":"alsa_output.pci.x"}},
      {"index":1,"description":"meet_out Audio/Sink sink","properties":{"node.name":"meet_out"}}
    ]"""
    monkeypatch.setattr(devices.subprocess, "run", _fake_run(payload))
    found = devices.sinks(exclude=("meet_out",))
    assert [d.name for d in found] == ["alsa_output.pci.x"]
    assert found[0].label == "Altavoces"


def test_devices_list_survives_bad_json(monkeypatch):
    monkeypatch.setattr(devices.subprocess, "run", _fake_run("no json"))
    assert devices.sinks() == []


def test_devices_list_survives_missing_pactl(monkeypatch):
    def _boom(*args, **kwargs):
        raise OSError("no such file")

    monkeypatch.setattr(devices.subprocess, "run", _boom)
    assert devices.sources() == []


def test_microphones_excludes_monitors(monkeypatch):
    payload = """[
      {"index":0,"description":"Monitor of Altavoces","properties":{"node.name":"alsa_output.pci.x.monitor"}},
      {"index":1,"description":"Micrófono interno","properties":{"node.name":"alsa_input.pci.x"}},
      {"index":2,"description":"Monitor of meet_out Audio/Sink sink","properties":{"node.name":"meet_out"}},
      {"index":3,"description":"Micro_del_interprete","properties":{"node.name":"meet_mic"}}
    ]"""
    monkeypatch.setattr(devices.subprocess, "run", _fake_run(payload))
    names = [d.name for d in devices.microphones(exclude=("meet_mic",))]
    assert names == ["alsa_input.pci.x"]


# ------------------------------------------------------------------- voices
def test_voicevox_styles_are_flattened(monkeypatch):
    data = [
        {"name": "四国めたん", "styles": [{"name": "ノーマル", "id": 2}, {"name": "あまあま", "id": 0}]},
        {"name": "青山龍星", "styles": [{"name": "ノーマル", "id": 13}]},
    ]
    monkeypatch.setattr(httpx, "get", lambda *a, **k: SimpleNamespace(json=lambda: data))
    styles = voices.list_voicevox_styles("http://x")
    assert styles == [(0, "四国めたん (あまあま)"), (2, "四国めたん (ノーマル)"), (13, "青山龍星 (ノーマル)")]


def test_voicevox_styles_empty_when_service_down(monkeypatch):
    def _boom(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(httpx, "get", _boom)
    assert voices.list_voicevox_styles("http://x") == []


def test_piper_voices_lists_downloaded_models(tmp_path):
    good = tmp_path / "es_ES-davefx-medium"
    good.mkdir()
    (good / "es_ES-davefx-medium.onnx").write_bytes(b"x")
    (tmp_path / "vacia").mkdir()
    assert voices.list_piper_voices(str(tmp_path)) == ["es_ES-davefx-medium"]


def test_piper_voices_missing_dir():
    assert voices.list_piper_voices("/no/existe") == []
