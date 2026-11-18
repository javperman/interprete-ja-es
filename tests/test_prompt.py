"""Pruebas del prompt de intérprete (función pura)."""

from __future__ import annotations

from interprete.mt.prompt import build_messages


def test_basic_shape():
    msgs = build_messages("こんにちは", source="ja", target="es")
    assert msgs[0]["role"] == "system"
    assert "intérprete" in msgs[0]["content"]
    assert "japonés" in msgs[0]["content"]
    assert "español" in msgs[0]["content"]
    assert msgs[-1] == {"role": "user", "content": "こんにちは"}


def test_context_limited_to_five():
    ctx = [f"frase {i}" for i in range(10)]
    msgs = build_messages("nueva", source="es", target="ja", context=ctx)
    # system + 5 de contexto + user
    assert len(msgs) == 7
    assert msgs[1]["content"] == "frase 5"
    assert msgs[5]["content"] == "frase 9"


def test_glossary_included():
    msgs = build_messages("hola", source="es", target="ja", glossary=["API", "onboarding"])
    assert "API" in msgs[0]["content"]
    assert "onboarding" in msgs[0]["content"]
