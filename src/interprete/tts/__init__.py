"""Síntesis de voz (TTS)."""

from .base import AudioOut, TtsEngine
from .factory import build_tts
from .piper import PiperTts
from .voicevox import VoicevoxTts

__all__ = ["AudioOut", "PiperTts", "TtsEngine", "VoicevoxTts", "build_tts"]
