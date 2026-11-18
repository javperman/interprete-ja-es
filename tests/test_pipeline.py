"""Pruebas del pipeline de escucha con dobles de prueba (sin hardware)."""

from __future__ import annotations

import asyncio

import pytest
from collections.abc import AsyncIterator

import numpy as np

from interprete.pipeline import ListenPipeline
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
    """VAD determinista: silencio si la media < 0.25, voz si no."""

    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate

    def speech_probability(self, frame: np.ndarray) -> float:
        return 0.9 if float(np.mean(frame)) > 0.25 else 0.0


class FakeStt:
    def transcribe(self, audio, sample_rate, language=None) -> str:
        return "こんにちは"

    def close(self) -> None:
        pass


class FakeTranslator:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def translate_stream(self, text, *, source, target, context=None, glossary=None):
        self.calls.append({"text": text, "context": context, "source": source, "target": target})
        for chunk in ("Hola", " a todos"):
            await asyncio.sleep(0)
            yield chunk

    async def aclose(self) -> None:
        pass


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


def _run(pipeline, seq):
    asyncio.run(pipeline.run(_frames(seq)))


def test_single_turn_transcribes_and_translates():
    tr = FakeTranslator()
    p = ListenPipeline(stt=FakeStt(), translator=tr, segmenter=_segmenter())
    _run(p, [FRAME, FRAME, SPEECH, SPEECH, SPEECH, FRAME, FRAME])

    assert len(p.results) == 1
    res = p.results[0]
    assert res.source_text == "こんにちは"
    assert res.target_text == "Hola a todos"
    assert res.speech_s == 3 * 512 / 16000
    # instrumentación por etapa
    for key in ("stt_ms", "mt_ms", "mt_ttft_ms", "total_ms"):
        assert key in res.timing.spans or key == "total_ms"
    assert res.timing.total_ms is not None
    assert res.total_ms is not None and res.total_ms >= 0


def test_context_passed_on_second_turn():
    tr = FakeTranslator()
    p = ListenPipeline(stt=FakeStt(), translator=tr, segmenter=_segmenter(), context_sentences=4)
    _run(
        p,
        [FRAME, SPEECH, SPEECH, SPEECH, FRAME, SPEECH, SPEECH, SPEECH, FRAME, FRAME],
    )
    assert len(p.results) == 2
    assert tr.calls[0]["context"] is None
    assert tr.calls[1]["context"] == ["Hola a todos"]


def test_empty_transcription_is_skipped():
    class SilentStt(FakeStt):
        def transcribe(self, audio, sample_rate, language=None) -> str:
            return "   "

    tr = FakeTranslator()
    p = ListenPipeline(stt=SilentStt(), translator=tr, segmenter=_segmenter())
    _run(p, [SPEECH, SPEECH, FRAME, FRAME])
    assert p.results == []
    assert p.empty == 1
    assert tr.calls == []


def test_translator_error_does_not_kill_channel():
    class BoomTranslator(FakeTranslator):
        async def translate_stream(self, text, *, source, target, context=None, glossary=None):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    tr = BoomTranslator()
    p = ListenPipeline(stt=FakeStt(), translator=tr, segmenter=_segmenter())
    _run(p, [SPEECH, SPEECH, FRAME, FRAME])
    assert p.results == []
    assert p.errors == 1


def test_backpressure_drops_and_counts():
    p = ListenPipeline(stt=FakeStt(), translator=FakeTranslator(), segmenter=_segmenter())

    async def run():
        q: asyncio.Queue = asyncio.Queue(maxsize=1)
        q.put_nowait((0.0, "ocupa"))
        p._enqueue(q, "nueva")  # cola llena -> se descarta

    asyncio.run(run())
    assert p.dropped == 1


def test_latency_log_written(tmp_path):
    from interprete.latency import LatencyLog

    out = tmp_path / "lat.csv"
    p = ListenPipeline(
        stt=FakeStt(),
        translator=FakeTranslator(),
        segmenter=_segmenter(),
        latency_log=LatencyLog(out),
    )
    _run(p, [SPEECH, SPEECH, FRAME, FRAME])
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("stt_ms")
    assert "mt_ttft_ms" in lines[0] and "queue_ms" in lines[0]
    assert len(lines) == 2  # cabecera + una fila
    assert lines[1].count(",") == lines[0].count(",")
