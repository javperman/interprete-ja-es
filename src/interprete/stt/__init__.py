"""Reconocimiento de voz (STT)."""

from .base import SttBackend
from .faster_whisper import FasterWhisperStt

__all__ = ["FasterWhisperStt", "SttBackend"]
