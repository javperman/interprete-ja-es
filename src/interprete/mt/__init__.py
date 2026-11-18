"""Traducción automática (MT)."""

from .base import Translator
from .factory import build_translator
from .openai_compat import PROVIDERS, OpenAICompatibleTranslator
from .prompt import build_messages, build_system_prompt
from .vertex import VertexTranslator, build_vertex_body

__all__ = [
    "PROVIDERS",
    "OpenAICompatibleTranslator",
    "Translator",
    "VertexTranslator",
    "build_messages",
    "build_system_prompt",
    "build_translator",
    "build_vertex_body",
]
