"""Traductor con Google Vertex AI (Gemini), autenticado con cuenta de servicio.

Usa Vertex AI con una cuenta de servicio desde Python con ``google-auth``:
  * endpoint nativo ``:streamGenerateContent?alt=sse`` para streaming de tokens;
  * ``location = global`` → host ``aiplatform.googleapis.com`` (si no,
    ``{location}-aiplatform.googleapis.com``).

La credencial se lee de un JSON de cuenta de servicio (por defecto
``~/.config/interprete/gcp-sa.json``, 0600) o de ``GOOGLE_APPLICATION_CREDENTIALS``.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx

from .base import Translator
from .prompt import build_system_prompt

SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
DEFAULT_SA = "~/.config/interprete/gcp-sa.json"


def build_vertex_body(
    text: str,
    *,
    source: str,
    target: str,
    context: list[str] | None = None,
    glossary: list[str] | None = None,
    max_output_tokens: int = 1000,
    temperature: float = 0.2,
    thinking_level: str | None = None,
) -> dict:
    """Cuerpo de la petición a Vertex ``generateContent``/``streamGenerateContent``."""
    generation_config: dict = {
        "maxOutputTokens": max_output_tokens,
        "temperature": temperature,
    }
    if thinking_level:
        generation_config["thinkingConfig"] = {"thinkingLevel": thinking_level}
    return {
        "systemInstruction": {
            "parts": [
                {
                    "text": build_system_prompt(
                        source=source, target=target, glossary=glossary, context=context
                    )
                }
            ]
        },
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": generation_config,
    }


def _token_from_stream_event(data: str) -> str | None:
    """Extrae el texto de un ``data:`` SSE de Vertex (o de None)."""
    try:
        obj = json.loads(data)
    except json.JSONDecodeError:
        return None
    cands = obj.get("candidates") or []
    if not cands:
        return None
    parts = (cands[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts) or None


class VertexTranslator(Translator):
    def __init__(
        self,
        project: str,
        model: str = "gemini-3.5-flash",
        location: str = "global",
        service_account: str | None = None,
        temperature: float = 0.2,
        max_output_tokens: int = 1000,
        thinking_level: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account as sa

        self.project = project
        self.model = model
        self.location = location
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.thinking_level = thinking_level

        path = Path(
            os.path.expanduser(
                service_account
                or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", DEFAULT_SA)
            )
        )
        if not path.exists():
            raise FileNotFoundError(
                f"no encuentro la credencial de cuenta de servicio en {path}"
            )
        self._creds = sa.Credentials.from_service_account_file(str(path), scopes=SCOPES)
        self._request = Request()
        self._creds.refresh(self._request)

        host = "aiplatform.googleapis.com" if location == "global" else f"{location}-aiplatform.googleapis.com"
        self._base = (
            f"https://{host}/v1/projects/{project}/locations/{location}"
            f"/publishers/google/models/{model}"
        )
        self._client = httpx.AsyncClient(timeout=timeout)

    def _auth_headers(self) -> dict[str, str]:
        if not self._creds.valid:
            self._creds.refresh(self._request)
        return {
            "Authorization": f"Bearer {self._creds.token}",
            "Content-Type": "application/json",
        }

    async def translate_stream(
        self,
        text: str,
        *,
        source: str,
        target: str,
        context: list[str] | None = None,
        glossary: list[str] | None = None,
    ) -> AsyncIterator[str]:
        body = build_vertex_body(
            text,
            source=source,
            target=target,
            context=context,
            glossary=glossary,
            max_output_tokens=self.max_output_tokens,
            temperature=self.temperature,
            thinking_level=self.thinking_level,
        )
        url = self._base + ":streamGenerateContent?alt=sse"
        async with self._client.stream(
            "POST", url, json=body, headers=self._auth_headers()
        ) as resp:
            if resp.status_code != 200:
                detail = (await resp.aread()).decode("utf-8", "replace")
                raise RuntimeError(f"Vertex API error ({resp.status_code}): {detail[:400]}")
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                chunk = _token_from_stream_event(line[len("data: ") :])
                if chunk:
                    yield chunk

    async def aclose(self) -> None:
        await self._client.aclose()
