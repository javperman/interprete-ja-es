"""VAD Silero usando el modelo ONNX con onnxruntime.

Se evita a propósito el paquete ``silero-vad`` (que arrastra ``torch`` y fija
``torchaudio<2.10``, roto en Python 3.14). Aquí se ejecuta el modelo ONNX
directamente.

Firma del modelo (v5):
    input  [batch, samples]     samples = 512 a 16 kHz
    state  [2, batch, 128]
    sr     scalar int64
  -> output [batch, 1] probabilidad de voz
     stateN [2, batch, 128]
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import onnxruntime as ort

DEFAULT_MODEL = Path(
    os.environ.get("SILERO_VAD_ONNX", Path.home() / ".cache/interprete/silero_vad.onnx")
)

# Fotogramas válidos por frecuencia (requisito de Silero v5).
FRAME_SAMPLES = {8000: 256, 16000: 512}
CONTEXT_SAMPLES = {8000: 32, 16000: 64}


class SileroOnnxVad:
    """Modelo de VAD compatible con ``vad.base.VadModel``."""

    def __init__(self, model_path: str | Path | None = None, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        if sample_rate not in FRAME_SAMPLES:
            raise ValueError(f"frecuencia no soportada por Silero: {sample_rate}")
        self.frame_samples = FRAME_SAMPLES[sample_rate]
        self.context_samples = CONTEXT_SAMPLES[sample_rate]
        path = Path(model_path) if model_path else DEFAULT_MODEL
        if not path.exists():
            raise FileNotFoundError(f"no encuentro el modelo Silero ONNX en {path}")
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self._sess = ort.InferenceSession(
            str(path), providers=["CPUExecutionProvider"], sess_options=opts
        )
        self.reset()

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros((1, self.context_samples), dtype=np.float32)

    def speech_probability(self, frame: np.ndarray) -> float:
        frame = np.asarray(frame, dtype=np.float32).reshape(-1)
        if frame.shape[0] != self.frame_samples:
            raise ValueError(
                f"el fotograma debe tener {self.frame_samples} muestras, no {frame.shape[0]}"
            )
        # El modelo espera contexto + fotograma (64 + 512 a 16 kHz).
        x = np.concatenate([self._context, frame.reshape(1, -1)], axis=1)
        out, self._state = self._sess.run(
            None, {"input": x, "state": self._state, "sr": np.array(self.sample_rate, np.int64)}
        )
        self._context = x[:, -self.context_samples :]
        return float(out[0, 0])
