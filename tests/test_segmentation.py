"""Pruebas de la segmentación por VAD (lógica pura, sin PipeWire)."""

from __future__ import annotations

import numpy as np
import pytest

from interprete.vad.base import Segmenter


class FakeModel:
    """Modelo de VAD controlable desde el test."""

    def __init__(self, prob: float = 0.0) -> None:
        self.prob = prob

    def speech_probability(self, frame: np.ndarray) -> float:  # noqa: ARG002
        return self.prob


FRAME = 160  # 10 ms a 16 kHz


def _frame(value: float = 0.01) -> np.ndarray:
    return np.full(FRAME, value, dtype=np.float32)


def _segmenter(**kw) -> tuple[Segmenter, FakeModel]:
    model = FakeModel()
    defaults = dict(
        sample_rate=16000,
        threshold=0.5,
        min_silence_ms=30,
        speech_pad_ms=0,
        pre_roll_ms=0,
        max_speech_s=5.0,
    )
    defaults.update(kw)
    return Segmenter(model, **defaults), model


def test_no_segment_on_silence_only():
    seg, _ = _segmenter()
    for _ in range(20):
        assert seg.push(_frame()) is None


def test_emits_segment_after_silence():
    seg, model = _segmenter()
    for _ in range(3):
        assert seg.push(_frame()) is None
    model.prob = 0.9
    for _ in range(5):
        assert seg.push(_frame()) is None

    out = None
    model.prob = 0.0
    for _ in range(3):
        out = seg.push(_frame()) or out
    assert out is not None
    # 5 fotogramas de voz (el silencio final se recorta con speech_pad_ms=0)
    assert len(out.audio) == 5 * FRAME
    assert out.duration == pytest.approx(50 / 1000)


def test_pre_roll_included():
    seg, model = _segmenter(pre_roll_ms=50)
    for _ in range(5):  # 5 fotogramas de silencio -> pre-roll
        seg.push(_frame())
    model.prob = 0.9
    for _ in range(4):
        seg.push(_frame())
    model.prob = 0.0
    out = None
    for _ in range(3):
        out = seg.push(_frame()) or out
    assert out is not None
    assert len(out.audio) == (5 + 4) * FRAME


def test_max_speech_caps_segment():
    seg, model = _segmenter(max_speech_s=0.1)  # 100 ms -> 10 fotogramas
    model.prob = 0.9
    out = None
    for _ in range(30):
        out = seg.push(_frame()) or out
    assert out is not None
    assert out.duration <= 0.1 + 1e-6


def test_flush_forces_segment():
    seg, model = _segmenter()
    model.prob = 0.9
    for _ in range(5):
        seg.push(_frame())
    out = seg.flush()
    assert out is not None
    assert len(out.audio) == 5 * FRAME
