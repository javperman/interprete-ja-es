"""Pruebas de la fábrica de traductores."""

from __future__ import annotations

import asyncio

import pytest

from interprete.config import MtConfig
from interprete.mt import PROVIDERS, build_translator


def _close(t):
    asyncio.run(t.aclose())


def test_presets():
    assert "deepseek" in PROVIDERS
    assert "gemini" in PROVIDERS
    assert PROVIDERS["gemini"]["api_key_env"] == "GEMINI_API_KEY"


def test_build_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "clave-de-prueba")
    t = build_translator(MtConfig(provider="gemini"))
    assert t.model == "gemini-3.5-flash"
    assert t.extra_body == {}  # no aplica 'thinking'
    _close(t)


def test_build_deepseek_disables_thinking(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "clave-de-prueba")
    t = build_translator(MtConfig(provider="deepseek"))
    assert t.extra_body == {"thinking": {"type": "disabled"}}
    _close(t)


def test_missing_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ValueError):
        build_translator(MtConfig(provider="deepseek"))


def test_unknown_provider():
    with pytest.raises(ValueError):
        build_translator(MtConfig(provider="noexiste"))
