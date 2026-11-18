"""Ventana principal de la aplicación."""

from __future__ import annotations

import os

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, GLib, Gtk

from ..config import Config
from ..session import make_state, resolve
from .page_diagnostic import PageDiagnostic
from .page_meeting import PageMeeting
from .page_settings import PageSettings
from .ui import GuiUi

IDLE_HINT = (
    "Listo. Pon auriculares y, en Meet/Teams, salida = «Meet in» y micrófono = "
    "«Micro_del_interprete»."
)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app, cfg: Config, config_path: str | None) -> None:
        super().__init__(application=app, title="Intérprete JA ⇄ ES")
        self.cfg = cfg
        self.config_path = config_path or "config.toml"
        self.engine = app.engine
        self.state = None
        self.overlay = None
        self.running = False
        self.starting = False
        self._notice = IDLE_HINT
        self._notice_level = "info"

        self.set_default_size(1120, 800)

        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)

        # ------------------------------------------------------------ header
        header = Adw.HeaderBar()
        self.header = header
        self.stack = Adw.ViewStack()
        self.switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(self.switcher)

        self.check_button = Gtk.Button(label="Comprobar")
        self.check_button.connect("clicked", lambda *_: self._show_diagnostics())
        header.pack_start(self.check_button)

        self.subtitles_button = Gtk.ToggleButton(label="Subtítulos")
        self.subtitles_button.add_css_class("flat")
        self.subtitles_button.set_tooltip_text("Ventana con la última traducción en grande")
        self.subtitles_button.connect("toggled", lambda b: self._toggle_subtitles(b.get_active()))
        header.pack_start(self.subtitles_button)

        self.toggle_button = Gtk.Button(label="Iniciar")
        self.toggle_button.add_css_class("suggested-action")
        self.toggle_button.connect("clicked", lambda *_: self.toggle())
        header.pack_end(self.toggle_button)
        toolbar.add_top_bar(header)

        # ------------------------------------------------------------- banner
        self.banner = Adw.Banner()
        self.banner.set_revealed(False)
        toolbar.add_top_bar(self.banner)

        # ------------------------------------------------------------ páginas
        self.page_meeting = PageMeeting(self)
        self.page_settings = PageSettings(self)
        self.page_diagnostic = PageDiagnostic(self)
        self.stack.add_titled(self.page_meeting, "meeting", "Reunión")
        self.stack.add_titled(self.page_settings, "settings", "Ajustes")
        self.stack.add_titled(self.page_diagnostic, "diagnostic", "Diagnóstico")
        _PAGES = {"reunion": "meeting", "ajustes": "settings", "diagnostico": "diagnostic"}
        start = os.environ.get("INTERPRETE_START_PAGE", "meeting").lower()
        self.stack.set_visible_child_name(_PAGES.get(start, start))
        toolbar.set_content(self.stack)

        # ------------------------------------------------------------ status
        self.status = Gtk.Label(label=IDLE_HINT, xalign=0)
        self.status.add_css_class("caption")
        self.status.set_ellipsize(3)  # Pango.EllipsizeMode.END
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.append(self.status)
        toolbar.add_bottom_bar(box)

        GLib.timeout_add(300, self._tick)
        GLib.idle_add(self._initial_check)

    # ------------------------------------------------------------------ ciclo
    def _initial_check(self) -> bool:
        self.page_diagnostic.refresh()
        return GLib.SOURCE_REMOVE

    def _show_diagnostics(self) -> None:
        self.stack.set_visible_child_name("diagnostic")

    def _toggle_subtitles(self, active: bool) -> None:
        if active:
            if self.overlay is None:
                from .overlay import SubtitleWindow

                self.overlay = SubtitleWindow(self)
                self.overlay.connect("close-request", self._on_overlay_closed)
            self._update_overlay()
            self.overlay.present()
        elif self.overlay is not None:
            self.overlay.hide()

    def _on_overlay_closed(self, *_args) -> bool:
        self.subtitles_button.set_active(False)
        return False

    def _update_overlay(self) -> None:
        if self.overlay is None or not self.overlay.get_visible():
            return
        state = self.state
        if state is None:
            return
        channel = state.channel("listen") or (state.channels[0] if state.channels else None)
        if channel is None or not channel.lines:
            return
        last = channel.lines[-1]
        self.overlay.update(last.source, last.target)

    def toggle(self) -> None:
        if self.running or self.starting:
            self.stop()
        else:
            self.start()

    def start(self) -> None:
        if self.running or self.starting:
            return
        options = self.page_meeting.build_options()
        resolved, errors = resolve(self.cfg, options)
        if errors:
            self.notify(" · ".join(errors), "error")
            self.banner.set_title(" · ".join(errors))
            self.banner.set_revealed(True)
            self._show_diagnostics()
            return
        self.banner.set_revealed(False)

        self.state = make_state(self.cfg, options, resolved)
        ui = GuiUi(self.state, self)
        self.starting = True
        self.page_meeting.prepare_for_run()
        self._set_toggle("Iniciando…", sensitive=True)
        self.notify("Cargando modelos… (la primera vez tarda unos segundos)", "info")
        self.engine.start_session(self.cfg, options, ui, self._session_done)

    def stop(self) -> None:
        if not (self.running or self.starting):
            return
        self.notify("Deteniendo…", "info")
        self.engine.request_stop()

    def _session_done(self, session) -> bool:
        self.starting = False
        self.running = False
        self.page_meeting.set_running(False)
        self._set_toggle("Iniciar", sensitive=True)
        if session is not None and session.error:
            self.banner.set_title(session.error)
            self.banner.set_revealed(True)
            self.notify(session.error, "error")
        elif session is not None and session.summary:
            self.notify(" · ".join(session.summary), "ok")
        else:
            self.notify(IDLE_HINT, "info")
        self.state = None
        self._update_status()
        return GLib.SOURCE_REMOVE

    # ---------------------------------------------------------------- acciones
    def apply(self, action: str) -> None:
        self.engine.apply(action)

    def refresh_now(self) -> None:
        self.page_meeting.on_state_changed()
        self._update_status()

    def on_state_changed(self) -> None:
        """Lo llama ``GuiUi`` (ya en el hilo de GTK)."""
        self.page_meeting.on_state_changed()
        self._update_status()
        self._update_overlay()

    def on_settings_saved(self) -> None:
        self.page_meeting.refresh_devices()

    def notify(self, text: str, level: str = "info") -> None:
        self._notice = text
        self._notice_level = level
        self._update_status()

    # ------------------------------------------------------------------ estado
    def _set_toggle(self, label: str, *, sensitive: bool) -> None:
        self.toggle_button.set_label(label)
        self.toggle_button.set_sensitive(sensitive)
        if label == "Parar":
            self.toggle_button.remove_css_class("suggested-action")
            self.toggle_button.add_css_class("destructive-action")
        else:
            self.toggle_button.remove_css_class("destructive-action")
            self.toggle_button.add_css_class("suggested-action")

    def _update_status(self) -> None:
        if not self.running and not self.starting:
            self.status.set_text(self._notice or IDLE_HINT)
            return
        parts: list[str] = []
        if self.state is not None:
            elapsed = self.state.elapsed_s()
            minutes, seconds = divmod(int(elapsed), 60)
            hours, minutes = divmod(minutes, 60)
            clock = f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"
            parts.append(f"● En marcha {clock}")
            for key in ("listen", "speak"):
                channel = self.state.channel(key)
                if channel is None:
                    continue
                first = channel.last_first_token_ms
                first_text = f"{first / 1000:.1f}s" if first else "—"
                info = f"{channel.name.split('(')[0].strip()}: {channel.turns} frases · {first_text}"
                if channel.filtered:
                    info += f" · {channel.filtered} ignoradas"
                if channel.errors:
                    info += f" · err {channel.errors}"
                parts.append(info)
        if self._notice:
            parts.append(self._notice)
        self.status.set_text("  ·  ".join(parts))

    def _tick(self) -> bool:
        self.engine.sync_state()
        session = self.engine.session
        if session is not None and session.running and not self.running:
            self.running = True
            self.starting = False
            self.page_meeting.set_running(True)
            self._set_toggle("Parar", sensitive=True)
            self.banner.set_revealed(False)
            self._notice = ""
        if self.state is not None:
            self.page_meeting.on_state_changed()
            if self.state.flags.get("paused"):
                self.status.add_css_class("warning")
            else:
                self.status.remove_css_class("warning")
        self._update_status()
        return GLib.SOURCE_CONTINUE
