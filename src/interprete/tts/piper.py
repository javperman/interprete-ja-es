"""TTS español con Piper (paquete ``piper-tts``, OHF-voice/piper1-gpl).

Instalación (sin root): ``scripts/install-piper.sh`` — instala ``piper-tts`` en el
venv y descarga la voz a ``~/.local/share/interprete/piper/<voz>/``.

Voz por defecto: ``es_ES-davefx-medium`` (22050 Hz, mono).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .base import AudioOut, TtsEngine

DEFAULT_VOICE = "es_ES-davefx-medium"
DEFAULT_VOICES_DIR = "~/.local/share/interprete/piper"


class PiperTts(TtsEngine):
    def __init__(
        self,
        voice: str = DEFAULT_VOICE,
        voices_dir: str = DEFAULT_VOICES_DIR,
        *,
        length_scale: float = 1.0,
        volume: float = 1.0,
        use_cuda: bool = False,
    ) -> None:
        self.voice = voice
        self.voices_dir = Path(voices_dir).expanduser()
        self.model_path = self.voices_dir / voice / f"{voice}.onnx"
        self.length_scale = length_scale
        self.volume = volume
        self.use_cuda = use_cuda
        self._voice = None

    def is_ready(self) -> bool:
        return self.model_path.exists()

    def _load(self):
        if self._voice is None:
            if not self.model_path.exists():
                raise FileNotFoundError(
                    f"no encuentro la voz de Piper en {self.model_path}. "
                    "Ejecuta scripts/install-piper.sh"
                )
            from piper import PiperVoice

            self._voice = PiperVoice.load(str(self.model_path), use_cuda=self.use_cuda)
        return self._voice

    def warmup(self) -> None:  # evita el coste de carga en la primera frase
        self._load()

    def synthesize(self, text: str, language: str = "es") -> AudioOut:  # noqa: ARG002
        from piper import SynthesisConfig

        voice = self._load()
        config = SynthesisConfig(length_scale=self.length_scale, volume=self.volume)
        parts: list[np.ndarray] = []
        rate = 22050
        for chunk in voice.synthesize(text, config):
            rate = int(chunk.sample_rate)
            parts.append(np.asarray(chunk.audio_float_array, dtype=np.float32).reshape(-1))
        audio = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
        return AudioOut(audio=audio, sample_rate=rate)

    def close(self) -> None:
        self._voice = None
