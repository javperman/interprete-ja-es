"""Ventana de subtítulos grandes (siempre a la vista durante la llamada).

GTK4 no tiene «siempre encima» portable: para que quede fija y sin bordes se
recomienda la regla de Hyprland que escribe ``scripts/install-gui.sh``
(``float`` + ``pin`` + tamaño/posición sobre el título «Subtítulos»).
"""

from __future__ import annotations

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, Pango


class SubtitleWindow(Gtk.Window):
    def __init__(self, parent: Gtk.Window) -> None:
        super().__init__(title="Subtítulos", transient_for=parent)
        self.set_default_size(940, 190)
        self.set_decorated(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(14)
        box.set_margin_bottom(14)
        box.set_margin_start(18)
        box.set_margin_end(18)

        self.source = Gtk.Label(label="", xalign=0.5)
        self.source.set_wrap(True)
        self.source.add_css_class("dim-label")
        self.source.set_ellipsize(Pango.EllipsizeMode.END)
        self.source.set_lines(1)
        box.append(self.source)

        self.target = Gtk.Label(label="(esperando…)", xalign=0.5, yalign=0.5)
        self.target.set_wrap(True)
        self.target.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.target.set_vexpand(True)
        self.target.set_justify(Gtk.Justification.CENTER)
        self.target.add_css_class("title-1")
        box.append(self.target)

        self.set_child(box)
        self._last: tuple[str, str] | None = None

    def update(self, source: str, target: str) -> None:
        if self._last == (source, target):
            return
        self._last = (source, target)
        self.source.set_text(source or "")
        self.source.set_visible(bool(source))
        self.target.set_text(target or "…")
