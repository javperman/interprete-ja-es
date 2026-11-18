"""Utilidades de audio sobre PipeWire (``pw-cat``/``pw-record``/``pactl``).

Se usan subprocesos que apuntan a los nodos **por nombre**, sin depender del
naming de PortAudio. El remuestreo se hace con ``soxr``.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr


def _need(cmd: str) -> None:
    if shutil.which(cmd) is None:
        raise FileNotFoundError(f"falta el comando '{cmd}' (paquete pipewire/pipewire-audio)")


def list_sink_names() -> list[str]:
    _need("pactl")
    out = subprocess.run(
        ["pactl", "list", "short", "sinks"], capture_output=True, text=True, check=True
    ).stdout
    return [line.split("\t")[1] for line in out.splitlines() if line.strip()]


def list_source_names() -> list[str]:
    _need("pactl")
    out = subprocess.run(
        ["pactl", "list", "short", "sources"], capture_output=True, text=True, check=True
    ).stdout
    return [line.split("\t")[1] for line in out.splitlines() if line.strip()]


def node_exists(name: str) -> bool:
    return name in list_sink_names() or name in list_source_names()


def default_sink() -> str:
    """Nombre del sink por defecto (normalmente los auriculares)."""
    _need("pactl")
    return subprocess.run(
        ["pactl", "get-default-sink"], capture_output=True, text=True, check=True
    ).stdout.strip()


def default_source() -> str:
    """Nombre de la fuente (micrófono) por defecto."""
    _need("pactl")
    return subprocess.run(
        ["pactl", "get-default-source"], capture_output=True, text=True, check=True
    ).stdout.strip()


def play_file(target: str, path: str | Path, *, rate: int = 48000) -> None:
    """Reproduce un WAV en el nodo ``target`` (bloqueante)."""
    _need("pw-cat")
    subprocess.run(
        ["pw-cat", "--playback", f"--target={target}", f"--rate={rate}", str(path)],
        check=True,
    )


def record_to_wav(
    target: str,
    path: str | Path,
    seconds: float,
    *,
    rate: int = 48000,
    channels: int = 2,
    monitor: bool = False,
) -> None:
    """Graba ``seconds`` segundos del nodo ``target`` a un WAV s16le.

    Con ``monitor=True`` graba el *monitor* del sink ``target`` (el monitor no es
    un nodo aparte; se pide con ``stream.capture.sink``).
    """
    _need("pw-record")
    cmd = [
        "pw-record",
        f"--target={target}",
        f"--rate={rate}",
        f"--channels={channels}",
        "--format=s16",
    ]
    if monitor:
        cmd += ["-P", "{ stream.capture.sink=true }"]
    cmd.append(str(path))
    with subprocess.Popen(cmd, stderr=subprocess.DEVNULL) as proc:
        try:
            proc.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=2)


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """Lee un WAV como float32 mono/stereo en ``(data, samplerate)``."""
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return data, int(sr)


def write_wav(path: str | Path, data: np.ndarray, rate: int) -> None:
    sf.write(str(path), data, rate, subtype="PCM_16")


def resample(data: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return data
    return soxr.resample(data, sr_in, sr_out)


def temp_wav(suffix: str = ".wav") -> Path:
    fd, name = tempfile.mkstemp(suffix=suffix, prefix="interprete-")
    Path(name).unlink(missing_ok=True)
    return Path(name)
