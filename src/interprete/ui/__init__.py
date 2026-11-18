"""Interfaz de usuario (texto, TUI y subtítulos)."""

from .base import Ui
from .factory import build_ui, is_interactive
from .plain import PlainUi
from .render import render, render_frame, render_rows, subtitles_frame, subtitles_rows
from .state import AppState, ChannelState, Line, Notice
from .text import display_width, fit, pad, truncate, wrap
from .tui import SubtitleUi, TuiUi

__all__ = [
    "AppState",
    "ChannelState",
    "Line",
    "Notice",
    "PlainUi",
    "SubtitleUi",
    "TuiUi",
    "Ui",
    "build_ui",
    "display_width",
    "fit",
    "is_interactive",
    "pad",
    "render",
    "render_frame",
    "render_rows",
    "subtitles_frame",
    "subtitles_rows",
    "truncate",
    "wrap",
]
