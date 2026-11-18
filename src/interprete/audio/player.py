"""Reproducción de audio a nodos de PipeWire y reenvío del monitor.

Todo se hace con ``pw-cat --playback --target=<nodo> --format=f32 --raw -`` y
alimentando PCM **float32 mono** por stdin (verificado en el la máquina de pruebas).

- ``PwPlayback``: reproduce un fragmento (la voz sintetizada).
- ``PwPlayStream``: flujo continuo (el reenvío del japonés original).
- ``JaForwarder``: reenvía el audio original capturado a un nodo a volumen de
  fondo, con *ducking* relativo mientras suena la traducción y descarte si va
  retrasado (sirve para el japonés de fondo y para tu voz de fondo).
"""

from __future__ import annotations

import asyncio
import logging
import shutil

import numpy as np

log = logging.getLogger("interprete.audio.player")


def _need(cmd: str) -> None:
    if shutil.which(cmd) is None:
        raise FileNotFoundError(f"falta el comando '{cmd}' (paquete pipewire/pipewire-audio)")


def apply_gain(frame: np.ndarray, volume: float) -> np.ndarray:
    """Aplica un volumen lineal a un frame float32 (función pura, testeable)."""
    return (np.asarray(frame, dtype=np.float32) * float(volume)).astype(np.float32)


def playback_command(
    target: str, rate: int, *, channels: int = 1, binary: str = "pw-cat"
) -> list[str]:
    """Comando ``pw-cat`` para reproducir PCM f32 raw por stdin."""
    return [
        binary,
        "--playback",
        f"--target={target}",
        f"--rate={rate}",
        f"--channels={channels}",
        "--format=f32",
        "--raw",
        "-",
    ]


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is None:
        try:
            proc.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=2)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()


class PwPlayback:
    """Reproduce fragmentos de audio (float32 mono) en un nodo."""

    def __init__(self, target: str, *, binary: str = "pw-cat") -> None:
        self.target = target
        self.binary = binary

    async def play(self, audio: np.ndarray, rate: int) -> None:
        data = np.asarray(audio, dtype=np.float32)
        if data.size == 0:
            return
        _need(self.binary)
        proc = await asyncio.create_subprocess_exec(
            *playback_command(self.target, rate, binary=self.binary),
            stdin=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        assert proc.stdin is not None
        try:
            proc.stdin.write(data.tobytes())
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            log.warning("el proceso de reproducción cerró el pipe antes de tiempo")
        finally:
            try:
                proc.stdin.close()
            except (BrokenPipeError, ConnectionResetError):
                pass
        await proc.wait()


class PwPlayStream:
    """Flujo de reproducción continuo hacia un nodo."""

    def __init__(
        self, target: str, rate: int, *, channels: int = 1, binary: str = "pw-cat"
    ) -> None:
        self.target = target
        self.rate = rate
        self.channels = channels
        self.binary = binary
        self._proc: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        _need(self.binary)
        self._proc = await asyncio.create_subprocess_exec(
            *playback_command(self.target, self.rate, channels=self.channels, binary=self.binary),
            stdin=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

    async def write(self, audio: np.ndarray) -> bool:
        """Escribe un frame; devuelve ``False`` si el flujo ya no está disponible."""
        proc = self._proc
        if proc is None or proc.returncode is not None or proc.stdin is None:
            return False
        try:
            proc.stdin.write(np.asarray(audio, dtype=np.float32).tobytes())
            await proc.stdin.drain()
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False

    async def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        if proc.stdin is not None:
            try:
                proc.stdin.close()
            except (BrokenPipeError, ConnectionResetError):
                pass
        await _terminate(proc)


class JaForwarder:
    """Reenvía el audio original capturado a un nodo a un volumen de fondo.

    Usa una cola acotada para **no bloquear la captura**: si el reproductor se
    retrasa, se descartan los frames más antiguos (se cuenta en ``dropped``).

    Mientras suena la traducción, el fondo se atenúa a ``volume * duck_factor``
    (relativo, para que el fondo siga siendo audible con cualquier volumen).
    """

    def __init__(
        self,
        target: str,
        *,
        rate: int = 16000,
        volume: float = 0.50,
        duck_factor: float = 0.40,
        max_queue: int = 64,
        binary: str = "pw-cat",
    ) -> None:
        self.target = target
        self.rate = rate
        self.volume = volume
        self.duck_factor = duck_factor
        self.max_queue = max_queue
        self.binary = binary

        self.dropped = 0
        self.enabled = True  # ajuste en caliente (tecla j en la TUI)
        self._duck = False
        self._queue: asyncio.Queue | None = None
        self._stream: PwPlayStream | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._stream = PwPlayStream(self.target, self.rate, binary=self.binary)
        await self._stream.start()
        self._queue = asyncio.Queue(maxsize=self.max_queue)
        self._task = asyncio.create_task(self._writer())

    def set_duck(self, on: bool) -> None:
        """Baja el volumen del fondo mientras suena la traducción."""
        self._duck = bool(on)

    def set_enabled(self, on: bool) -> None:
        """Activa o desactiva el fondo (ajuste en caliente)."""
        self.enabled = bool(on)

    def set_volume(self, volume: float) -> None:
        """Fija el volumen del fondo (0–1)."""
        self.volume = max(0.0, min(1.0, float(volume)))

    def set_duck_factor(self, factor: float) -> None:
        """Cuánto se atenúa el fondo mientras habla la traducción (0–1)."""
        self.duck_factor = max(0.0, min(1.0, float(factor)))

    def current_gain(self) -> float:
        """Ganancia efectiva ahora mismo (para la interfaz y los tests)."""
        if not self.enabled:
            return 0.0
        return self.volume * self.duck_factor if self._duck else self.volume

    def feed(self, frame: np.ndarray) -> None:
        """Encola un frame capturado (no bloqueante)."""
        if self._queue is None:
            return
        try:
            self._queue.put_nowait(frame)
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(frame)
            except (asyncio.QueueEmpty, asyncio.QueueFull):  # pragma: no cover
                pass
            self.dropped += 1

    async def _writer(self) -> None:
        assert self._queue is not None and self._stream is not None
        while True:
            frame = await self._queue.get()
            if frame is None:
                break
            if not self.enabled:
                continue  # desactivado en caliente: se descartan los frames
            volume = self.volume * self.duck_factor if self._duck else self.volume
            if not await self._stream.write(apply_gain(frame, volume)):
                break

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - limpieza
                pass
            self._task = None
        if self._stream is not None:
            await self._stream.close()
            self._stream = None
