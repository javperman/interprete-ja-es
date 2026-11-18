"""Pruebas del arranque de los fondos (el fallo que los dejó mudos).

El 2026-11-13 el usuario reportó que no oía ni el japonés de fondo ni su voz de
fondo. La causa: al extraer el motor a ``session.py`` se perdió la llamada a
``JaForwarder.start()``; sin ella la cola interna queda en ``None`` y ``feed()``
descarta todos los frames **en silencio**. Estas pruebas fijan que se arranquen.
"""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

import interprete.audio as audio_pkg
import interprete.session as session_mod
from interprete.config import Config
from interprete.session import Session, SessionOptions, _start_fondo


class FakeUi:
    def __init__(self) -> None:
        self.state = _State()
        self.notices: list[tuple[str, str]] = []
        self.turns: list[tuple[str, object]] = []
        self.on_tick = None

    def notice(self, level: str, text: str) -> None:
        self.notices.append((level, text))

    def turn(self, key, res) -> None:
        self.turns.append((key, res))


class _State:
    def __init__(self) -> None:
        self.channels: list = []
        self.flags: dict = {}

    def channel(self, key):
        return next((c for c in self.channels if getattr(c, "key", None) == key), None)

    def elapsed_s(self) -> float:
        return 0.0


class FakeForwarder:
    """Doble que apunta si se arrancó (lo que se rompió)."""

    arrancados: list["FakeForwarder"] = []

    def __init__(self, target, **kwargs) -> None:
        self.target = target
        self.volume = kwargs.get("volume", 0.5)
        self.duck_factor = kwargs.get("duck_factor", 0.4)
        self.enabled = True
        self.dropped = 0
        self.started = False
        self.stopped = False
        self.frames = 0

    async def start(self) -> None:
        self.started = True
        FakeForwarder.arrancados.append(self)

    def feed(self, frame) -> None:
        if not self.started:
            return  # igual que el original: sin start() no se reproduce nada
        self.frames += 1

    def set_duck(self, on: bool) -> None:
        pass

    def set_enabled(self, on: bool) -> None:
        self.enabled = bool(on)

    def set_volume(self, volume: float) -> None:
        self.volume = float(volume)

    def set_duck_factor(self, factor: float) -> None:
        self.duck_factor = float(factor)

    async def stop(self) -> None:
        self.stopped = True


class FakeStt:
    def warmup(self) -> None:
        pass

    def transcribe_detailed(self, audio, sample_rate, language=None):
        return "こんにちは", "ja"

    def transcribe(self, audio, sample_rate, language=None):
        return "こんにちは"

    def close(self) -> None:
        pass


class FakeTranslator:
    async def translate_stream(self, text, **_kwargs):
        yield "hola"

    async def aclose(self) -> None:
        pass


class FakeTts:
    def synthesize(self, text, language="es"):
        from interprete.tts.base import AudioOut

        return AudioOut(audio=np.zeros(240, dtype=np.float32), sample_rate=24000)

    def is_ready(self) -> bool:
        return True

    def close(self) -> None:
        pass


class FakeSegmenter:
    pass


@pytest.fixture(autouse=True)
def _limpia_arrancados(monkeypatch):
    """Todos los tests de este módulo usan el doble de ``JaForwarder``."""
    FakeForwarder.arrancados = []
    monkeypatch.setattr("interprete.audio.player.JaForwarder", FakeForwarder)
    yield
    FakeForwarder.arrancados = []


@pytest.fixture
def sin_dispositivos(monkeypatch):
    monkeypatch.setattr(audio_pkg, "list_sink_names", lambda: [])
    monkeypatch.setattr(audio_pkg, "list_source_names", lambda: [])
    monkeypatch.setattr(audio_pkg, "default_sink", lambda: "hp")
    monkeypatch.setattr(audio_pkg, "default_source", lambda: "mic")


