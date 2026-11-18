"""Pestaña «Ajustes»: voces, traducción y preferencias (se guardan en config.toml)."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

from ..config import save_config
from . import voices
from .widgets import Choice, Section, Toggle, labeled, volume_scale

PROVIDERS = [
    ("vertex", "Vertex AI (Google, cuenta de servicio)"),
    ("gemini", "Gemini API (clave GEMINI_API_KEY)"),
    ("deepseek", "DeepSeek (clave DEEPSEEK_API_KEY)"),
]


class PageSettings(Gtk.ScrolledWindow):
    def __init__(self, window) -> None:
        super().__init__()
        self.window = window
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)
        self.set_child(box)

        cfg = window.cfg

        # ---------------------------------------------------------- voces
        ja_group = self._group("Voz japonesa (lo que oyen los demás)")
        self.ja_style = Choice([])
        self.ja_style.set_hexpand(True)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.append(labeled("Estilo de VOICEVOX", self.ja_style, expand=True))
        self.ja_preview = Gtk.Button(label="Probar voz")
        self.ja_preview.set_valign(Gtk.Align.END)
        self.ja_preview.connect("clicked", lambda *_: self._preview_ja())
        row.append(self.ja_preview)
        ja_group.append(row)

        hint = Gtk.Label(
            label=(
                "Para una reunión hacen falta voces claras, de tono medio y ritmo "
                "normal. Las graves y lentas (como 離途 シリアス) suenan íntimas. "
                "Las marcadas con ★ están probadas."
            ),
            xalign=0,
        )
        hint.set_wrap(True)
        hint.set_hexpand(True)
        # Sin acotar el ancho natural, el texto ensancha el marco y se recorta.
        hint.set_max_width_chars(30)
        hint.add_css_class("dim-label")
        hint.add_css_class("caption")
        ja_group.append(hint)

        self.ja_speed = volume_scale(float(cfg.tts_ja.speed_scale), lambda *_: None)
        self.ja_speed.set_range(0.7, 1.4)
        self.ja_speed.set_increments(0.05, 0.1)
        self.ja_speed.set_tooltip_text("1,00 es la velocidad natural; menos = más lento")
        ja_group.append(labeled("Velocidad", self.ja_speed, expand=True))

        self.ja_intonation = volume_scale(float(cfg.tts_ja.intonation_scale), lambda *_: None)
        self.ja_intonation.set_range(0.0, 1.5)
        self.ja_intonation.set_increments(0.05, 0.1)
        self.ja_intonation.set_tooltip_text(
            "Menos = entonación más plana y sobria (0,80 es «de negocios»; 1,00 suena a anime)"
        )
        ja_group.append(labeled("Entonación (menos = más sobria)", self.ja_intonation, expand=True))

        self.ja_pitch = volume_scale(float(cfg.tts_ja.pitch_scale), lambda *_: None)
        self.ja_pitch.set_range(-0.3, 0.3)
        self.ja_pitch.set_increments(0.02, 0.05)
        self.ja_pitch.set_tooltip_text("Tono: valores negativos hacen la voz más grave")
        ja_group.append(labeled("Tono (negativo = más grave)", self.ja_pitch, expand=True))
        box.append(ja_group)

        es_group = self._group("Voz española (lo que oyes tú)")
        self.es_voice = Choice([])
        self.es_voice.set_hexpand(True)
        self.es_length = volume_scale(1.0, lambda *_: None)
        self.es_length.set_range(0.5, 1.6)
        self.es_length.set_increments(0.05, 0.1)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.append(labeled("Voz de Piper", self.es_voice, expand=True))
        self.es_preview = Gtk.Button(label="Probar voz")
        self.es_preview.set_valign(Gtk.Align.END)
        self.es_preview.connect("clicked", lambda *_: self._preview_es())
        row.append(self.es_preview)
        es_group.append(row)
        es_group.append(labeled("Velocidad (menos = más rápido)", self.es_length, expand=True))
        box.append(es_group)

        # ------------------------------------------------------ traducción
        mt_group = self._group("Traducción")
        self.provider = Choice(PROVIDERS)
        self.provider.set_hexpand(True)
        mt_group.append(labeled("Proveedor", self.provider, expand=True))
        self.model = Gtk.Entry()
        self.model.set_placeholder_text("vacío = el modelo por defecto del proveedor")
        mt_group.append(labeled("Modelo", self.model, expand=True))
        self.temperature = volume_scale(float(cfg.mt.temperature), lambda *_: None)
        self.temperature.set_range(0.0, 1.0)
        self.temperature.set_increments(0.05, 0.1)
        mt_group.append(labeled("Temperatura", self.temperature, expand=True))
        self.context = Gtk.SpinButton.new_with_range(0, 10, 1)
        mt_group.append(labeled("Frases de contexto", self.context, expand=True))
        self.glossary = Gtk.Entry()
        self.glossary.set_placeholder_text("palabras que no deben traducirse, separadas por comas")
        mt_group.append(labeled("Glosario", self.glossary, expand=True))
        box.append(mt_group)

        # ------------------------------------------------------- preferencias
        pref_group = self._group("Preferencias")
        self.auto_language = Toggle("Detectar el idioma automáticamente", active=cfg.stt.auto_language)
        self.auto_language.button.set_halign(Gtk.Align.START)
        self.auto_language.button.set_tooltip_text(
            "Útil si se mezclan japonés y español; en llamadas puras es más preciso dejarlo apagado"
        )
        pref_group.append(self.auto_language.button)
        self.show_original = Toggle("Mostrar el texto original", active=cfg.ui.show_original)
        self.show_original.button.set_halign(Gtk.Align.START)
        pref_group.append(self.show_original.button)
        box.append(pref_group)

        # --------------------------------------------------- ruido y eco
        ruido_group = self._group("Ruido, toses y eco")
        self.hallucination_filter = Toggle(
            "Ignorar ruidos y frases inventadas", active=cfg.filters.hallucination_filter
        )
        self.hallucination_filter.button.set_halign(Gtk.Align.START)
        self.hallucination_filter.button.set_tooltip_text(
            "Cuando el STT recibe ruido, música o silencio inventa frases "
            "(«お待ちしております»). Con esto se descartan."
        )
        ruido_group.append(self.hallucination_filter.button)

        self.echo_guard = Toggle(
            "Evitar que se traduzca a sí mismo (eco)", active=cfg.filters.echo_guard
        )
        self.echo_guard.button.set_halign(Gtk.Align.START)
        self.echo_guard.button.set_tooltip_text(
            "La voz que suena en tus auriculares se escapa y la recoge el micrófono; "
            "sin esto el intérprete vuelve a traducir su propia traducción."
        )
        ruido_group.append(self.echo_guard.button)

        self.min_speech = Gtk.SpinButton.new_with_range(0, 2000, 50)
        self.min_speech.set_value(int(cfg.filters.min_speech_ms))
        self.min_speech.set_tooltip_text(
            "Duración mínima (ms) para considerar que hay una frase; sube si se cuelan golpes o toses"
        )
        ruido_group.append(
            labeled("Duración mínima de una frase (ms)", self.min_speech, expand=False)
        )
        box.append(ruido_group)

        # ---------------------------------------------------------- guardar
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.save_button = Gtk.Button(label="Guardar ajustes")
        self.save_button.add_css_class("suggested-action")
        self.save_button.connect("clicked", lambda *_: self.save())
        actions.append(self.save_button)
        self.saved_label = Gtk.Label(label="")
        self.saved_label.add_css_class("dim-label")
        actions.append(self.saved_label)
        box.append(actions)

        self._load_values()
        threading.Thread(target=self._load_catalogs, daemon=True).start()

    # ------------------------------------------------------------------ UI
    def _group(self, title: str) -> Section:
        """Grupo con título; ``append`` escribe dentro del marco."""
        return Section(title)

    def _load_values(self) -> None:
        cfg = self.window.cfg
        self.provider.set_value(cfg.mt.provider)
        self.model.set_text(cfg.mt.model or "")
        self.temperature.set_value(float(cfg.mt.temperature))
        self.context.set_value(int(cfg.mt.context_sentences))
        self.glossary.set_text(", ".join(cfg.mt.glossary))
        self.es_voice.set_value(cfg.tts_es.voice)
        self.es_length.set_value(float(cfg.tts_es.length_scale))
        self.ja_speed.set_value(float(cfg.tts_ja.speed_scale))
        self.ja_intonation.set_value(float(cfg.tts_ja.intonation_scale))
        self.ja_pitch.set_value(float(cfg.tts_ja.pitch_scale))

    # ------------------------------------------------------------- catálogos
    def _load_catalogs(self) -> None:
        cfg = self.window.cfg
        styles = voices.list_voicevox_styles(cfg.tts_ja.url)
        piper = voices.list_piper_voices(cfg.tts_es.voices_dir)

        def _apply() -> bool:
            if styles:
                self.ja_style.set_options([(str(i), n) for i, n in voices.order_styles(styles)])
                self.ja_style.set_value(str(cfg.tts_ja.speaker))
            else:
                self.ja_style.set_options([(str(cfg.tts_ja.speaker), f"estilo {cfg.tts_ja.speaker}")])
                self.window.notify(
                    "VOICEVOX no responde: no puedo listar las voces (arráncalo y reintenta)",
                    "warn",
                )
            if piper:
                self.es_voice.set_options([(v, v) for v in piper])
                self.es_voice.set_value(cfg.tts_es.voice)
            else:
                self.es_voice.set_options([(cfg.tts_es.voice, cfg.tts_es.voice)])
            return GLib.SOURCE_REMOVE

        GLib.idle_add(_apply)

    # ------------------------------------------------------------- preescucha
    def _preview_ja(self) -> None:
        style = self.ja_style.get_value()
        if not style:
            return
        speed = self.ja_speed.get_value()
        intonation = self.ja_intonation.get_value()
        pitch = self.ja_pitch.get_value()
        self._preview(
            self.ja_preview,
            lambda: voices.synthesize_voicevox(
                self.window.cfg.tts_ja.url,
                int(style),
                speed_scale=speed,
                intonation_scale=intonation,
                pitch_scale=pitch,
            ),
        )

    def _preview_es(self) -> None:
        voice = self.es_voice.get_value()
        if not voice:
            return
        length = self.es_length.get_value()
        self._preview(
            self.es_preview,
            lambda: voices.synthesize_piper(
                voice, self.window.cfg.tts_es.voices_dir, length_scale=length
            ),
        )

    def _preview(self, button: Gtk.Button, synth) -> None:
        button.set_sensitive(False)
        button.set_label("Sintetizando…")

        def _work() -> None:
            try:
                audio = synth()
                voices.play_audio(audio.audio, audio.sample_rate)
                message = f"preescucha lista ({audio.audio.size / audio.sample_rate:.1f} s)"
            except Exception as exc:  # noqa: BLE001
                message = f"no se pudo sintetizar: {type(exc).__name__}"
            GLib.idle_add(_done, message)

        def _done(message: str) -> bool:
            button.set_sensitive(True)
            button.set_label("Probar voz")
            self.window.notify(message, "info")
            return GLib.SOURCE_REMOVE

        threading.Thread(target=_work, daemon=True).start()

    # ---------------------------------------------------------------- guardar
    def save(self) -> None:
        cfg = self.window.cfg
        cfg.mt.provider = self.provider.get_value() or cfg.mt.provider
        cfg.mt.model = self.model.get_text().strip()
        cfg.mt.temperature = round(float(self.temperature.get_value()), 2)
        cfg.mt.context_sentences = int(self.context.get_value())
        glossary = [item.strip() for item in self.glossary.get_text().split(",") if item.strip()]
        cfg.mt.glossary = glossary
        style = self.ja_style.get_value()
        if style:
            cfg.tts_ja.speaker = int(style)
        cfg.tts_ja.speed_scale = round(float(self.ja_speed.get_value()), 2)
        cfg.tts_ja.intonation_scale = round(float(self.ja_intonation.get_value()), 2)
        cfg.tts_ja.pitch_scale = round(float(self.ja_pitch.get_value()), 2)
        voice = self.es_voice.get_value()
        if voice:
            cfg.tts_es.voice = voice
        cfg.tts_es.length_scale = round(float(self.es_length.get_value()), 2)
        cfg.stt.auto_language = self.auto_language.get_active()
        cfg.filters.hallucination_filter = self.hallucination_filter.get_active()
        cfg.filters.echo_guard = self.echo_guard.get_active()
        cfg.filters.min_speech_ms = int(self.min_speech.get_value())
        cfg.ui.show_original = self.show_original.get_active()
        path = save_config(cfg, self.window.config_path)
        self.saved_label.set_text(f"guardado en {path.name}")
        self.window.notify("Ajustes guardados. Se aplican al iniciar la próxima sesión.", "ok")
        self.window.on_settings_saved()
