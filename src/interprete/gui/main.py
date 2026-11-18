"""Punto de entrada de la app: ``interprete gui`` o ``python -m interprete.gui``."""

from __future__ import annotations


def run_gui(
    config_path: str | None = None,
    *,
    toggle: bool = False,
    start: bool = False,
    subtitles: bool = False,
    quit_: bool = False,
) -> int:
    """Abre (o controla) la instancia única de la app."""
    from .app import InterpreteApp

    argv = ["interprete"]
    if toggle:
        argv.append("--toggle")
    if start:
        argv.append("--start")
    if subtitles:
        argv.append("--subtitles")
    if quit_:
        argv.append("--quit")
    app = InterpreteApp(config_path)
    return app.run(argv)


if __name__ == "__main__":
    raise SystemExit(run_gui())
