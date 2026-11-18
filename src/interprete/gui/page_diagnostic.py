"""Pestaña «Diagnóstico»: comprobaciones del doctor y conexiones en vivo."""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")

from gi.repository import GLib, Gtk

ICONS = {"ok": "✓", "warn": "!", "error": "✗", "skip": "·"}
CSS = {"ok": "success", "warn": "warning", "error": "error", "skip": "dim-label"}


class PageDiagnostic(Gtk.Box):
    def __init__(self, window) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.window = window
        self.set_margin_top(12)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)

        # ---------------------------------------------------------- acciones
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.check_button = Gtk.Button(label="Comprobar ahora")
        self.check_button.add_css_class("suggested-action")
        self.check_button.connect("clicked", lambda *_: self.refresh())
        actions.append(self.check_button)

        self.live_button = Gtk.Button(label="Probar traducción (real)")
        self.live_button.connect("clicked", lambda *_: self.refresh(live=True))
        actions.append(self.live_button)

        self.routing_button = Gtk.Button(label="Ver conexiones")
        self.routing_button.connect("clicked", lambda *_: self.refresh_routing())
        actions.append(self.routing_button)

        self.free_gpu_button = Gtk.Button(label="Liberar memoria de la GPU")
        self.free_gpu_button.set_tooltip_text(
            "Descarga el modelo de voz y suelta la memoria de la tarjeta (se vuelve "
            "a cargar al iniciar la próxima sesión)"
        )
        self.free_gpu_button.connect("clicked", lambda *_: self._liberar_gpu())
        actions.append(self.free_gpu_button)

        self.spinner = Gtk.Spinner()
        actions.append(self.spinner)
        self.append(actions)

        # ------------------------------------------------------- resultados
        self.summary = Gtk.Label(label="Pulsa «Comprobar ahora» para revisar el sistema.", xalign=0)
        self.summary.set_wrap(True)
        self.append(self.summary)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("boxed-list")
        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        scroller.set_child(self.listbox)
        self.append(scroller)

        # --------------------------------------------------------- conexiones
        label = Gtk.Label(label="Conexiones de audio en vivo", xalign=0)
        label.add_css_class("heading")
        self.append(label)
        self.routing = Gtk.Label(label="(pulsa «Ver conexiones»)", xalign=0)
        self.routing.set_wrap(True)
        self.routing.add_css_class("monospace")
        self.routing.set_selectable(True)
        frame = Gtk.Frame()
        frame.set_child(self._padded(self.routing))
        self.append(frame)

    def _padded(self, widget: Gtk.Widget) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.append(widget)
        return box

    # ------------------------------------------------------------------ checks
    def refresh(self, *, live: bool = False) -> None:
        self.check_button.set_sensitive(False)
        self.live_button.set_sensitive(False)
        self.spinner.start()
        self.summary.set_text("Comprobando…")
        threading.Thread(target=self._work, args=(live,), daemon=True).start()

    def _work(self, live: bool) -> None:
        from ..doctor import run_checks, worst_status

        cfg = self.window.cfg
        try:
            checks = run_checks(cfg, listen=True, speak=True, live=live)
            status = worst_status(checks)
        except Exception as exc:  # noqa: BLE001
            GLib.idle_add(self._render, [], f"error al comprobar: {type(exc).__name__}", "error")
            return
        GLib.idle_add(self._render, checks, status, "")

    def _render(self, checks, status, error: str):
        self.spinner.stop()
        self.check_button.set_sensitive(True)
        self.live_button.set_sensitive(True)
        while (row := self.listbox.get_row_at_index(0)) is not None:
            self.listbox.remove(row)
        if error:
            self.summary.set_text(error)
            return
        for check in checks:
            self.listbox.append(self._row(check))
        texts = {
            "ok": "Todo listo para la reunión.",
            "warn": "Funciona, pero revisa los avisos.",
            "error": "Hay bloqueos que resolver antes de la reunión.",
            "skip": "Comprobación incompleta.",
        }
        self.summary.set_text(texts.get(status, status))
        self.refresh_routing()
        self.window.refresh_now()
        return GLib.SOURCE_REMOVE

    def _row(self, check) -> Gtk.ListBoxRow:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)

        icon = Gtk.Label(label=ICONS.get(check.status, "·"))
        icon.add_css_class("title-3")
        icon.add_css_class(CSS.get(check.status, "dim-label"))
        box.append(icon)

        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        texts.set_hexpand(True)
        name = Gtk.Label(label=check.name, xalign=0)
        name.add_css_class("heading")
        texts.append(name)
        if check.detail:
            detail = Gtk.Label(label=check.detail, xalign=0)
            detail.set_wrap(True)
            detail.add_css_class("dim-label")
            detail.add_css_class("caption")
            texts.append(detail)
        box.append(texts)

        if check.fix and check.status != "ok":
            button = Gtk.Button(label="Arreglar")
            button.set_valign(Gtk.Align.CENTER)
            button.connect("clicked", lambda *_, c=check: self._fix(c))
            box.append(button)

        row = Gtk.ListBoxRow()
        row.set_child(box)
        return row

    def _liberar_gpu(self) -> None:
        from ..stt.faster_whisper import liberar_modelos

        if self.window.running or self.window.starting:
            self.window.notify("Para la sesión antes de liberar la GPU", "warn")
            return
        cuantos = liberar_modelos()
        if cuantos:
            self.window.notify(f"Modelo descargado: memoria de la GPU liberada ({cuantos})", "ok")
        else:
            self.window.notify("No había ningún modelo cargado", "info")

    def _fix(self, check) -> None:
        from ..doctor import apply_fixes

        applied = apply_fixes([check])
        if applied:
            self.window.notify("Arreglo aplicado: " + ", ".join(applied), "ok")
        else:
            self.window.notify("No hay arreglo automático para ese fallo", "warn")
        self.refresh()

    # --------------------------------------------------------------- conexiones
    def refresh_routing(self) -> None:
        from ..routing import routing_report

        try:
            lines = routing_report(self.window.cfg)
        except Exception as exc:  # noqa: BLE001
            lines = [f"no se pudo consultar: {type(exc).__name__}"]
        self.routing.set_text("\n".join(lines))
