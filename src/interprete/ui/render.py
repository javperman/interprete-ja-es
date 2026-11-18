"""Construcción del cuadro de la TUI (puro y testeable).

``render_rows`` devuelve las filas ya recortadas/rellenadas al ancho exacto, cada
una con sus segmentos y estilo. Separar el dibujado del terminal permite probar la
maquetación sin abrir una TTY.

Marcado: el japonés es de **doble ancho**, así que el recorte se hace con
``ui.text`` (ancho real), no con ``len()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .state import AppState, ChannelState
from .text import display_width, fit, pad, truncate, wrap

# ------------------------------------------------------------------ estilos
STYLES: dict[str, str] = {
    "": "",
    "title": "\x1b[1;36m",
    "info": "\x1b[2m",
    "hdr_listen": "\x1b[1;33m",
    "hdr_speak": "\x1b[1;35m",
    "status": "\x1b[2m",
    "dst": "",
    "src": "\x1b[2m",
    "sep": "\x1b[2m",
    "keys": "\x1b[2m",
    "help.key": "\x1b[1;36m",
    "notice.info": "\x1b[36m",
    "notice.ok": "\x1b[32m",
    "notice.warn": "\x1b[33m",
    "notice.error": "\x1b[1;31m",
}
RESET = "\x1b[0m"
TWO_COL_MIN_WIDTH = 76
MIN_WIDTH = 40
MIN_HEIGHT = 8


@dataclass(slots=True)
class Row:
    """Una fila de pantalla: segmentos (texto, estilo)."""

    segments: list[tuple[str, str]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(text for text, _ in self.segments)

    def ansi(self) -> str:
        out = []
        for text, style in self.segments:
            code = STYLES.get(style, "")
            out.append(f"{code}{text}{RESET}" if code else text)
        return "".join(out)


def row(text: str, style: str = "") -> Row:
    return Row([(text, style)])


# ------------------------------------------------------------------ formato
def fmt_elapsed(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_ms(value: float | None) -> str:
    return f"{value:.0f}ms" if value else "—"


def fmt_s(value: float | None) -> str:
    return f"{value / 1000:.2f}s" if value else "—"


# ------------------------------------------------------------------ cabeceras
def _title_row(state: AppState, width: int) -> Row:
    left = " Intérprete JA ⇄ ES "
    right = f" {fmt_elapsed(state.elapsed_s())} "
    inner = width - 2
    fill = inner - display_width(left) - display_width(right)
    if fill < 0:
        return row(fit(" Intérprete JA ⇄ ES", width), "title")
    return row("─" + left + "─" * fill + right + "─", "title")


def _info_row(state: AppState, width: int) -> Row:
    parts = [state.provider or "mt"]
    if state.model:
        parts.append(state.model)
    if state.flags.get("paused"):
        parts.append("PAUSA")
    parts.append(f"JA fondo {state.flags.get('ja_volume', 0):.2f}")
    if state.privacy:
        parts.append(state.privacy)
    return row(fit(" " + " · ".join(parts), width), "info")


def _keys_row(width: int) -> Row:
    from .keys import KEY_BAR

    text = "  ".join(f"[{key}] {label}" for key, label in KEY_BAR)
    return row(fit(text, width), "keys")


# ------------------------------------------------------------------ canales
def _channel_header(ch: ChannelState, width: int) -> Row:
    role = "hdr_listen" if ch.key == "listen" else "hdr_speak"
    text = ch.name if ch.tts_on else f"{ch.name}  ·  voz OFF"
    return row(fit(text, width), role)


def _channel_status(ch: ChannelState, width: int) -> Row:
    text = (
        f"{ch.turns} frases · 1er {fmt_s(ch.last_first_token_ms)}"
        f" · TTS {ch.spoken}/{ch.spoken + ch.skipped + ch.muted}"
    )
    if ch.errors:
        text += f" · err {ch.errors}"
    return row(fit(text, width), "status")


def _channel_body(
    ch: ChannelState, width: int, height: int, *, show_original: bool
) -> list[Row]:
    """Transcripción reciente del canal (lo nuevo abajo)."""
    if height <= 0:
        return []
    content: list[Row] = []
    for line in ch.lines:
        if show_original and line.source:
            content.append(row("  " + truncate(line.source, max(1, width - 2)), "src"))
        if line.target:
            wrapped = wrap("▸ " + line.target, width)
            content.extend(row(w, "dst") for w in wrapped)
    if len(content) > height:
        content = content[-height:]
    return content


def _column(ch: ChannelState, width: int, height: int, *, show_original: bool) -> list[Row]:
    if height <= 0:
        return []
    rows = [_channel_header(ch, width), _channel_status(ch, width)]
    rows.extend(_channel_body(ch, width, height - 2, show_original=show_original))
    if len(rows) < height:
        rows.extend(row(" " * width) for _ in range(height - len(rows)))
    return rows[:height]


def _merge_columns(left: list[Row], right: list[Row], width: int, sep: str = "│") -> list[Row]:
    col = (width - 1) // 2
    rows: list[Row] = []
    for lrow, rrow in zip(left, right):
        segments = [(fit(lrow.text, col), _first_style(lrow)), (sep, "sep")]
        segments.append((fit(rrow.text, width - col - 1), _first_style(rrow)))
        rows.append(Row(segments))
    return rows


def _first_style(r: Row) -> str:
    """Estilo dominante de una fila (el primer segmento con texto)."""
    for text, style in r.segments:
        if text.strip():
            return style
    return ""


def _body_rows(state: AppState, width: int, height: int, *, show_original: bool) -> list[Row]:
    if height <= 0:
        return []
    listen = state.channel("listen")
    speak = state.channel("speak")
    if listen and speak and width >= TWO_COL_MIN_WIDTH:
        left = _column(listen, (width - 1) // 2, height, show_original=show_original)
        right = _column(speak, width - (width - 1) // 2 - 1, height, show_original=show_original)
        return _merge_columns(left, right, width)
    # una sola columna: primer canal, separador, segundo canal
    channels = [c for c in (listen, speak) if c is not None]
    if not channels:
        return [row(" " * width) for _ in range(height)]
    if len(channels) == 1:
        return _column(channels[0], width, height, show_original=show_original)
    top = max(1, (height - 1) // 2)
    bottom = height - top - 1
    rows = _column(channels[0], width, top, show_original=show_original)
    rows.append(row("─" * width, "sep"))
    rows.extend(_column(channels[1], width, max(0, bottom), show_original=show_original))
    return rows[:height]


# ------------------------------------------------------------------ pie
def _notice_row(state: AppState, width: int) -> Row:
    notice = state.last_notice()
    if notice is None:
        return row(" " * width)
    icon = {"info": "i", "ok": "✓", "warn": "!", "error": "✗"}.get(notice.level, "·")
    return row(fit(f" {icon} {notice.text}", width), f"notice.{notice.level}")


def _help_rows(width: int, height: int) -> list[Row]:
    from .keys import HELP_TEXT

    rows = [row(fit(" Ayuda — teclas", width), "title"), row(" " * width)]
    key_col = min(17, max(8, width // 3))
    for key, desc in HELP_TEXT:
        rows.append(
            Row(
                [
                    (fit("   " + key, key_col), "help.key"),
                    (fit("  " + desc, width - key_col), ""),
                ]
            )
        )
    while len(rows) < height:
        rows.append(row(" " * width))
    return rows[:height]


# ------------------------------------------------------------------ API
def render_rows(
    state: AppState,
    width: int,
    height: int,
    *,
    show_original: bool = True,
    show_help: bool = False,
) -> list[Row]:
    """Cuadro completo: exactamente ``height`` filas de ``width`` celdas."""
    width = max(MIN_WIDTH, width)
    height = max(MIN_HEIGHT, height)

    if show_help:
        rows = _help_rows(width, height)
        return [_pad_row(r, width) for r in rows]

    head = [_title_row(state, width), _info_row(state, width)]
    footer = [_notice_row(state, width), _keys_row(width)]
    body_h = height - len(head) - len(footer)
    body = _body_rows(state, width, body_h, show_original=show_original)
    rows = head + body + footer
    if len(rows) < height:
        rows.extend(row(" " * width) for _ in range(height - len(rows)))
    return [_pad_row(r, width) for r in rows[:height]]


def _pad_row(r: Row, width: int) -> Row:
    text = r.text
    gap = width - display_width(text)
    if gap > 0:
        return Row([*r.segments, (" " * gap, "")])
    return r


def render(
    state: AppState,
    width: int,
    height: int,
    *,
    show_original: bool = True,
    show_help: bool = False,
) -> list[str]:
    """Igual que ``render_rows`` pero solo el texto (para pruebas/registro)."""
    return [r.text for r in render_rows(state, width, height, show_original=show_original, show_help=show_help)]


def render_frame(state: AppState, width: int, height: int, *, show_original: bool = True, show_help: bool = False) -> str:
    """Cuadro listo para escribir en la terminal (con códigos ANSI)."""
    rows = render_rows(state, width, height, show_original=show_original, show_help=show_help)
    return "\r\n".join(r.ansi() for r in rows)


# ------------------------------------------------------------------ subtítulos
def subtitles_rows(
    state: AppState,
    width: int,
    height: int,
    *,
    show_original: bool = True,
    show_help: bool = False,
) -> list[Row]:
    """Modo subtítulos: la última traducción, centrada y en grande."""
    width = max(MIN_WIDTH, width)
    height = max(MIN_HEIGHT, height)
    if show_help:
        return [_pad_row(r, width) for r in _help_rows(width, height)]

    rows = [_title_row(state, width)]
    body_h = height - 3
    ch = state.channel("listen") or (state.channels[0] if state.channels else None)
    last = ch.lines[-1] if ch and ch.lines else None

    body: list[Row] = []
    if last is None:
        body.append(row(pad("(esperando…)", width, align="center"), "info"))
    else:
        if show_original and last.source:
            for piece in wrap(last.source, max(1, width - 4)):
                body.append(row(pad(piece, width, align="center"), "src"))
            body.append(row(" " * width))
        for piece in wrap(last.target, max(1, width - 4)):
            body.append(row(pad(piece, width, align="center"), "title"))

    top = max(0, (body_h - len(body)) // 2)
    rows.extend(row(" " * width) for _ in range(top))
    rows.extend(body[: max(0, body_h - top)])
    while len(rows) < height - 2:
        rows.append(row(" " * width))
    rows.append(_notice_row(state, width))
    rows.append(_keys_row(width))
    return [_pad_row(r, width) for r in rows[:height]]


def subtitles_frame(
    state: AppState,
    width: int,
    height: int,
    *,
    show_original: bool = True,
    show_help: bool = False,
) -> str:
    rows = subtitles_rows(state, width, height, show_original=show_original, show_help=show_help)
    return "\r\n".join(r.ansi() for r in rows)

