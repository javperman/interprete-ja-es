"""Pruebas del VAD Silero ONNX (se omiten si falta el modelo)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

MODEL = Path.home() / ".cache/interprete/silero_vad.onnx"

pytestmark = pytest.mark.skipif(not MODEL.exists(), reason="modelo Silero ONNX no disponible")


def test_silence_is_low_probability():
    from interprete.vad import SileroOnnxVad

    vad = SileroOnnxVad()
    rng = np.random.default_rng(0)
    probs = [
        vad.speech_probability(rng.normal(0, 1e-4, vad.frame_samples).astype(np.float32))
        for _ in range(10)
    ]
    assert max(probs) < 0.5


def test_frame_size_enforced():
    from interprete.vad import SileroOnnxVad

    vad = SileroOnnxVad()
    with pytest.raises(ValueError):
        vad.speech_probability(np.zeros(100, dtype=np.float32))


def test_state_reset():
    from interprete.vad import SileroOnnxVad

    vad = SileroOnnxVad()
    frame = np.full(vad.frame_samples, 0.1, dtype=np.float32)
    p1 = vad.speech_probability(frame)
    vad.reset()
    p2 = vad.speech_probability(frame)
    assert p1 == pytest.approx(p2)