@pytest.fixture
def componentes_falsos(monkeypatch):
    import interprete.pipeline as pipeline_mod
    import interprete.tts as tts_mod

    monkeypatch.setattr(session_mod, "_build_stt", lambda cfg: FakeStt())
    monkeypatch.setattr(session_mod, "_build_segmenter", lambda cfg: FakeSegmenter())
    monkeypatch.setattr(session_mod, "build_translator", lambda cfg: FakeTranslator())
    # Sin TTS real: si no, el test dependería de que VOICEVOX esté levantado.
    monkeypatch.setattr(tts_mod, "build_tts", lambda cfg: FakeTts())
    monkeypatch.setattr(pipeline_mod, "Channel", lambda *a, **k: _FakeChannel())


class _FakeStats:
    results: tuple = ()
    dropped = 0
    empty = 0
    errors = 0
    seconds_processed = 0.0


class _FakeChannel:
    def __init__(self, *args, **kwargs) -> None:
        self.name = kwargs.get("name", "canal")
        self.speaker = None
        self.stats = _FakeStats()

    async def run(self, frames, stop_event=None) -> None:
        pass

    async def aclose(self) -> None:
        pass


def test_start_fondo_arranca_y_devuelve_el_reenvio():
    ui = FakeUi()
    fwd = asyncio.run(_start_fondo("meet_out", 0.5, 0.4, ui, "tu voz de fondo"))
    assert fwd is not None
    assert fwd.started is True
    assert FakeForwarder.arrancados == [fwd]
    assert ui.notices == []


def test_start_fondo_sin_destino_avisa():
    ui = FakeUi()
    assert asyncio.run(_start_fondo("", 0.5, 0.4, ui, "el japonés de fondo")) is None
    assert FakeForwarder.arrancados == []
    assert any("no sé dónde" in texto for _, texto in ui.notices)


def test_start_fondo_si_falla_no_tumba_la_sesion(monkeypatch):
    class Roto(FakeForwarder):
        async def start(self) -> None:
            raise FileNotFoundError("falta el comando 'pw-cat'")

    monkeypatch.setattr("interprete.audio.player.JaForwarder", Roto)
    ui = FakeUi()
    assert asyncio.run(_start_fondo("meet_out", 0.5, 0.4, ui, "tu voz de fondo")) is None
    assert any("no pude activar" in texto for _, texto in ui.notices)


def test_open_arranca_los_dos_fondos(sin_dispositivos, componentes_falsos, tmp_path):
    """Canal de escucha + japonés de fondo y canal de habla + tu voz de fondo."""
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")

    cfg = Config()
    options = SessionOptions(
        mode="run",
        input_wav=str(wav),
        headphones="hp",
        ja_forward=True,
        es_forward=True,
    )
    ui = FakeUi()
    sesion = Session(cfg, options, ui)

    ok = asyncio.run(_abrir(sesion))

    assert ok is True
    assert len(FakeForwarder.arrancados) == 2
    assert all(f.started for f in FakeForwarder.arrancados)
    assert sesion.runtime.forwarder is not None
    assert sesion.runtime.forwarder_es is not None
    # El japonés de fondo va a los auriculares; tu voz, al nodo que ve Meet.
    assert {f.target for f in FakeForwarder.arrancados} == {"hp", "meet_out"}
    asyncio.run(sesion.close())
    assert all(f.stopped for f in FakeForwarder.arrancados)


def test_sin_activar_el_fondo_no_se_arranca_nada(sin_dispositivos, componentes_falsos, tmp_path):
    wav = tmp_path / "clip.wav"
    wav.write_bytes(b"RIFF")
    options = SessionOptions(
        mode="listen", input_wav=str(wav), headphones="hp", ja_forward=False
    )
    sesion = Session(Config(), options, FakeUi())
    assert asyncio.run(_abrir(sesion)) is True
    assert FakeForwarder.arrancados == []
    assert sesion.runtime.forwarder is None
    asyncio.run(sesion.close())


async def _abrir(sesion: Session) -> bool:
    return await sesion.open()
