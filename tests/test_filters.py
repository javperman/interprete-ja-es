"""Pruebas de los filtros de texto (alucinaciones del STT y eco).

Salen de la prueba real del 2026-11-13: el intérprete traducía «cualquier
sonido». Dos causas: Whisper **inventa** frases con ruido/silencio y los
auriculares devuelven la voz sintetizada al micrófono (se traducía a sí mismo).
"""

from __future__ import annotations

import pytest

from interprete.filters import (
    EchoGuard,
    TurnFilters,
    is_hallucination,
    normalize,
)

# ---------------------------------------------------------------- normalizar
def test_normalize_quita_puntuacion_y_espacios():
    assert normalize("  ¡Hola,   mundo!  ") == "holamundo"
    assert normalize("お世話になっております。") == "お世話になっております"
    assert normalize("Hello, World! ♪") == "helloworld"


# ------------------------------------------------------------ alucinaciones
@pytest.mark.parametrize(
    "texto",
    [
        "お待ちしております",
        "お待ちしております。",
        " ご視聴ありがとうございました ",
        "チャンネル登録よろしくお願いします",
        "Subtítulos realizados por la comunidad de Amara.org",
        "Gracias por ver el video!",
        "Thanks for watching!",
        "Please subscribe",
    ],
)
def test_detecta_frases_inventadas_conocidas(texto):
    assert is_hallucination(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "こんにちは。本日の打ち合わせを始めます。",
        "¿Puedes repetir eso, por favor?",
        "No lo capto bien.",
        "Sí",
        "はい",
        "Vale, pero voy a hacer una frase larga para probar.",
        "いやいややばいやばいやばいやばいだめだめだめだめ",  # habla real, repetitiva
    ],
)
def test_no_descarta_habla_normal(texto):
    assert not is_hallucination(texto)


def test_texto_vacio_es_alucinacion():
    assert is_hallucination("")
    assert is_hallucination("   ")


def test_lista_negra_extra():
    assert is_hallucination("hola, probando", extra=["hola, probando"])
    assert not is_hallucination("hola, probando")


# -------------------------------------------------------------------- eco
def test_el_eco_del_propio_interprete_se_detecta():
    guard = EchoGuard()
    guard.record("En cuanto al ensayo, no hay problema.", when=100.0)
    # El micrófono recoge la traducción que suena en los auriculares:
    assert guard.is_echo("En cuanto al ensayo, no hay problema", when=103.0)
    assert guard.is_echo("en cuanto al ensayo no hay problema!", when=105.0)
    # Variante parcial (se pierde el final por el corte del micro):
    assert guard.is_echo("En cuanto al ensayo, no hay", when=104.0)


def test_el_eco_caduca():
    guard = EchoGuard(window_s=10.0)
    guard.record("En cuanto al ensayo, no hay problema.", when=100.0)
    assert not guard.is_echo("En cuanto al ensayo, no hay problema.", when=115.0)


def test_frases_cortas_no_se_confunden_con_eco():
    """«Sí» o «はい» deben pasar: son respuestas legítimas."""
    guard = EchoGuard()
    guard.record("Sí", when=100.0)
    guard.record("はい", when=100.0)
    assert not guard.is_echo("Sí", when=101.0)
    assert not guard.is_echo("はい", when=101.0)


def test_habla_distinta_no_es_eco():
    guard = EchoGuard()
    guard.record("En cuanto al ensayo, no hay problema.", when=100.0)
    assert not guard.is_echo("Voy a hablar del presupuesto del próximo trimestre", when=101.0)


def test_el_guardia_no_crece_sin_limite():
    guard = EchoGuard(min_chars=4)
    for i in range(200):
        guard.record(f"frase numero {i} de prueba", when=100.0 + i)
    assert len(guard._dicho) <= 64


# --------------------------------------------------------- TurnFilters
def test_turn_filters_duración_mínima():
    f = TurnFilters(min_speech_ms=350)
    assert f.is_too_short(0.2) is True  # un golpe en la mesa
    assert f.is_too_short(0.5) is False
    assert TurnFilters(min_speech_ms=0).is_too_short(0.01) is False


