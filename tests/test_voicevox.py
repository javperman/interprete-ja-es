"""Pruebas de VOICEVOX: parámetros de prosodia (unitarias) e integración real."""

from __future__ import annotations

import io

import httpx
import numpy as np
import pytest
import soundfile as sf


# --------------------------------------------------------------------------
# Unitarias: se comprueba que la prosodia llega al motor (sin llamarlo).
# --------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, *, payload=None, content: bytes = b"") -> None:
        self._payload = payload
        self.content = content
        self.status_code = 200

    def json(self):
        return self._payload


class _FakeClient:
    """Cliente falso que apunta lo que se manda a ``/synthesis``."""

    def __init__(self, *args, **kwargs) -> None:
        self.enviados: list[dict] = []

    def get(self, path, **_kwargs):
        return _FakeResponse(payload={"version": "test"})

    def post(self, path, params=None, json=None):  # noqa: A002 - firma de httpx
        if path == "/audio_query":
            return _FakeResponse(
                payload={"speedScale": 1.0, "intonationScale": 1.0, "pitchScale": 0.0}
            )
        self.enviados.append(dict(json or {}))
        buffer = io.BytesIO()
        sf.write(buffer, np.zeros(240, dtype=np.float32), 24000, format="WAV")
        return _FakeResponse(content=buffer.getvalue())

    def close(self):
        pass


def test_prosodia_se_envia_al_motor(monkeypatch):
    from interprete.tts import VoicevoxTts

    fake = _FakeClient()
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: fake)

    tts = VoicevoxTts(url="http://x", speaker=101, speed_scale=0.95, intonation_scale=0.8)
    out = tts.synthesize("こんにちは", "ja")

    assert out.sample_rate == 24000
    assert fake.enviados, "no se llegó a llamar a /synthesis"
    enviado = fake.enviados[0]
    assert enviado["speedScale"] == 0.95
    assert enviado["intonationScale"] == 0.8
    assert enviado["pitchScale"] == 0.0


def test_la_fabrica_pasa_los_ajustes():
    from interprete.config import TtsEngineConfig
    from interprete.tts.factory import build_tts

    cfg = TtsEngineConfig(engine="voicevox", speaker=101, intonation_scale=0.75, pitch_scale=-0.1)
    tts = build_tts(cfg)
    try:
        assert tts.speaker == 101
        assert tts.intonation_scale == 0.75
        assert tts.pitch_scale == -0.1
    finally:
        tts.close()


# --------------------------------------------------------------------------
# Integración: solo si el motor está levantado en :50021.
# --------------------------------------------------------------------------
URL = "http://127.0.0.1:50021"
TEXTO = "お世話になっております。本日の打ち合わせについてご説明します。"


def _up() -> bool:
    try:
        return httpx.get(f"{URL}/version", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _up(), reason="VOICEVOX no está en marcha en :50021")


def test_synthesize_japanese():
    from interprete.tts import VoicevoxTts

    tts = VoicevoxTts(url=URL, speaker=101)
    assert tts.is_ready()
    out = tts.synthesize("こんにちは。テストです。", language="ja")
    assert out.sample_rate == 24000
    assert out.audio.size > 24000  # al menos ~1 s
    assert abs(out.audio).max() > 0.01
    tts.close()


def _perfil_voz(audio: np.ndarray, sr: int) -> tuple[float, float, float]:
    """(F0 mediana, rango de entonación en semitonos, periodicidad media).

    La **periodicidad** (pico de autocorrelación, 0–1) distingue una voz clara de
    una susurrante: fue la métrica que faltó cuando se eligió una voz que sonaba
    «íntima» (grave, lenta y con aire).
    """
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    ventana, salto = int(0.04 * sr), int(0.01 * sr)
    tonos, periodos = [], []
    for inicio in range(0, len(audio) - ventana, salto):
        marco = audio[inicio : inicio + ventana]
        if float(np.sqrt(np.mean(marco**2))) < 0.01:
            continue
        marco = marco - marco.mean()
        corr = np.correlate(marco, marco, mode="full")[len(marco) - 1 :]
        if corr[0] <= 0:
            continue
        corr = corr / corr[0]
        minimo, maximo = int(sr / 300), min(int(sr / 60), len(corr) - 1)
        if maximo <= minimo:
            continue
        pico = int(np.argmax(corr[minimo:maximo])) + minimo
        if corr[pico] < 0.25:
            continue
        tonos.append(sr / pico)
        periodos.append(float(corr[pico]))
    if len(tonos) < 10:
        return 0.0, 0.0, 0.0
    serie = np.array(tonos)
    semitonos = 12 * np.log2(serie / np.median(serie))
    rango = float(np.percentile(semitonos, 90) - np.percentile(semitonos, 10))
    return float(np.median(serie)), rango, float(np.mean(periodos))


def _rango_entonacion(audio: np.ndarray, sr: int) -> float:
    """Rango de tono en semitonos (p10–p90): menos = melodía más plana.

    Se usa el rango y no la desviación típica porque esta última es ruidosa en
    voces ya planas; el rango se comporta de forma monótona con ``intonationScale``.
    """
    return _perfil_voz(audio, sr)[1]


