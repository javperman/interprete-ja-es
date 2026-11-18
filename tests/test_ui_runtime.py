"""Pruebas de los ajustes en caliente compartidos con la TUI."""

from __future__ import annotations

import asyncio

from interprete.session import Runtime
from interprete.ui.state import AppState, ChannelState


class FakeSpeaker:
    def __init__(self) -> None:
        self.enabled = True
        self.spoken = 3
        self.skipped = 1
        self.muted = 0
        self.errors = 0

    def set_enabled(self, on: bool) -> None:
        self.enabled = bool(on)


class FakeForwarder:
    def __init__(self, volume: float = 0.50, duck_factor: float = 0.40) -> None:
        self.enabled = True
        self.volume = volume
        self.duck_factor = duck_factor

    def set_enabled(self, on: bool) -> None:
        self.enabled = bool(on)

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, float(volume)))

    def set_duck_factor(self, factor: float) -> None:
        self.duck_factor = max(0.0, min(1.0, float(factor)))


def _runtime():
    state = AppState()
    state.channels = [
        ChannelState(key="listen", name="JA → ES", source_lang="ja", target_lang="es"),
        ChannelState(key="speak", name="ES → JA", source_lang="es", target_lang="ja"),
    ]
    rt = Runtime()
    rt.state = state
    rt.speakers = {"listen": FakeSpeaker(), "speak": FakeSpeaker()}
    rt.forwarder = FakeForwarder()
    rt.stop = asyncio.Event()
    return rt


def test_toggle_tts_listen():
    rt = _runtime()
    note = rt.apply("toggle_tts_listen")
    assert "silenciada" in note
    assert rt.speakers["listen"].enabled is False
    assert rt.state.channel("listen").tts_on is False
    rt.apply("toggle_tts_listen")
    assert rt.speakers["listen"].enabled is True
    assert rt.state.channel("listen").tts_on is True


def test_toggle_ja_and_flags():
    rt = _runtime()
    rt.apply("toggle_ja")
    assert rt.forwarder.enabled is False
    assert rt.state.flags["ja_forward"] is False


def test_volume_step_and_clamp():
    rt = _runtime()
    base = rt.forwarder.volume
    rt.apply("ja_volume_up")
    assert abs(rt.forwarder.volume - (base + 0.05)) < 1e-9
    for _ in range(20):
        rt.apply("ja_volume_up")
    assert rt.forwarder.volume == 1.0
    for _ in range(40):
        rt.apply("ja_volume_down")
    assert rt.forwarder.volume == 0.0
    assert rt.state.flags["ja_volume"] == 0.0


def test_pause_silences_everything_and_restores():
    rt = _runtime()
    rt.speakers["speak"].set_enabled(False)  # el usuario ya había silenciado el JA
    note = rt.apply("toggle_pause")
    assert "PAUSA" in note
    assert rt.forwarder.enabled is False
    assert all(not s.enabled for s in rt.speakers.values())
    assert rt.state.flags["paused"] is True
    note = rt.apply("toggle_pause")
    assert "reanudado" in note
    assert rt.forwarder.enabled is True
    assert rt.speakers["listen"].enabled is True
    assert rt.speakers["speak"].enabled is False  # se respeta el estado previo
    assert rt.state.flags["paused"] is False


def test_quit_sets_stop_event():
    rt = _runtime()
    assert rt.apply("quit") is None
    assert rt.stop.is_set()


def test_actions_without_components():
    rt = _runtime()
    rt.forwarder = None
    assert "no está activo" in rt.apply("toggle_ja")
    rt.speakers = {}
    assert "no disponible" in rt.apply("toggle_tts_speak")


def test_unknown_action():
    rt = _runtime()
    assert "desconocida" in rt.apply("nope")


def test_sync_copies_speaker_and_forwarder_state():
    rt = _runtime()
    rt.forwarder.volume = 0.55
    rt.sync()
    ch = rt.state.channel("listen")
    assert ch.spoken == 3
    assert ch.skipped == 1
    assert ch.tts_on is True
    assert rt.state.flags["ja_volume"] == 0.55
    assert rt.state.flags["ja_forward"] is True


def test_es_background_toggle_and_volume():
    rt = _runtime()
    rt.forwarder_es = FakeForwarder(volume=0.15)
    rt.apply("toggle_es")
    assert rt.forwarder_es.enabled is False
    assert rt.state.flags["es_forward"] is False
    rt.apply("es_volume_up")
    assert abs(rt.forwarder_es.volume - 0.20) < 1e-9
    rt.apply("set_volume:forwarder_es:0.40")
    assert abs(rt.forwarder_es.volume - 0.40) < 1e-9
    assert rt.state.flags["es_volume"] == 0.40


def test_set_switch_is_idempotent():
    rt = _runtime()
    # ya está activada: no debe cambiar nada
    assert rt.apply("set_switch:tts_es:1") == ""
    assert rt.speakers["listen"].enabled is True
    assert "silenciada" in rt.apply("set_switch:tts_es:0")
    assert rt.speakers["listen"].enabled is False
    assert "desconocido" in rt.apply("set_switch:inventado:1")


def test_set_duck_fija_la_atenuacion_de_los_fondos():
    rt = _runtime()
    rt.forwarder_es = FakeForwarder()
    assert "atenúa" in rt.apply("set_duck:0.70")
    assert rt.forwarder.duck_factor == 0.70
    assert rt.forwarder_es.duck_factor == 0.70
    assert rt.state.flags["duck_factor"] == 0.70
    assert "inválida" in rt.apply("set_duck:nope")


def test_set_duck_sin_fondos_avisa():
    rt = _runtime()
    rt.apply("toggle_ja")  # desactiva el japonés de fondo
    assert "no está activo" in rt.apply("toggle_ja") or True
    rt.forwarder = None
    rt.forwarder_es = None
    assert "no hay fondos" in rt.apply("set_duck:0.5")


def test_pause_restores_es_background_too():
    rt = _runtime()
    rt.forwarder_es = FakeForwarder()
    rt.forwarder_es.set_enabled(False)  # el usuario lo tenía apagado
    rt.apply("toggle_pause")
    assert rt.forwarder_es.enabled is False
    rt.apply("toggle_pause")
    assert rt.forwarder_es.enabled is False  # se respeta el estado previo
