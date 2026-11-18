"""Traductor genérico para proveedores compatibles con la API OpenAI.

Sirve tanto para DeepSeek como para Gemini (endpoint OpenAI-compatible de Google
AI Studio). El streaming de tokens y la construcción del prompt son comunes.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from .base import Translator
from .prompt import build_messages

# Presets de proveedor: solo cambian base_url, modelo y variable de entorno.
PROVIDERS: dict[str, dict[str, object]] = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-flash",
        "api_key_env": "DEEPSEEK_API_KEY",
        # DeepSeek activa 'thinking' por defecto; lo desactivamos para latencia.
        "extra_body": {"thinking": {"type": "disabled"}},
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-3.5-flash",
        "api_key_env": "GEMINI_API_KEY",
        "extra_body": None,
    },
}


class OpenAICompatibleTranslator(Translator):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        temperature: float = 0.2,
        extra_body: dict | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise ValueError("falta la clave del proveedor de traducción")
        self.model = model
        self.temperature = temperature
        self.extra_body = extra_body or {}
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def translate_stream(
        self,
        text: str,
        *,
        source: str,
        target: str,
        context: list[str] | None = None,
        glossary: list[str] | None = None,
    ) -> AsyncIterator[str]:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": build_messages(
                text, source=source, target=target, context=context, glossary=glossary
            ),
            "stream": True,
            "temperature": self.temperature,
        }
        payload.update(self.extra_body)

        async with self._client.stream("POST", "/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[len("data: ") :]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                delta = (chunk.get("choices") or [{}])[0].get("delta", {}).get("content")
                if delta:
                    yield delta

    async def aclose(self) -> None:
        await self._client.aclose()
