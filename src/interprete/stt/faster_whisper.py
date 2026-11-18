"""STT con faster-whisper (modelo caliente en GPU).

Reutiliza el modelo ``large-v3-turbo`` que ya está en la caché de Hugging Face
del equipo. Para CUDA usa las librerías CUDA 12 de usuario
(``~/.local/share/hermes-cuda``): conviene exportar ``LD_LIBRARY_PATH`` **antes**
de arrancar el proceso (lo hace ``scripts/stt-daemon``).
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

import numpy as np

from ..filters import is_hallucination
from .base import SttBackend

log = logging.getLogger("interprete.stt")

DEFAULT_MODEL = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"

# El modelo se guarda por proceso y se **reutiliza** entre sesiones: cargar dos
# veces el mismo modelo en una GPU pequeña (4 GB) acaba en
# «CUDA failed with error out of memory», que es lo que pasó al reiniciar una
# sesión sin cerrar la app.
_MODELOS: dict[tuple, object] = {}
_MODELOS_LOCK = threading.Lock()


def modelo_compartido(
    model: str,
    device: str,
    compute_type: str,
    cpu_threads: int = 0,
):
    """Devuelve el modelo ya cargado (lo carga la primera vez).

    ``device="auto"`` intenta CUDA y, si la GPU no tiene memoria, usa la CPU.
    """
    clave = (model, device, compute_type, cpu_threads)
    with _MODELOS_LOCK:
        ya = _MODELOS.get(clave)
        if ya is not None:
            return ya
        from faster_whisper import WhisperModel

        kwargs: dict[str, object] = {"device": device, "compute_type": compute_type}
        if cpu_threads:
            kwargs["cpu_threads"] = cpu_threads
        modelo = WhisperModel(model, **kwargs)
        _MODELOS[clave] = modelo
        return modelo


def cargar_modelo(
    model: str,
    device: str,
    compute_type: str,
    cpu_threads: int = 0,
) -> tuple[object, str]:
    """Carga el modelo y devuelve ``(modelo, dispositivo_real)``.

    Con ``device="auto"`` prueba CUDA y, si falla por falta de memoria (u otra
    razón de la GPU), sigue en CPU para que la reunión no se quede sin intérprete.
    """
    if device != "auto":
        return modelo_compartido(model, device, compute_type, cpu_threads), device

    # Primero reutiliza lo que ya esté cargado (no vuelve a pedir memoria).
    with _MODELOS_LOCK:
        for (m, d, _ct, _cpu), modelo in _MODELOS.items():
            if m == model:
                return modelo, d
    try:
        return modelo_compartido(model, "cuda", compute_type, cpu_threads), "cuda"
    except Exception as exc:  # noqa: BLE001 - sin GPU seguimos en CPU
        log.warning("no pude usar la GPU (%s): paso a CPU", exc)
        return modelo_compartido(model, "cpu", "int8", cpu_threads), "cpu"


def liberar_modelos() -> int:
    """Descarga los modelos y libera la memoria de la GPU. Devuelve cuántos había."""
    import gc

    with _MODELOS_LOCK:
        cuantos = len(_MODELOS)
        _MODELOS.clear()
    gc.collect()
    return cuantos


def modelos_cargados() -> list[tuple[str, str]]:
    """``[(modelo, dispositivo)]`` de lo que hay cargado ahora mismo."""
    with _MODELOS_LOCK:
        return [(m, d) for (m, d, _ct, _cpu) in _MODELOS]


def cuda_lib_dirs(root: str | Path) -> list[str]:
    """Directorios ``lib`` de los wheels ``nvidia-*`` instalados en ``root``."""
    root = Path(root).expanduser()
    dirs: list[str] = []
    nvidia = root / "nvidia"
    if nvidia.is_dir():
        for sub in sorted(nvidia.iterdir()):
            lib = sub / "lib"
            if lib.is_dir():
                dirs.append(str(lib))
    if (root / "lib").is_dir():
        dirs.append(str(root / "lib"))
    return dirs


def preload_ld_library_path(root: str | Path) -> None:
    """Antepone los directorios CUDA al ``LD_LIBRARY_PATH`` del proceso actual."""
    dirs = cuda_lib_dirs(root)
    if not dirs:
        return
    current = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["LD_LIBRARY_PATH"] = ":".join(dirs + ([current] if current else []))


class FasterWhisperStt(SttBackend):
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        device: str = "cuda",
        compute_type: str = "int8_float16",
        beam_size: int = 1,
        cuda_lib_path: str | None = None,
        cpu_threads: int = 0,
        no_speech_threshold: float = 0.6,
        log_prob_threshold: float = -1.0,
        compression_ratio_threshold: float = 2.4,
    ) -> None:
        if cuda_lib_path and device.startswith("cuda"):
            preload_ld_library_path(cuda_lib_path)
        # El modelo se comparte por proceso (y con ``device="auto"`` cae a CPU si
        # la GPU no tiene memoria): así se puede parar y volver a iniciar.
        self._model, self.device = cargar_modelo(model, device, compute_type, cpu_threads)
        self.beam_size = beam_size
        # Confianza mínima: por debajo se considera ruido y no frases inventadas.
        self.no_speech_threshold = no_speech_threshold
        self.log_prob_threshold = log_prob_threshold
        self.compression_ratio_threshold = compression_ratio_threshold
        # Los dos canales comparten el modelo; serializamos las llamadas a la GPU.
        self._lock = threading.Lock()

    def transcribe(
        self, audio: np.ndarray, sample_rate: int, language: str | None = None
    ) -> str:
        return self.transcribe_detailed(audio, sample_rate, language)[0]

    def _segmento_valido(self, seg) -> bool:
        """¿El segmento es voz real o una invención del modelo?

        Con ruido, música o silencio Whisper **inventa** frases («お待ちしております»)
        y las devuelve con total seguridad, así que no basta el texto: hay que
        mirar las métricas del propio modelo.
        """
        if getattr(seg, "no_speech_prob", 0.0) > self.no_speech_threshold:
            log.debug("descartado por no_speech_prob: %.2f %r", seg.no_speech_prob, seg.text)
            return False
        if getattr(seg, "avg_logprob", 0.0) < self.log_prob_threshold:
            log.debug("descartado por avg_logprob: %.2f %r", seg.avg_logprob, seg.text)
            return False
        if getattr(seg, "compression_ratio", 0.0) > self.compression_ratio_threshold:
            log.debug("descartado por repetición: %.2f", seg.compression_ratio)
            return False
        return True

    def transcribe_detailed(
        self, audio: np.ndarray, sample_rate: int, language: str | None = None
    ) -> tuple[str, str | None]:
        """Transcribe y devuelve además el idioma detectado (útil en modo auto)."""
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        if sample_rate != 16000:
            import soxr

            audio = soxr.resample(audio, sample_rate, 16000)
        with self._lock:
            segments, info = self._model.transcribe(
                audio,
                language=language,
                beam_size=self.beam_size,
                vad_filter=False,  # la segmentación la hace nuestra VAD
                condition_on_previous_text=False,
                no_speech_threshold=self.no_speech_threshold,
                log_prob_threshold=self.log_prob_threshold,
                compression_ratio_threshold=self.compression_ratio_threshold,
            )
            partes = [seg.text for seg in segments if self._segmento_valido(seg)]
            detected = getattr(info, "language", None)
        text = "".join(partes).strip()
        if not text:
            return "", detected
        if is_hallucination(text):
            log.debug("descartado por frase inventada: %r", text)
            return "", detected
        return text, detected

    def warmup(self) -> None:
        self.transcribe(np.zeros(16000, dtype=np.float32), 16000, language=None)

    def close(self) -> None:
        """No descarga el modelo: se comparte entre sesiones del mismo proceso.

        Para liberar la GPU de verdad está ``liberar_modelos()``.
        """
