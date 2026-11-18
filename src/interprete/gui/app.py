"""Aplicación GTK4/Adwaita (instancia única, con soporte de `--toggle`)."""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gdk, Gio, Gtk

from ..config import load_config
from .engine import Engine
from .window import MainWindow

APP_ID = "io.github.javperman.interprete"


class InterpreteApp(Adw.Application):
    def __init__(self, config_path: str | None = None) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.config_path = config_path
        self.engine = Engine()
        self._css_loaded = False

    # ------------------------------------------------------------------ GTK
    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._load_css()

    def _load_css(self) -> None:
        if self._css_loaded:
            return
        css_path = Path(__file__).with_name("style.css")
        if not css_path.exists():
            return
        provider = Gtk.CssProvider()
        provider.load_from_path(str(css_path))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        self._css_loaded = True

    def do_activate(self) -> None:
        window = self.props.active_window
        if window is None:
            cfg = load_config(self.config_path)
            window = MainWindow(self, cfg, self.config_path)
        window.present()

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        args = command_line.get_arguments()[1:]
        if self.props.active_window is None:
            self.activate()
        window = self.props.active_window
        if "--quit" in args:
            self.quit()
            return 0
        if window is None:
            return 0
        if "--toggle" in args:
            window.toggle()
        if "--start" in args:
            window.start()
        if "--subtitles" in args:
            window.subtitles_button.set_active(not window.subtitles_button.get_active())
        window.present()
        return 0

    def do_shutdown(self) -> None:
        try:
            self.engine.shutdown()
        finally:
            Adw.Application.do_shutdown(self)
