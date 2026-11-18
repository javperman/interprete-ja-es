"""Interfaz de STT. Implementaciones en ``faster_whisper`` (y, en su caso,
``hermes_socket``)."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class SttBackend(ABC):
    """Transcribe audio a texto."""

    @abstractmethod
    def transcribe(
        self, audio: np.ndarray, sample_rate: int, language: str | None = None
    ) -> str:
        """Devuelve el texto de ``audio`` (float32 mono)."""

    def warmup(self) -> None:  # pragma: no cover - opcional
        """Carga el modelo si hace falta (evita el coste en la primera frase)."""

    def transcribe_detailed(
        self, audio: np.ndarray, sample_rate: int, language: str | None = None
    ) -> tuple[str, str | None]:
        """Como ``transcribe`` pero devuelve también el idioma detectado.

        Implementación por defecto: delega en ``transcribe`` y no informa idioma.
        Los backends que pueden detectarlo (faster-whisper) lo sobrescriben.
        """
        return self.transcribe(audio, sample_rate, language), None

    def close(self) -> None:  # pragma: no cover - opcional
        """Libera recursos."""
