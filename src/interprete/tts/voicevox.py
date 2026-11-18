"""TTS japonés con VOICEVOX Engine (HTTP local).

El motor corre como servicio de usuario en ``127.0.0.1:50021`` (build CPU, no
consume VRAM). Se instala con ``scripts/install-voicevox.sh``.
"""

from __future__ import annotations

import io

import httpx
import numpy as np
import soundfile as sf

from .base import AudioOut, TtsEngine


class VoicevoxTts(TtsEngine):
    def __init__(
        self,
        url: str = "http://127.0.0.1:50021",
        speaker: int = 101,
        speed_scale: float = 1.0,
        intonation_scale: float = 0.80,
        pitch_scale: float = 0.0,
        volume_scale: float = 1.0,
        timeout: float = 30.0,
    ) -> None:
        self._client = httpx.Client(base_url=url, timeout=timeout)
        self.speaker = speaker
        # Prosodia: bajar ``intonation_scale`` aplana la melodía y suena mucho
        # menos a anime (medido: 4,2 semitonos de variación → 2,3).
        self.speed_scale = speed_scale
        self.intonation_scale = intonation_scale
        self.pitch_scale = pitch_scale
        self.volume_scale = volume_scale

    def is_ready(self) -> bool:
        try:
            return self._client.get("/version").status_code == 200
        except httpx.HTTPError:
            return False

    def synthesize(self, text: str, language: str = "ja") -> AudioOut:  # noqa: ARG002
        query = self._client.post(
            "/audio_query", params={"text": text, "speaker": self.speaker}
        ).json()
        query["speedScale"] = self.speed_scale
        query["intonationScale"] = self.intonation_scale
        query["pitchScale"] = self.pitch_scale
        query["volumeScale"] = self.volume_scale
        wav = self._client.post(
            "/synthesis", params={"speaker": self.speaker}, json=query
        ).content
        data, sr = sf.read(io.BytesIO(wav), dtype="float32", always_2d=False)
        return AudioOut(audio=np.asarray(data, dtype=np.float32), sample_rate=int(sr))

    def close(self) -> None:
        self._client.close()
