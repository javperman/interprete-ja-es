"""Pruebas de reproducción y reenvío (sin PipeWire)."""

from __future__ import annotations

import asyncio

import numpy as np

from interprete.audio.player import JaForwarder, apply_gain, playback_command


def test_apply_gain_scales():
    frame = np.ones(512, dtype=np.float32)
    out = apply_gain(frame, 0.25)
    assert out.dtype == np.float32
    assert np.allclose(out, 0.25)
    # no modifica el original
    assert np.allclose(frame, 1.0)


def test_playback_command_shape():
    cmd = playback_command("mis-auriculares", 22050)
    assert cmd[0] == "pw-cat"
    assert "--playback" in cmd
    assert "--target=mis-auriculares" in cmd
    assert "--rate=22050" in cmd
    assert "--format=f32" in cmd
    assert "--raw" in cmd
    assert cmd[-1] == "-"


def test_forwarder_drops_oldest_when_full():
    fwd = JaForwarder("hp", max_queue=1)

    async def run():
        fwd._queue = asyncio.Queue(maxsize=1)
        fwd.feed(np.full(4, 1.0, dtype=np.float32))  # ocupa
        fwd.feed(np.full(4, 2.0, dtype=np.float32))  # descarta el anterior
        fwd.feed(np.full(4, 3.0, dtype=np.float32))  # descarta el anterior
        return fwd._queue.get_nowait()

    kept = asyncio.run(run())
    assert fwd.dropped == 2
    assert np.allclose(kept, 3.0)  # se conserva el más reciente


def test_ducking_es_relativo_al_volumen():
    """El fondo se atenúa en proporción, no a un valor fijo: sigue oyéndose."""
    fwd = JaForwarder("hp", volume=0.60, duck_factor=0.40)
    assert fwd.current_gain() == 0.60
    fwd.set_duck(True)
    assert abs(fwd.current_gain() - 0.24) < 1e-9  # audible, no desaparece
    fwd.set_volume(0.30)
    assert abs(fwd.current_gain() - 0.12) < 1e-9
    fwd.set_duck(False)
    assert abs(fwd.current_gain() - 0.30) < 1e-9
    fwd.set_enabled(False)
    assert fwd.current_gain() == 0.0


def test_duck_factor_se_puede_subir_para_no_atenuar():
    fwd = JaForwarder("hp", volume=0.50, duck_factor=0.40)
    fwd.set_duck_factor(1.0)
    fwd.set_duck(True)
    assert fwd.current_gain() == 0.50  # 1.0 = no se atenúa nada
    fwd.set_duck_factor(2.5)  # se acota
    assert fwd.duck_factor == 1.0
