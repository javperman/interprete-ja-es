"""Fábrica de motores TTS a partir de la configuración."""

from __future__ import annotations

from ..config import TtsEngineConfig
from .base import TtsEngine
from .piper import PiperTts
from .voicevox import VoicevoxTts


def build_tts(cfg: TtsEngineConfig) -> TtsEngine:
    if cfg.engine == "voicevox":
        return VoicevoxTts(
            url=cfg.url,
            speaker=cfg.speaker,
            speed_scale=cfg.speed_scale,
            intonation_scale=cfg.intonation_scale,
            pitch_scale=cfg.pitch_scale,
        )
    if cfg.engine == "piper":
        return PiperTts(
            voice=cfg.voice,
            voices_dir=cfg.voices_dir,
            length_scale=cfg.length_scale,
        )
    raise ValueError(f"motor TTS desconocido: {cfg.engine!r}")
