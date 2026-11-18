"""Construcción del prompt de intérprete (funciones puras y testeables)."""

from __future__ import annotations

LANG_NAMES = {"ja": "japonés", "es": "español", "en": "inglés"}


def _lang(code: str) -> str:
    return LANG_NAMES.get(code, code)


def build_system_prompt(
    *,
    source: str,
    target: str,
    glossary: list[str] | None = None,
    context: list[str] | None = None,
) -> str:
    """Instrucciones del intérprete (común a todos los proveedores)."""
    rules = [
        f"Eres un intérprete simultáneo {_lang(source)} → {_lang(target)}.",
        "Traduce solo la última frase del usuario; no añadas comentarios, "
        "explicaciones ni transliteraciones.",
        "Conserva nombres propios, cifras y siglas. Mantén un registro natural "
        "y hablado, apto para una reunión de trabajo.",
        "Si el texto está incompleto o es ininteligible, devuelve una traducción "
        "lo más fiel posible sin inventar contenido.",
    ]
    if glossary:
        rules.append("Glosario (respeta estas correspondencias): " + "; ".join(glossary))
    if context:
        prev = " / ".join(context[-5:])
        rules.append(f"Contexto de las últimas frases traducidas: {prev}")
    return " ".join(rules)


def build_messages(
    text: str,
    *,
    source: str,
    target: str,
    context: list[str] | None = None,
    glossary: list[str] | None = None,
) -> list[dict[str, str]]:
    """Mensajes estilo OpenAI (system + contexto como 'assistant' + user)."""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": build_system_prompt(source=source, target=target, glossary=glossary)}
    ]
    for prev in (context or [])[-5:]:
        messages.append({"role": "assistant", "content": prev})
    messages.append({"role": "user", "content": text})
    return messages
