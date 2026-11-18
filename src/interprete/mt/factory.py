"""Fábrica de traductores a partir de la configuración.

El pipeline no conoce al proveedor: pide un ``Translator`` y listo.
"""

from __future__ import annotations

import os

from ..config import MtConfig
from .base import Translator
from .openai_compat import PROVIDERS, OpenAICompatibleTranslator
from .vertex import VertexTranslator

DEFAULT_VERTEX_MODEL = "gemini-3.5-flash-lite"


def model_name(cfg: MtConfig) -> str:
    """Nombre del modelo que se usará (para mostrar en la UI)."""
    if cfg.provider == "vertex":
        return cfg.model or DEFAULT_VERTEX_MODEL
    preset = PROVIDERS.get(cfg.provider)
    if preset is None:
        return cfg.model or ""
    return cfg.model or str(preset["model"])


def build_translator(cfg: MtConfig) -> Translator:
    if cfg.provider == "vertex":
        return VertexTranslator(
            project=cfg.project,
            model=cfg.model or DEFAULT_VERTEX_MODEL,
            location=cfg.location,
            service_account=cfg.service_account,
            temperature=cfg.temperature,
            thinking_level=cfg.thinking_level or None,
        )

    preset = PROVIDERS.get(cfg.provider)
    if preset is None:
        raise ValueError(f"proveedor de MT desconocido: {cfg.provider!r}")

    base_url = cfg.base_url or str(preset["base_url"])
    model = cfg.model or str(preset["model"])
    env = cfg.api_key_env or str(preset["api_key_env"])
    api_key = os.environ.get(env, "")
    extra = preset.get("extra_body")
    if cfg.provider != "deepseek":
        extra = None  # 'thinking' solo aplica a DeepSeek
    return OpenAICompatibleTranslator(
        api_key=api_key,
        model=model,
        base_url=base_url,
        temperature=cfg.temperature,
        extra_body=extra if isinstance(extra, dict) else None,
    )
