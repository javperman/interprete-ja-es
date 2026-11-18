"""Segmentación por frases a partir de un modelo de VAD.

La lógica de segmentación es **pura** (no depende de PipeWire ni del modelo
concreto): recibe fotogramas y emite ``SpeechSegment`` al detectar el final de
una frase. Se prueba con un modelo de prueba en ``tests/``.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class VadModel(Protocol):
    """Modelo de VAD: probabilidad de voz de un fotograma (float32 mono)."""

    def speech_probability(self, frame: np.ndarray) -> float: ...


# Alias histórico de la propuesta inicial.
Probe = VadModel


@dataclass(slots=True)
class SpeechSegment:
    audio: np.ndarray
    sample_rate: int
    t_start: float
    t_end: float

    @property
    def duration(self) -> float:
        return len(self.audio) / self.sample_rate


class Segmenter:
    """Convierte un flujo de fotogramas en segmentos de una frase.

    Emite un ``SpeechSegment`` cuando la voz cesa durante ``min_silence_ms`` o se
    alcanza ``max_speech_s``.
    """

    def __init__(
        self,
        model: VadModel,
        *,
        sample_rate: int = 16000,
        threshold: float = 0.5,
        min_silence_ms: int = 500,
        speech_pad_ms: int = 200,
        pre_roll_ms: int = 300,
        max_speech_s: float = 20.0,
    ) -> None:
        self.model = model
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.min_silence_ms = min_silence_ms
        self.speech_pad_ms = speech_pad_ms
        self.max_speech_s = max_speech_s

        self._pre: deque[np.ndarray] = deque()
        self._pre_max_ms = pre_roll_ms
        self._pre_ms = 0.0
        self._buf: list[np.ndarray] = []
        self._buf_ms = 0.0
        self._silence_ms = 0.0
        self._in_speech = False
        self._t = 0.0  # tiempo consumido, en segundos
        self._seg_start = 0.0

    # ------------------------------------------------------------------
    def push(self, frame: np.ndarray) -> SpeechSegment | None:
        frame = np.asarray(frame, dtype=np.float32).reshape(-1)
        frame_ms = 1000.0 * len(frame) / self.sample_rate
        is_speech = self.model.speech_probability(frame) >= self.threshold
        segment: SpeechSegment | None = None

        if not self._in_speech:
            if is_speech:
                self._in_speech = True
                self._seg_start = self._t - self._pre_ms / 1000.0
                self._buf = list(self._pre)
                self._buf_ms = self._pre_ms
                self._append(frame, frame_ms)
                self._silence_ms = 0.0
            else:
                self._push_pre(frame, frame_ms)
        else:
            self._append(frame, frame_ms)
            if is_speech:
                self._silence_ms = 0.0
            else:
                self._silence_ms += frame_ms
                if self._silence_ms >= self.min_silence_ms:
                    segment = self._emit()
            if segment is None and self._buf_ms / 1000.0 >= self.max_speech_s:
                segment = self._emit()

        self._t += frame_ms / 1000.0
        return segment

    def flush(self) -> SpeechSegment | None:
        """Fuerza el cierre del segmento en curso (p. ej. al parar)."""
        return self._emit() if self._in_speech else None

    # ------------------------------------------------------------------
    def _append(self, frame: np.ndarray, frame_ms: float) -> None:
        self._buf.append(frame)
        self._buf_ms += frame_ms

    def _push_pre(self, frame: np.ndarray, frame_ms: float) -> None:
        self._pre.append(frame)
        self._pre_ms += frame_ms
        while self._pre and self._pre_ms - frame_ms >= self._pre_max_ms:
            old = self._pre.popleft()
            self._pre_ms -= 1000.0 * len(old) / self.sample_rate

    def _emit(self) -> SpeechSegment | None:
        if not self._buf:
            self._reset()
            return None
        audio = np.concatenate(self._buf).astype(np.float32)
        # recorta el silencio final, dejando speech_pad_ms
        keep_tail_ms = self.speech_pad_ms
        drop_ms = max(0.0, self._silence_ms - keep_tail_ms)
        if drop_ms > 0:
            drop = int(self.sample_rate * drop_ms / 1000.0)
            if drop < len(audio):
                audio = audio[:-drop]
        t_end = self._t
        seg = SpeechSegment(
            audio=audio, sample_rate=self.sample_rate, t_start=self._seg_start, t_end=t_end
        )
        self._reset()
        return seg

    def _reset(self) -> None:
        self._in_speech = False
        self._buf = []
        self._buf_ms = 0.0
        self._silence_ms = 0.0
        self._pre.clear()
        self._pre_ms = 0.0
