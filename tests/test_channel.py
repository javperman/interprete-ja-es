"""Pruebas del canal completo y del reenvío (con dobles, sin hardware)."""

from __future__ import annotations

import asyncio

import pytest
from collections.abc import AsyncIterator

import numpy as np

from interprete.pipeline import Channel, tee_frames
from interprete.tts.base import AudioOut
from interprete.vad.base import Segmenter


@pytest.fixture(autouse=True)
def _sin_filtros_por_defecto(monkeypatch):
    """Los dobles usan segmentos de 32 ms: aquí se prueba el pipeline, no el filtrado.

    El filtrado real (duración mínima, frases inventadas y eco) se prueba en
    ``tests/test_filters.py``.
    """
    from interprete.filters import TurnFilters as _Reales

    monkeypatch.setattr(
        "interprete.pipeline.listen.TurnFilters",
        lambda *a, **k: _Reales(min_speech_ms=0, hallucination_filter=False),
    )


FRAME = np.zeros(512, dtype=np.float32)
SPEECH = np.full(512, 0.5, dtype=np.float32)


class FakeVad:
    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate

    def speech_probability(self, frame: np.ndarray) -> float:
        return 0.9 if float(np.mean(frame)) > 0.25 else 0.0


class FakeStt:
    def transcribe(self, audio, sample_rate, language=None) -> str:
        return "Z" if language == "es" else "こんにちは"


class FakeTranslator:
    async def translate_stream(self, text, *, source, target, context=None, glossary=None):
        yield "TRADUCCIÓN"

    async def aclose(self) -> None:
        pass


class FakeTts:
    def synthesize(self, text: str, language: str = "es") -> AudioOut:
        return AudioOut(audio=np.ones(2205, dtype=np.float32) * 0.1, sample_rate=22050)

    def close(self) -> None:
        pass


class FakePlayer:
    def __init__(self) -> None:
        self.played: list[int] = []

    async def play(self, audio, rate: int) -> None:
        self.played.append(rate)


def _segmenter() -> Segmenter:
    return Segmenter(
        FakeVad(),
        sample_rate=16000,
        threshold=0.5,
        min_silence_ms=32,
        speech_pad_ms=0,
        pre_roll_ms=0,
        max_speech_s=5.0,
    )


def _frames(seq: list[np.ndarray]) -> AsyncIterator[np.ndarray]:
    async def gen():
        for f in seq:
            yield f

    return gen()


def _make_channel(seen: list, player=None, tts=None) -> Channel:
    return Channel(
        "test",
        stt=FakeStt(),
        translator=FakeTranslator(),
        segmenter=_segmenter(),
        source_lang="ja",
        target_lang="es",
        tts=tts,
        player=player,
        on_result=seen.append,
    )


def test_channel_reports_result():
    seen: list = []
    ch = _make_channel(seen)
    asyncio.run(ch.run(_frames([FRAME, SPEECH, SPEECH, FRAME, FRAME])))
    assert len(seen) == 1
    assert seen[0].target_text == "TRADUCCIÓN"
    assert ch.stats.results  # el pipeline acumula resultados


def test_channel_with_speaker_plays_translation():
    seen: list = []
    player = FakePlayer()
    ch = _make_channel(seen, player=player, tts=FakeTts())

    async def run():
        await ch.run(_frames([SPEECH, SPEECH, FRAME, FRAME]))
        await ch.aclose()

    asyncio.run(run())
    assert player.played == [22050]  # se reprodujo la traducción


def test_tee_frames_feeds_none_and_passes_through():
    class Fwd:
        def __init__(self) -> None:
            self.got: list[np.ndarray] = []

        def feed(self, frame) -> None:
            self.got.append(frame)

    async def gen():
        for i in range(3):
            yield np.full(4, i, dtype=np.float32)

    async def run():
        fwd = Fwd()
        out = [f async for f in tee_frames(gen(), fwd)]
        return fwd, out

    fwd, out = asyncio.run(run())
    assert len(out) == 3
    assert len(fwd.got) == 3
    assert np.allclose(fwd.got[2], 2.0)
