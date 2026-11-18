"""Pruebas puras del proveedor Vertex (sin red ni credenciales)."""

from __future__ import annotations

import json

from interprete.mt.vertex import _token_from_stream_event, build_vertex_body


def test_body_shape():
    body = build_vertex_body("こんにちは", source="ja", target="es")
    assert body["contents"][0]["role"] == "user"
    assert body["contents"][0]["parts"][0]["text"] == "こんにちは"
    assert "japonés" in body["systemInstruction"]["parts"][0]["text"]
    assert body["generationConfig"]["maxOutputTokens"] == 1000


def test_thinking_level_optional():
    assert "thinkingConfig" not in build_vertex_body("x", source="ja", target="es")[
        "generationConfig"
    ]
    body = build_vertex_body("x", source="ja", target="es", thinking_level="low")
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}


def test_context_and_glossary_go_to_system():
    body = build_vertex_body(
        "nueva", source="es", target="ja", context=["uno", "dos"], glossary=["API"]
    )
    system = body["systemInstruction"]["parts"][0]["text"]
    assert "API" in system
    assert "uno / dos" in system


def test_parse_stream_event():
    ev = json.dumps({"candidates": [{"content": {"parts": [{"text": "Hola"}]}}]})
    assert _token_from_stream_event(ev) == "Hola"
    assert _token_from_stream_event("no-json") is None
    assert _token_from_stream_event("{}") is None
