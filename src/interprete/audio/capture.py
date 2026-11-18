"""Fuentes de audio (frames) para el pipeline.

Un **frame** es un ``np.ndarray`` float32 mono de ``frame_samples`` muestras
(512 a 16 kHz), el tamaño que exige Silero.

- ``PwCapture``: captura continua de un nodo PipeWire con ``pw-record``.
- ``wav_frames``: reproduce un WAV como si fuera un flujo de frames (pruebas).
- ``inject_wav``: envía un WAV a un nodo con ``pw-cat`` (modo de pruebas).

Detalle verificado (2026-11-13): el *monitor* de un sink **no** es un nodo
PipeWire aparte, así que ``pw-record --target=meet_in.monitor`` cae al micro
por defecto. La forma correcta es apuntar al sink y pedir su monitor con
``-P '{ stream.capture.sink=true }'``.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import AsyncIterator
from pathlib import Path

import numpy as np

from .pw import read_wav, resample

FRAME_SAMPLES = 512  # 32 ms a 16 kHz (requisito de Silero)
DEFAULT_RATE = 16000
MONITOR_PROPERTY = "{ stream.capture.sink=true }"


def _need(cmd: str) -> None:
    if shutil.which(cmd) is None:
        raise FileNotFoundError(f"falta el comando '{cmd}' (paquete pipewire/pipewire-audio)")


class PwCapture:
    """Captura continua de un nodo de PipeWire como frames float32 mono.

    Si ``monitor=True`` captura el *monitor* del sink (audio que se reproduce en
    él) en lugar de una fuente normal. Es el modo del canal de escucha.
    """

    def __init__(
        self,
        target: str,
        *,
        rate: int = DEFAULT_RATE,
        channels: int = 1,
        frame_samples: int = FRAME_SAMPLES,
        monitor: bool = False,
        latency: str = "30ms",
        binary: str = "pw-record",
    ) -> None:
        self.target = target
        self.rate = rate
        self.channels = channels
        self.frame_samples = frame_samples
        self.monitor = monitor
        self.latency = latency
        self.binary = binary

    def command(self) -> list[str]:
        """Comando ``pw-record`` equivalente (útil para logs y tests)."""
        cmd = [
            self.binary,
            f"--target={self.target}",
            f"--rate={self.rate}",
            f"--channels={self.channels}",
            "--format=f32",
            "--raw",
        ]
        if self.latency:
            cmd.append(f"--latency={self.latency}")
        if self.monitor:
            cmd += ["-P", MONITOR_PROPERTY]
        cmd.append("-")  # stdout
        return cmd

    async def frames(self) -> AsyncIterator[np.ndarray]:
        """Genera frames hasta que el proceso de captura termina."""
        _need(self.binary)
        proc = await asyncio.create_subprocess_exec(
            *self.command(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stderr_lines: list[str] = []
        drain = asyncio.create_task(_drain_stderr(proc, stderr_lines))
        nbytes = self.frame_samples * self.channels * 4
        yielded = 0
        try:
            while True:
                try:
                    raw = await proc.stdout.readexactly(nbytes)
                except asyncio.IncompleteReadError:
                    break
                arr = np.frombuffer(raw, dtype=np.float32)
                if self.channels > 1:
                    arr = arr.reshape(-1, self.channels).mean(axis=1)
                yield arr.astype(np.float32, copy=True)
                yielded += 1
        finally:
            await _terminate(proc, drain)
        if yielded == 0 and stderr_lines:
            raise RuntimeError(
                f"pw-record no capturó nada de {self.target!r}: "
                + " ".join(stderr_lines)[:300]
            )


async def _drain_stderr(proc: asyncio.subprocess.Process, sink: list[str]) -> None:
    if proc.stderr is None:
        return
    while True:
        line = await proc.stderr.readline()
        if not line:
            break
        sink.append(line.decode("utf-8", "replace").strip())


async def _terminate(proc: asyncio.subprocess.Process, drain: asyncio.Task) -> None:
    if proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
    drain.cancel()
    try:
        await drain
    except (asyncio.CancelledError, Exception):  # noqa: BLE001 - limpieza
        pass


async def wav_frames(
    path: str | Path,
    *,
    rate: int = DEFAULT_RATE,
    frame_samples: int = FRAME_SAMPLES,
    realtime: bool = False,
) -> AsyncIterator[np.ndarray]:
    """Reproduce un WAV como flujo de frames float32 mono a ``rate``.

    Con ``realtime=True`` espera el tiempo de cada frame (simula audio en vivo);
    con ``realtime=False`` los emite lo antes posible (tests).
    """
    data, sr = read_wav(path)
    mono = data.mean(axis=1)
    if sr != rate:
        mono = resample(mono, sr, rate)
    mono = np.asarray(mono, dtype=np.float32).reshape(-1)

    total = len(mono)
    i = 0
    while i < total:
        chunk = mono[i : i + frame_samples]
        if len(chunk) < frame_samples:
            chunk = np.pad(chunk, (0, frame_samples - len(chunk)))
        if realtime:
            await asyncio.sleep(frame_samples / rate)
        yield chunk.astype(np.float32, copy=True)
        i += frame_samples


async def inject_wav(
    target: str,
    path: str | Path,
    *,
    volume: float = 1.0,
    binary: str = "pw-cat",
) -> asyncio.subprocess.Process:
    """Envía un WAV al nodo ``target`` con ``pw-cat`` (devuelve el proceso)."""
    _need(binary)
    return await asyncio.create_subprocess_exec(
        binary,
        "--playback",
        f"--target={target}",
        f"--volume={volume}",
        str(path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
