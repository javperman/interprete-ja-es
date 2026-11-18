"""Pestaña «Reunión»: controles y transcripción en vivo."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, Pango

from ..session import SessionOptions
from . import devices
from .widgets import Choice, Toggle, labeled, volume_scale

MODE_OPTIONS = [
    ("run", "Ambos (intérprete completo)"),
    ("listen", "Solo oír (JA → ES)"),
    ("speak", "Solo hablar (ES → JA)"),
]


class _Transcript(Gtk.Box):
    """Panel de transcripción de un canal."""

    def __init__(self, title: str) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        header = Gtk.Label(label=title, xalign=0)
        header.add_css_class("heading")
        self.header = header
        self.append(header)

        self.buffer = Gtk.TextBuffer()
        self.buffer.create_tag("tgt", weight=Pango.Weight.BOLD, size_points=13)
        self.buffer.create_tag("src", style=Pango.Style.ITALIC)
        self.view = Gtk.TextView(buffer=self.buffer)
        self.view.set_editable(False)
        self.view.set_cursor_visible(False)
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_left_margin(8)
        self.view.set_right_margin(8)
        self.view.set_top_margin(6)
        self.view.set_bottom_margin(6)

        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        scroller.set_child(self.view)
        self.append(scroller)

    def clear(self) -> None:
        self.buffer.set_text("")

    def add_turn(self, source: str, target: str, *, show_original: bool = True) -> None:
        end = self.buffer.get_end_iter()
        if show_original and source:
            self.buffer.insert_with_tags_by_name(end, f"{source}\n", "src")
            end = self.buffer.get_end_iter()
        if target:
            self.buffer.insert_with_tags_by_name(end, f"{target}\n\n", "tgt")
        self.view.scroll_to_iter(self.buffer.get_end_iter(), 0.0, False, 0.0, 0.0)


class PageMeeting(Gtk.Box):
    def __init__(self, window) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.window = window
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)
        self._syncing = False
        self._rendered = {"listen": 0, "speak": 0}
        self._desired = {"ja": True, "es": False, "speak_es": True, "speak_ja": True}

        self.append(self._build_devices_row())
        self.append(self._build_switches_row())
        self.append(self._build_volumes_row())

        separator = Gtk.Separator()
        self.append(separator)

        self.transcripts = {
            "listen": _Transcript("JA → ES   ·   tú oyes español"),
            "speak": _Transcript("ES → JA   ·   ellos oyen japonés"),
        }
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_vexpand(True)
        paned.set_resize_start_child(True)
        paned.set_resize_end_child(True)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)
        paned.set_start_child(self.transcripts["listen"])
        paned.set_end_child(self.transcripts["speak"])
        self.append(paned)

        self.refresh_devices()
        self.set_running(False)

    # ------------------------------------------------------------------ UI
    def _build_devices_row(self) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        self.mode = Choice(MODE_OPTIONS)
        self.mode.set_hexpand(True)
        row.append(labeled("Modo", self.mode, expand=True))

        self.mic = Choice([])
        self.mic.set_hexpand(True)
        row.append(labeled("Micrófono (físico)", self.mic, expand=True))

        self.output = Choice([])
        self.output.set_hexpand(True)
        row.append(labeled("Auriculares (salida)", self.output, expand=True))

        refresh = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh.set_tooltip_text("Volver a detectar los dispositivos")
        refresh.set_valign(Gtk.Align.END)
        refresh.connect("clicked", lambda *_: self.refresh_devices())
        row.append(refresh)
        return row

    def _build_switches_row(self) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.voice_es = Toggle("Voz en español")
        self.voice_ja = Toggle("Voz en japonés")
        self.ja_bg = Toggle("Japonés de fondo")
        self.es_bg = Toggle("Mi voz de fondo", active=False)
        self.pause = Toggle("Pausa", active=False)

        self.voice_es.button.set_tooltip_text("Traducción al español en tus auriculares")
        self.voice_ja.button.set_tooltip_text("Voz japonesa que oyen los demás")
        self.ja_bg.button.set_tooltip_text("Oír a los demás en japonés, por debajo")
        self.es_bg.button.set_tooltip_text("Enviar tu voz real a la reunión, por debajo")
        self.pause.button.set_tooltip_text("Silencia las voces sin dejar de escuchar")

        actions = {
            self.voice_es: "toggle_tts_listen",
            self.voice_ja: "toggle_tts_speak",
            self.ja_bg: "toggle_ja",
            self.es_bg: "toggle_es",
            self.pause: "toggle_pause",
        }
        for toggle, action in actions.items():
            toggle.connect(lambda _v, a=action, t=toggle: self._on_toggle(a, t))
            row.append(toggle.button)
        return row

    def _build_volumes_row(self) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.ja_volume = volume_scale(0.50, lambda v: self._on_volume("forwarder", v))
        self.es_volume = volume_scale(0.50, lambda v: self._on_volume("forwarder_es", v))
        self.duck = volume_scale(0.40, lambda v: self._on_duck(v))
        self.ja_volume.set_tooltip_text(
            "Cuánto oyes a la otra persona en japonés, por debajo de la traducción"
        )
        self.es_volume.set_tooltip_text(
            "Cuánto oye ella tu voz real en español, por debajo de la voz japonesa"
        )
        self.duck.set_tooltip_text(
            "Cuánto se bajan los dos fondos mientras suena la traducción (1,00 = no se bajan)"
        )
        row.append(labeled("Volumen del japonés de fondo", self.ja_volume, expand=True))
        row.append(labeled("Volumen de mi voz de fondo", self.es_volume, expand=True))
        row.append(labeled("Atenuar fondos al traducir", self.duck, expand=True))
        return row

    # ------------------------------------------------------------- acciones
    def _on_toggle(self, action: str, toggle: Toggle) -> None:
        if self._syncing:
            return
        if not self.window.running:
            # aún no hay sesión: solo recordamos la preferencia
            self._remember(toggle)
            return
        self.window.apply(action)
        self.window.refresh_now()

    def _remember(self, toggle: Toggle) -> None:
        if toggle is self.ja_bg:
            self._desired["ja"] = toggle.get_active()
        elif toggle is self.es_bg:
            self._desired["es"] = toggle.get_active()
        elif toggle is self.voice_es:
            self._desired["speak_es"] = toggle.get_active()
        elif toggle is self.voice_ja:
            self._desired["speak_ja"] = toggle.get_active()

    def _on_volume(self, attr: str, value: float) -> None:
        if self._syncing or not self.window.running:
            return
        self.window.apply(f"set_volume:{attr}:{value:.2f}")

    def _on_duck(self, value: float) -> None:
        if self._syncing or not self.window.running:
            return
        self.window.apply(f"set_duck:{value:.2f}")

    # ------------------------------------------------------------- dispositivos
    def refresh_devices(self) -> None:
        cfg = self.window.cfg
        mic_options = [("", "Automático (micro por defecto)")]
        for device in devices.microphones(exclude=(cfg.audio.source_mic,)):
            mic_options.append((device.name, device.label))
        self.mic.set_options(mic_options)
        if cfg.audio.mic:
            self.mic.set_value(cfg.audio.mic)

        out_options = [("", "Automático (auriculares por defecto)")]
        for device in devices.sinks(exclude=(cfg.audio.sink_in, cfg.audio.sink_out)):
            out_options.append((device.name, device.label))
        self.output.set_options(out_options)
        if cfg.audio.headphones:
            self.output.set_value(cfg.audio.headphones)

    def build_options(self) -> SessionOptions:
        mode = self.mode.get_value() or "run"
        want_listen = mode in ("listen", "run")
        want_speak = mode in ("speak", "run")
        speak_es = want_listen and self.voice_es.get_active()
        ja_forward = want_listen and self.ja_bg.get_active()
        return SessionOptions(
            mode=mode,
            mic=self.mic.get_value(),
            headphones=self.output.get_value(),
            ja_forward=ja_forward,
            es_forward=want_speak and self.es_bg.get_active(),
            speak_es=speak_es,
            speak_ja=want_speak and self.voice_ja.get_active(),
            ja_volume=self.ja_volume.get_value(),
            es_volume=self.es_volume.get_value(),
            duck_factor=self.duck.get_value(),
            auto_language=self.window.cfg.stt.auto_language,
            latency_log=self.window.cfg.logging.latency_log,
        )

    # ------------------------------------------------------------- estado
    def set_running(self, running: bool) -> None:
        for widget in (self.mode.dropdown, self.mic.dropdown, self.output.dropdown):
            widget.set_sensitive(not running)
        self.pause.set_sensitive(running)

    def prepare_for_run(self) -> None:
        """Limpia la transcripción antes de empezar una sesión nueva."""
        for transcript in self.transcripts.values():
            transcript.clear()
        self._rendered = {"listen": 0, "speak": 0}

    def sync_from_state(self) -> None:
        state = self.window.state
        if state is None:
            return
        self._syncing = True
        flags = state.flags
        self.voice_es.set_active(flags.get("speak_es", self.voice_es.get_active()))
        self.voice_ja.set_active(flags.get("speak_ja", self.voice_ja.get_active()))
        self.ja_bg.set_active(flags.get("ja_forward", self.ja_bg.get_active()))
        self.es_bg.set_active(flags.get("es_forward", self.es_bg.get_active()))
        self.pause.set_active(flags.get("paused", False))
        if "ja_volume" in flags:
            self.ja_volume.set_value(float(flags["ja_volume"]))
        if "es_volume" in flags:
            self.es_volume.set_value(float(flags["es_volume"]))
        if "duck_factor" in flags:
            self.duck.set_value(float(flags["duck_factor"]))
        self._syncing = False

    def on_state_changed(self) -> None:
        state = self.window.state
        if state is None:
            return
        for key, transcript in self.transcripts.items():
            channel = state.channel(key)
            if channel is None:
                continue
            already = self._rendered.get(key, 0)
            if channel.turns < already:  # se reinició
                transcript.clear()
                already = 0
            for line in channel.lines[already:]:
                transcript.add_turn(
                    line.source, line.target, show_original=state.flags.get("show_original", True)
                )
            self._rendered[key] = channel.turns
        self.sync_from_state()
