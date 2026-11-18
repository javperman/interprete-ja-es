"""Pruebas de integración de Piper (se omiten si la voz no está instalada)."""

from __future__ import annotations

from pathlib import Path

import pytest

VOICE = "es_ES-davefx-medium"
MODEL = Path.home() / f".local/share/interprete/piper/{VOICE}/{VOICE}.onnx"


def _piper_installed() -> bool:
    try:
        import piper  # noqa: F401
    except ImportError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not (MODEL.exists() and _piper_installed()),
    reason="Piper o la voz no están instalados (scripts/install-piper.sh)",
)


def test_synthesize_spanish():
    from interprete.tts import PiperTts

    tts = PiperTts(voice=VOICE)
    assert tts.is_ready()
    out = tts.synthesize("Buenos días, empecemos la reunión.", "es")
    assert out.sample_rate == 22050
    assert out.audio.dtype.name == "float32"
    assert out.audio.size > 22050  # al menos ~1 s
    assert abs(out.audio).max() > 0.01
