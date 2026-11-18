"""Adaptador entre el motor y los widgets GTK.

``GuiUi`` implementa la misma interfaz ``Ui`` que la TUI y la salida de texto,
pero en vez de pintar caracteres actualiza la ventana. Como la sesión corre en
otro hilo, todo lo que toca widgets se reenvía al hilo de GTK con
``GLib.idle_add``.
"""

from __future__ import annotations

from gi.repository import GLib

from ..ui.base import Ui
from ..ui.state import AppState


class GuiUi(Ui):
    def __init__(self, state: AppState, window) -> None:
        super().__init__(state)
        self.window = window
        self.enabled = True

    # ------------------------------------------------------------------
    def turn(self, key: str, res) -> None:
        GLib.idle_add(self._deliver_turn, key, res)

    def notice(self, level: str, text: str) -> None:
        GLib.idle_add(self._deliver_notice, level, text)

    # ------------------------------------------------------------------
    def _deliver_turn(self, key: str, res):
        Ui.turn(self, key, res)
        self.window.on_state_changed()
        return GLib.SOURCE_REMOVE

    def _deliver_notice(self, level: str, text: str):
        Ui.notice(self, level, text)
        self.window.on_state_changed()
        return GLib.SOURCE_REMOVE
