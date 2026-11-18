"""Pruebas de las fuentes de audio (sin PipeWire)."""

from __future__ import annotations

import asyncio

import numpy as np
import soundfile as sf

from interprete.audio.capture import MONITOR_PROPERTY, PwCapture, wav_frames


def _collect(agen) -> list[np.ndarray]:
    async def run():
        return [f async for f in agen]

    return asyncio.run(run())


def test_command_monitor_uses_property():
    cap = PwCapture("meet_in", rate=16000, channels=1, frame_samples=512, monitor=True)
    cmd = cap.command()
    assert "--target=meet_in" in cmd
    assert "--format=f32" in cmd
    assert "--raw" in cmd
    assert MONITOR_PROPERTY in cmd
    assert cmd[-1] == "-"


def test_command_plain_source_has_no_monitor_property():
    cap = PwCapture("alsa_input.usb", monitor=False)
    assert MONITOR_PROPERTY not in cap.command()


def test_wav_frames_sizes_and_padding(tmp_path):
    # 1000 muestras a 16 kHz -> 2 frames (512 + 512, el último con 24 de relleno)
    path = tmp_path / "tone.wav"
    sf.write(str(path), np.linspace(-0.5, 0.5, 1000, dtype=np.float32), 16000)
    frames = _collect(wav_frames(path, frame_samples=512))
    assert len(frames) == 2
    assert all(f.shape == (512,) for f in frames)
    assert frames[0].dtype == np.float32


def test_wav_frames_resamples_to_16k(tmp_path):
    path = tmp_path / "t48.wav"
    sf.write(str(path), np.zeros(48000, dtype=np.float32), 48000)  # 1 s
    frames = _collect(wav_frames(path, rate=16000, frame_samples=512))
    # 1 s a 16 kHz -> ~31.25 frames -> 32 frames
    assert len(frames) == 32
    assert all(f.shape == (512,) for f in frames)
