"""Widgets reutilizables de la GUI."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk


def labeled(text: str, widget: Gtk.Widget, *, expand: bool = False) -> Gtk.Box:
    """Etiqueta pequeña encima de un widget (patrón de formulario)."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    label = Gtk.Label(label=text, xalign=0)
    label.add_css_class("dim-label")
    label.add_css_class("caption")
    box.append(label)
    widget.set_hexpand(expand)
    box.append(widget)
    return box


class Choice(Gtk.Box):
    """Desplegable con ``[(valor, etiqueta)]`` y acceso por valor."""

    def __init__(self, options: list[tuple[str, str]], **kwargs) -> None:
        super().__init__(**kwargs)
        self._values: list[str] = []
        self.dropdown = Gtk.DropDown()
        self.dropdown.set_hexpand(True)
        # Sin este append el desplegable existe pero no se dibuja: la caja queda
        # vacía y no se puede elegir nada.
        self.append(self.dropdown)
        self.set_options(options)

    def set_options(self, options: list[tuple[str, str]]) -> None:
        self._values = [value for value, _ in options]
        labels = [label for _, label in options]
        self.dropdown.set_model(Gtk.StringList.new(labels))
        if labels:
            self.dropdown.set_selected(0)

    def get_value(self) -> str:
        index = self.dropdown.get_selected()
        if 0 <= index < len(self._values):
            return self._values[index]
        return self._values[0] if self._values else ""

    def set_value(self, value: str) -> bool:
        if value in self._values:
            self.dropdown.set_selected(self._values.index(value))
            return True
        return False

    def connect_changed(self, callback) -> None:
        self.dropdown.connect("notify::selected", lambda *_: callback(self.get_value()))


class Section(Gtk.Box):
    """Grupo con título y un marco; ``append`` añade dentro del marco.

    Así el código que rellena cada sección no tiene que saber que existe un
    ``Gtk.Frame`` por medio.
    """

    def __init__(self, title: str) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        label = Gtk.Label(label=title, xalign=0)
        label.add_css_class("heading")
        Gtk.Box.append(self, label)

        frame = Gtk.Frame()
        self.inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.inner.set_margin_top(10)
        self.inner.set_margin_bottom(10)
        self.inner.set_margin_start(10)
        self.inner.set_margin_end(10)
        frame.set_child(self.inner)
        Gtk.Box.append(self, frame)

    def append(self, child: Gtk.Widget) -> None:  # type: ignore[override]
        self.inner.append(child)


class Toggle:
    """Interruptor compacto con etiqueta."""

    def __init__(self, label: str, *, active: bool = True) -> None:
        self.button = Gtk.ToggleButton(label=label)
        self.button.set_active(active)
        self.button.add_css_class("flat")

    def set_active(self, active: bool) -> None:
        self.button.set_active(bool(active))

    def get_active(self) -> bool:
        return bool(self.button.get_active())

    def connect(self, callback) -> None:
        self.button.connect("toggled", lambda *_: callback(self.get_active()))

    def set_sensitive(self, value: bool) -> None:
        self.button.set_sensitive(value)


def volume_scale(initial: float, callback) -> Gtk.Scale:
    scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.05)
    scale.set_value(initial)
    scale.set_draw_value(True)
    scale.set_value_pos(Gtk.PositionType.RIGHT)
    scale.set_hexpand(True)
    scale.connect("value-changed", lambda widget: callback(widget.get_value()))
    return scale
