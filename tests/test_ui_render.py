"""Pruebas de la maquetación de la TUI (pura, sin terminal)."""

from __future__ import annotations

from interprete.latency import TurnTiming
from interprete.pipeline.listen import TurnResult
from interprete.ui.render import fmt_elapsed, render, render_rows, subtitles_rows
from interprete.ui.state import AppState, ChannelState
from interprete.ui.text import display_width


def _res(source: str, target: str):
    timing = TurnTiming(spans={"stt_ms": 400, "first_token_ms": 1200}, total_ms=1400)
    return TurnResult("ja", "es", source, target, 2.0, timing)


def _state() -> AppState:
    state = AppState(
        mode="run",
        provider="vertex",
        model="gemini-3.5-flash-lite",
        privacy="el texto sale a Google",
    )
    listen = ChannelState(
        key="listen", name="JA → ES   (tú oyes español)", source_lang="ja", target_lang="es"
    )
    listen.add(_res("お世話になっております。本日の打ち合わせを始めます。", "Buenos días. Empecemos la reunión de hoy."))
    listen.add(_res("ありがとうございます", "Muchas gracias"))
    speak = ChannelState(
        key="speak", name="ES → JA   (ellos oyen japonés)", source_lang="es", target_lang="ja"
    )
    speak.add(_res("Hola, encantado", "はじめまして、よろしくお願いします"))
    state.channels = [listen, speak]
    return state


def test_render_exact_dimensions():
    state = _state()
    for width, height in ((100, 30), (80, 24), (60, 16), (40, 8), (200, 50)):
        rows = render_rows(state, width, height)
        assert len(rows) == height, (width, height)
        for r in rows:
            assert display_width(r.text) == width, (width, height, repr(r.text))


def test_render_plain_has_no_ansi():
    text = "\n".join(render(_state(), 100, 30))
    assert "\x1b" not in text
    assert "Muchas gracias" in text


def test_two_columns_when_wide():
    text = "\n".join(render(_state(), 120, 30))
    assert "│" in text
    assert "JA → ES" in text and "ES → JA" in text


def test_single_column_when_narrow():
    text = "\n".join(render(_state(), 60, 20))
    assert "│" not in text
    assert "JA → ES" in text


def test_single_channel_mode():
    state = AppState(mode="listen", provider="vertex")
    ch = ChannelState(key="listen", name="JA → ES", source_lang="ja", target_lang="es")
    ch.add(_res("こんにちは", "Hola"))
    state.channels = [ch]
    rows = render_rows(state, 80, 20)
    assert len(rows) == 20
    assert "│" not in "\n".join(r.text for r in rows)


def test_help_overlay():
    text = "\n".join(render(_state(), 100, 30, show_help=True))
    assert "Ayuda" in text
    assert "salir" in text


def test_tts_off_marker():
    state = _state()
    state.channel("listen").tts_on = False
    text = "\n".join(render(state, 120, 30))
    assert "voz OFF" in text


def test_subtitles_show_last_translation():
    state = _state()
    rows = subtitles_rows(state, 100, 24)
    assert len(rows) == 24
    joined = "\n".join(r.text for r in rows)
    assert "Muchas gracias" in joined  # última traducción del canal de escucha


def test_fmt_elapsed():
    assert fmt_elapsed(0) == "00:00"
    assert fmt_elapsed(61) == "01:01"
    assert fmt_elapsed(3661) == "1:01:01"


def test_render_does_not_mutate_state():
    state = _state()
    before = [line.target for line in state.channel("listen").lines]
    render_rows(state, 100, 30)
    after = [line.target for line in state.channel("listen").lines]
    assert before == after
