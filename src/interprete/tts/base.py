"""Interfaz de TTS. Implementaciones: VOICEVOX (ja) y Piper (es)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class AudioOut:
    audio: np.ndarray  # float32, forma (n,) o (n, canales)
    sample_rate: int


class TtsEngine(ABC):
    """Convierte texto en audio."""

    @abstractmethod
    def synthesize(self, text: str, language: str) -> AudioOut:
        """Sintetiza ``text`` y devuelve audio float32."""

    def close(self) -> None:  # pragma: no cover - opcional
        """Libera recursos."""
