"""Pruebas del locutor español (backpressure y ducking), con dobles."""

from __future__ import annotations

import asyncio

import numpy as np

from interprete.pipeline import Speaker, SpanishSpeaker
from interprete.tts.base import AudioOut


class FakeTts:
    def __init__(self) -> None:
        self.calls = 0

    def synthesize(self, text: str, language: str = "es") -> AudioOut:
        self.calls += 1
        return AudioOut(audio=np.full(2205, 0.1, dtype=np.float32), sample_rate=22050)

    def close(self) -> None:
        pass


class SlowPlayer:
    def __init__(self) -> None:
        self.played = 0
        self.rates: list[int] = []

    async def play(self, audio, rate: int) -> None:
        self.played += 1
        self.rates.append(rate)
        await asyncio.sleep(0.05)


class FakeForwarder:
    def __init__(self) -> None:
        self.ducks: list[bool] = []

    def set_duck(self, on: bool) -> None:
        self.ducks.append(bool(on))


def test_submits_and_plays():
    tts, player = FakeTts(), SlowPlayer()
    sp = SpanishSpeaker(tts, player)

    async def run():
        assert sp.submit("Hola a todos") is True
        await sp.aclose()

    asyncio.run(run())
    assert sp.spoken == 1
    assert player.played == 1
    assert player.rates == [22050]


def test_busy_drops_new_utterance_degrades_to_text():
    tts, player = FakeTts(), SlowPlayer()
    sp = SpanishSpeaker(tts, player)

    async def run():
        assert sp.submit("primera") is True
        assert sp.submit("segunda") is False  # ocupado -> se descarta
        await sp.aclose()

    asyncio.run(run())
    assert sp.spoken == 1
    assert sp.skipped == 1
    assert tts.calls == 1


def test_ducking_toggles_around_playback():
    fwd = FakeForwarder()
    sp = SpanishSpeaker(FakeTts(), SlowPlayer(), forwarder=fwd)

    async def run():
        sp.submit("hola")
        await sp.aclose()

    asyncio.run(run())
    # se activa al empezar a hablar y se desactiva al terminar
    assert fwd.ducks == [True, False]


def test_empty_text_ignored():
    sp = SpanishSpeaker(FakeTts(), SlowPlayer())
    assert sp.submit("   ") is False


def test_queue_mode_plays_in_order_and_drops_oldest():
    spoken: list[str] = []
    sp = Speaker(
        FakeTts(),
        SlowPlayer(),
        lang="ja",
        mode="queue",
        queue_size=2,
        on_spoken=spoken.append,
    )

    async def run():
        # sin await entre submits: el worker no arranca hasta aclose()
        for t in ("a", "b", "c", "d"):
            sp.submit(t)
        await sp.aclose()

    asyncio.run(run())
    assert sp.dropped == 2  # se descartaron 'a' y 'b' (las más antiguas)
    assert spoken == ["c", "d"]  # se dicen en orden
    assert sp.spoken == 2


def test_queue_mode_keeps_all_when_room():
    spoken: list[str] = []
    sp = Speaker(FakeTts(), SlowPlayer(), mode="queue", queue_size=8, on_spoken=spoken.append)

    async def run():
        for t in ("uno", "dos", "tres"):
            sp.submit(t)
        await sp.aclose()

    asyncio.run(run())
    assert sp.dropped == 0
    assert spoken == ["uno", "dos", "tres"]
