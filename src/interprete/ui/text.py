"""Utilidades de texto para la UI en terminal.

El japonés usa caracteres de **doble ancho**: si se recorta contando ``len()``, la
interfaz se desalinea. Estas funciones calculan el ancho real de pantalla
(``unicodedata.east_asian_width``) para recortar y ajustar columnas. Son puras y
se prueban sin terminal.
"""

from __future__ import annotations

import unicodedata


def char_width(ch: str) -> int:
    """Ancho en celdas de un carácter (0 para combinantes, 2 para CJK anchos)."""
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def display_width(text: str) -> int:
    """Ancho en celdas de una cadena."""
    return sum(char_width(c) for c in text)


def truncate(text: str, width: int, ellipsis: str = "…") -> str:
    """Recorta ``text`` para que no supere ``width`` celdas (añade elipsis)."""
    if width <= 0:
        return ""
    if display_width(text) <= width:
        return text
    ell_w = display_width(ellipsis)
    if ell_w >= width:
        return ellipsis[:width]
    budget = width - ell_w
    out: list[str] = []
    used = 0
    for ch in text:
        cw = char_width(ch)
        if used + cw > budget:
            break
        out.append(ch)
        used += cw
    return "".join(out) + ellipsis


def wrap(text: str, width: int) -> list[str]:
    """Parte ``text`` en líneas de a lo sumo ``width`` celdas (corte por carácter)."""
    if width <= 0:
        return [""]
    lines: list[str] = []
    cur: list[str] = []
    used = 0
    for ch in text:
        if ch == "\n":
            lines.append("".join(cur))
            cur, used = [], 0
            continue
        cw = char_width(ch)
        if used + cw > width:
            lines.append("".join(cur))
            cur, used = [], 0
        cur.append(ch)
        used += cw
    lines.append("".join(cur))
    return lines


def pad(text: str, width: int, *, align: str = "left", fill: str = " ") -> str:
    """Rellena ``text`` hasta ``width`` celdas (izquierda/derecha/centro)."""
    gap = width - display_width(text)
    if gap <= 0:
        return text
    if align == "right":
        return fill * gap + text
    if align == "center":
        left = gap // 2
        return fill * left + text + fill * (gap - left)
    return text + fill * gap


def fit(text: str, width: int, *, ellipsis: str = "…") -> str:
    """Recorta y luego rellena: garantiza exactamente ``width`` celdas."""
    return pad(truncate(text, width, ellipsis), width)


def pad_lines(lines: list[str], width: int) -> list[str]:
    """Aplica ``fit`` a cada línea."""
    return [fit(line, width) for line in lines]
