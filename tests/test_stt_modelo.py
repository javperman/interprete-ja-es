"""Pruebas de la carga del modelo de voz: reutilización y reserva a CPU.

Salen del fallo real «RuntimeError: CUDA failed with error out of memory»: al
iniciar una segunda sesión en el mismo proceso se cargaba **otro** modelo sin
soltar el anterior (la GPU del equipo tiene 4 GB y el navegador ocupa parte).
"""

from __future__ import annotations

import pytest

from interprete.stt import faster_whisper as fw


class _ModeloFalso:
    def __init__(self, model: str, device: str = "cuda", compute_type: str = "", **kwargs) -> None:
        if device == "cuda" and model == "modelo-sin-gpu":
            raise RuntimeError("CUDA failed with error out of memory")
        self.model = model
        self.device = device
        self.compute_type = compute_type


@pytest.fixture(autouse=True)
def _limpia_cache(monkeypatch):
    fw.liberar_modelos()
    monkeypatch.setattr("faster_whisper.WhisperModel", _ModeloFalso)
    yield
    fw.liberar_modelos()


def test_el_mismo_modelo_solo_se_carga_una_vez():
    primero, dispositivo = fw.cargar_modelo("modelo", "cuda", "int8_float16")
    segundo, _ = fw.cargar_modelo("modelo", "cuda", "int8_float16")
    assert dispositivo == "cuda"
    assert primero is segundo  # reutilizado, no una segunda copia
    assert len(fw.modelos_cargados()) == 1


def test_auto_usa_cuda_si_se_puede():
    modelo, dispositivo = fw.cargar_modelo("modelo", "auto", "int8_float16")
    assert dispositivo == "cuda"
    assert modelo.device == "cuda"
    assert modelo.compute_type == "int8_float16"


def test_auto_cae_a_cpu_si_la_gpu_no_tiene_memoria():
    modelo, dispositivo = fw.cargar_modelo("modelo-sin-gpu", "auto", "int8_float16")
    assert dispositivo == "cpu"
    assert modelo.device == "cpu"
    assert modelo.compute_type == "int8"  # la CPU no admite int8_float16


def test_auto_reutiliza_lo_ya_cargado():
    primero, _ = fw.cargar_modelo("modelo", "auto", "int8_float16")
    segundo, dispositivo = fw.cargar_modelo("modelo", "auto", "int8_float16")
    assert segundo is primero
    assert dispositivo == "cuda"
    assert len(fw.modelos_cargados()) == 1


def test_cuda_explicito_no_cae_a_cpu():
    """Si el usuario pide CUDA y no cabe, debe fallar (no mentir con la CPU)."""
    with pytest.raises(RuntimeError, match="out of memory"):
        fw.cargar_modelo("modelo-sin-gpu", "cuda", "int8_float16")


def test_liberar_modelos_vacia_la_memoria():
    fw.cargar_modelo("modelo", "auto", "int8_float16")
    assert fw.modelos_cargados()
    assert fw.liberar_modelos() == 1
    assert fw.modelos_cargados() == []
    assert fw.liberar_modelos() == 0


def test_el_stt_reutiliza_el_modelo_entre_sesiones():
    """Dos sesiones seguidas en el mismo proceso (lo que fallaba con OOM)."""
    a = fw.FasterWhisperStt(model="modelo", device="auto", compute_type="int8_float16")
    b = fw.FasterWhisperStt(model="modelo", device="auto", compute_type="int8_float16")
    assert a.device == "cuda"
    assert a._model is b._model
    # Cerrar una sesión NO descarga el modelo (se comparte).
    a.close()
    assert fw.modelos_cargados()
