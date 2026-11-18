"""Interfaz de traductor. Implementación por defecto: DeepSeek (streaming)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class Translator(ABC):
    """Traduce texto entre dos idiomas con contexto y glosario opcional."""

    @abstractmethod
    def translate_stream(
        self,
        text: str,
        *,
        source: str,
        target: str,
        context: list[str] | None = None,
        glossary: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """Emite los fragmentos de la traducción conforme llegan (streaming)."""

    async def aclose(self) -> None:  # pragma: no cover - opcional
        """Libera el cliente HTTP."""
