"""Pruebas de las utilidades de texto de la UI (ancho CJK, recorte, ajuste)."""

from __future__ import annotations

from interprete.ui.text import display_width, fit, pad, truncate, wrap


def test_display_width_ascii_and_cjk():
    assert display_width("abc") == 3
    # 「こんにちは」 = 5 caracteres de doble ancho
    assert display_width("こんにちは") == 10
    assert display_width("あa") == 3


def test_truncate_respects_cjk_width():
    out = truncate("こんにちは世界", 7)
    assert display_width(out) <= 7
    assert out.endswith("…")
    # cabe justo: no recorta
    assert truncate("こんにちは", 10) == "こんにちは"


def test_truncate_zero_or_negative():
    assert truncate("hola", 0) == ""
    assert truncate("hola", -3) == ""


def test_wrap_splits_by_width_without_spaces():
    lines = wrap("こんにちは世界", 4)
    assert all(display_width(line) <= 4 for line in lines)
    assert "".join(lines) == "こんにちは世界"
    assert len(lines) == 4  # 2 anchos por línea: 2+2+2+1 caracteres


def test_wrap_keeps_newlines():
    lines = wrap("uno\ndos", 10)
    assert lines == ["uno", "dos"]


def test_pad_alignments():
    assert pad("ab", 5) == "ab   "
    assert pad("ab", 5, align="right") == "   ab"
    assert pad("ab", 5, align="center") == " ab  "
    assert pad("あ", 4, align="right") == "  あ"


def test_fit_always_exact_width():
    for text, width in (("hola", 6), ("こんにちは", 6), ("", 3), ("muy largo de verdad", 5)):
        assert display_width(fit(text, width)) == width
