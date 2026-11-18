"""Elección de la UI (plana, TUI o subtítulos)."""

from __future__ import annotations

import sys

from .base import Ui
from .plain import PlainUi
from .state import AppState
from .tui import SubtitleUi, TuiUi

MODES = ("auto", "tui", "subtitles", "plain")


def is_interactive() -> bool:
    return bool(getattr(sys.stdin, "isatty", lambda: False)()) and bool(
        getattr(sys.stdout, "isatty", lambda: False)()
    )


def build_ui(
    state: AppState,
    requested: str = "auto",
    *,
    show_original: bool = True,
    interactive: bool | None = None,
) -> Ui:
    """Construye la UI pedida; degrada a plana si no hay terminal interactiva."""
    interactive = is_interactive() if interactive is None else interactive
    mode = requested if requested in MODES else "auto"

    if mode == "plain" or not interactive:
        return PlainUi(state)
    if mode == "subtitles":
        return SubtitleUi(state, show_original=show_original)
    # auto | tui
    return TuiUi(state, show_original=show_original)