def test_turn_filters_agrupa_todo():
    guard = EchoGuard()
    f = TurnFilters(blocklist=["hola, probando"], min_speech_ms=300, echo_guard=guard)
    assert f.is_too_short(0.1)
    assert f.is_blocked_text("お待ちしております")
    assert f.is_blocked_text("hola, probando")
    assert not f.is_blocked_text("Buenos días a todos")

    f.remember_spoken("Vamos a empezar con el primer punto del día")  # ahora mismo
    assert guard.is_echo("Vamos a empezar con el primer punto del día", when=52.0)
    assert f.is_echo("Vamos a empezar con el primer punto del día")


def test_sin_echo_guard_no_filtra_eco():
    f = TurnFilters(echo_guard=None)
    f.remember_spoken("da igual lo que diga")
    assert f.is_echo("da igual lo que diga") is False


def test_hallucination_filter_se_puede_desactivar():
    f = TurnFilters(hallucination_filter=False)
    assert f.is_blocked_text("お待ちしております") is False


# ------------------------------------------------- el pipeline de verdad
def _segmento(ms: int = 800):
    import numpy as np

    from interprete.vad.base import SpeechSegment

    n = int(16000 * ms / 1000)
    return SpeechSegment(
        audio=np.full(n, 0.3, dtype=np.float32),
        sample_rate=16000,
        t_start=0.0,
        t_end=ms / 1000,
    )


class _SttFalso:
    def __init__(self, texto: str = "¿Puedes repetir eso, por favor?") -> None:
        self.texto = texto

    def transcribe(self, audio, sample_rate, language=None) -> str:
        return self.texto

    def transcribe_detailed(self, audio, sample_rate, language=None):
        return self.texto, "ja"


class _TraductorFalso:
    def __init__(self) -> None:
        self.llamadas = 0

    async def translate_stream(self, text, **kwargs):
        self.llamadas += 1
        yield "¿Puedes repetirlo?"

    async def aclose(self) -> None:
        pass


def _pipeline(filtros: TurnFilters, texto: str = "¿Puedes repetir eso, por favor?"):
    from interprete.pipeline import ListenPipeline

    traductor = _TraductorFalso()
    pipeline = ListenPipeline(
        stt=_SttFalso(texto),
        translator=traductor,
        segmenter=object(),
        filters=filtros,
    )
    return pipeline, traductor


def test_el_pipeline_descarta_sonidos_demasiado_cortos():
    import asyncio

    pipeline, traductor = _pipeline(TurnFilters(min_speech_ms=350))
    resultado = asyncio.run(pipeline.process(_segmento(100)))  # 0,1 s: un golpe
    assert resultado is None
    assert pipeline.filtered == 1
    assert traductor.llamadas == 0


def test_el_pipeline_descarta_frases_inventadas():
    import asyncio

    pipeline, traductor = _pipeline(TurnFilters(hallucination_filter=True), texto="お待ちしております")
    assert asyncio.run(pipeline.process(_segmento(900))) is None
    assert pipeline.filtered == 1
    assert traductor.llamadas == 0


def test_el_pipeline_descarta_el_eco_y_lo_cuenta():
    import asyncio

    guard = EchoGuard()
    filtros = TurnFilters(echo_guard=guard)
    # El intérprete acaba de decir esto y el micro lo recoge otra vez:
    guard.record("En cuanto al ensayo, no hay problema.")
    pipeline, traductor = _pipeline(
        filtros, texto="En cuanto al ensayo, no hay problema."
    )
    assert asyncio.run(pipeline.process(_segmento(900))) is None
    assert pipeline.filtered == 1
    assert pipeline.echos == 1
    assert traductor.llamadas == 0


def test_el_pipeline_deja_pasar_habla_normal():
    import asyncio

    pipeline, traductor = _pipeline(TurnFilters(echo_guard=EchoGuard()))
    resultado = asyncio.run(pipeline.process(_segmento(900)))
    assert resultado is not None
    assert pipeline.filtered == 0
    assert traductor.llamadas == 1
