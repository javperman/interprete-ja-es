"""Mapa de teclas → acciones de la UI (puro y testeable).

La TUI lee bytes en modo *raw* y los traduce a nombres de acción. El CLI es quien
ejecuta cada acción (así la UI no conoce los detalles del pipeline).
"""

from __future__ import annotations

# byte/str -> nombre de acción
KEYMAP: dict[str, str] = {
    "q": "quit",
    "\x03": "quit",  # Ctrl+C (en modo raw no llega como señal)
    "\x04": "quit",  # Ctrl+D
    "m": "toggle_tts_listen",
    "n": "toggle_tts_speak",
    "j": "toggle_ja",
    "p": "toggle_pause",
    "o": "toggle_original",
    "+": "ja_volume_up",
    "=": "ja_volume_up",
    "-": "ja_volume_down",
    "_": "ja_volume_down",
    "?": "help",
    "h": "help",
    " ": "help",
}

# Orden de las acciones de la barra inferior (etiqueta -> tecla).
KEY_BAR: list[tuple[str, str]] = [
    ("q", "salir"),
    ("m", "voz ES"),
    ("n", "voz JA"),
    ("j", "JA fondo"),
    ("+/-", "vol JA"),
    ("p", "pausa"),
    ("o", "original"),
    ("?", "ayuda"),
]

HELP_TEXT: list[tuple[str, str]] = [
    ("q  /  Ctrl+C", "salir del intérprete"),
    ("m", "activar/desactivar la voz en español (canal de escucha)"),
    ("n", "activar/desactivar la voz en japonés (canal de habla)"),
    ("j", "activar/desactivar el japonés original de fondo"),
    ("+  /  -", "subir/bajar el volumen del japonés de fondo"),
    ("p", "pausa: silencia voces y japonés de fondo sin parar la captura"),
    ("o", "mostrar/ocultar el texto original en la transcripción"),
    ("?  /  h", "esta ayuda"),
]


def parse_actions(data: bytes) -> list[str]:
    """Traduce bytes leídos de stdin en una lista de acciones."""
    actions: list[str] = []
    for byte in data:
        action = KEYMAP.get(chr(byte))
        if action is not None:
            actions.append(action)
    return actions