def test_la_voz_por_defecto_no_es_susurrante_ni_grave():
    """Regresión de la queja real: la voz por defecto sonaba «íntima».

    離途 (シリアス) tenía 93 Hz y la **peor** periodicidad de todas (0,57), que es
    el perfil de una voz susurrante. La voz por defecto debe ser clara, de tono
    medio y con ritmo normal, no grave-lenta-con-aire.
    """
    from interprete.config import Config
    from interprete.tts import VoicevoxTts

    cfg = Config().tts_ja
    tts = VoicevoxTts(url=URL, speaker=cfg.speaker, intonation_scale=cfg.intonation_scale)
    susurrante = VoicevoxTts(url=URL, speaker=101, intonation_scale=cfg.intonation_scale)
    try:
        audio = tts.synthesize(TEXTO, "ja").audio
        f0, rango, periodicidad = _perfil_voz(audio, 24000)
        _, _, period_susurrante = _perfil_voz(susurrante.synthesize(TEXTO, "ja").audio, 24000)
    finally:
        tts.close()
        susurrante.close()

    assert 120 <= f0 <= 190, f"el tono por defecto ({f0:.0f} Hz) es demasiado grave/agudo"
    assert periodicidad > period_susurrante, "la voz por defecto es más susurrante que la descartada"
    assert periodicidad > 0.60, f"voz poco clara (periodicidad {periodicidad:.3f})"
    assert rango < 9.0, f"melodía demasiado teatral ({rango:.2f} semitonos)"


def test_la_voz_por_defecto_es_agil_y_no_lenta():
    """Una voz lenta suena sensual; el ritmo debe ser de conversación normal."""
    from interprete.config import Config
    from interprete.tts import VoicevoxTts

    cfg = Config().tts_ja
    tts = VoicevoxTts(url=URL, speaker=cfg.speaker, speed_scale=cfg.speed_scale)
    try:
        ms_por_car = len(tts.synthesize(TEXTO, "ja").audio) / 24000 / len(TEXTO) * 1000
    finally:
        tts.close()
    assert ms_por_car < 150, f"la voz va lenta ({ms_por_car:.0f} ms/carácter)"


def test_las_voces_recomendadas_estan_probadas():
    """La lista ★ de la app no debe incluir voces susurrantes ni tonos extremos."""
    from interprete.gui.voices import EVITAR_JA, RECOMENDADAS_JA
    from interprete.tts import VoicevoxTts

    assert 11 in RECOMENDADAS_JA, "debe estar la voz por defecto"
    assert 101 not in RECOMENDADAS_JA
    assert 101 in EVITAR_JA

    for style_id in RECOMENDADAS_JA:
        tts = VoicevoxTts(url=URL, speaker=style_id)
        try:
            f0, rango, periodicidad = _perfil_voz(tts.synthesize(TEXTO, "ja").audio, 24000)
        finally:
            tts.close()
        assert 120 <= f0 <= 210, f"estilo {style_id}: tono fuera de rango ({f0:.0f} Hz)"
        assert periodicidad > 0.60, f"estilo {style_id}: voz poco clara ({periodicidad:.3f})"
        assert rango < 11.0, f"estilo {style_id}: melodía teatral ({rango:.2f})"


def test_bajar_la_entonacion_aplana_la_melodia():
    """La razón de ser del ajuste: menos rango de tono = menos «anime»."""
    from interprete.tts import VoicevoxTts

    sobria = VoicevoxTts(url=URL, speaker=101, intonation_scale=0.5)
    exagerada = VoicevoxTts(url=URL, speaker=101, intonation_scale=1.5)
    try:
        rango_sobrio = _rango_entonacion(sobria.synthesize(TEXTO, "ja").audio, 24000)
        rango_exagerado = _rango_entonacion(exagerada.synthesize(TEXTO, "ja").audio, 24000)
    finally:
        sobria.close()
        exagerada.close()
    # Medido en el la máquina de pruebas: 3,0 vs 4,7 semitonos de rango.
    assert rango_sobrio < rango_exagerado
    assert rango_sobrio < 0.8 * rango_exagerado


def test_la_voz_por_defecto_es_mas_sobria_que_la_anterior():
    """離途 (シリアス) debe aplanar mucho frente a 青山龍星 con la misma entonación."""
    from interprete.tts import VoicevoxTts

    nueva = VoicevoxTts(url=URL, speaker=101, intonation_scale=1.0)
    vieja = VoicevoxTts(url=URL, speaker=13, intonation_scale=1.0)
    try:
        rango_nueva = _rango_entonacion(nueva.synthesize(TEXTO, "ja").audio, 24000)
        rango_vieja = _rango_entonacion(vieja.synthesize(TEXTO, "ja").audio, 24000)
    finally:
        nueva.close()
        vieja.close()
    # Medido en el la máquina de pruebas: 3,6 vs 11,1 semitonos.
    assert rango_nueva < 0.6 * rango_vieja
