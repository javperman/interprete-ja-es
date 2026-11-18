"""CLI del intérprete JA ⇄ ES."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from . import __version__
from .audio import list_sink_names, list_source_names
from .config import load_config, load_env_file
from .mt import build_translator
from .session import Session, SessionOptions, make_state, resolve


# --------------------------------------------------------------------- nodos
def _cmd_nodes(cfg) -> int:
    sinks = list_sink_names()
    sources = list_source_names()
    print("Nodos virtuales del intérprete:\n")
    for label, name, kind in (
        ("meet_in  (salida Meet)", cfg.audio.sink_in, "sink"),
        ("meet_out (TTS ja)", cfg.audio.sink_out, "sink"),
        ("meet_mic (micro virtual)", cfg.audio.source_mic, "source"),
    ):
        present = name in (sinks if kind == "sink" else sources)
        mark = "ok" if present else "FALTA"
        print(f"  [{mark}] {label}: {name}")
    print("\nPistas:")
    print("  - Crea los nodos con: scripts/interprete-audio setup")
    print("  - Comprueba el enrutado con: scripts/interprete-audio verify")
    return 0


# --------------------------------------------------------------------- doctor
def _cmd_doctor(cfg, args) -> int:
    from .doctor import apply_fixes, format_checks, run_checks, worst_status

    # Sin flags se comprueban los dos canales.
    listen = args.listen or not args.speak
    speak = args.speak or not args.listen
    checks = run_checks(cfg, listen=listen, speak=speak, live=args.live)
    color = getattr(sys.stdout, "isatty", lambda: False)() and not args.no_color
    print("Comprobación previa a la reunión (solo lectura):\n")
    print(format_checks(checks, color=color))
    status = worst_status(checks)
    if args.fix and status in ("error", "warn"):
        applied = apply_fixes(checks)
        if applied:
            print("\nArreglos aplicados:")
            for item in applied:
                print(f"  · {item}")
            print("\nRepite 'interprete doctor' para confirmar.")
        else:
            print("\nNo hay arreglos automáticos para los fallos encontrados.")
    print()
    if status == "error":
        print("RESULTADO: hay bloqueos. Resuélvelos antes de la reunión.")
        return 1
    if status == "warn":
        print("RESULTADO: funciona, pero revisa los avisos.")
        return 0
    print("RESULTADO: todo listo para la reunión.")
    return 0


# ------------------------------------------------------------------- traducción
async def _translate(cfg, text: str, source: str, target: str) -> int:
    translator = build_translator(cfg.mt)
    try:
        async for chunk in translator.translate_stream(
            text, source=source, target=target, glossary=cfg.mt.glossary
        ):
            print(chunk, end="", flush=True)
    finally:
        await translator.aclose()
    print()
    return 0


# --------------------------------------------------------------------- sesión
def _options_from_args(cfg, args) -> SessionOptions:
    return SessionOptions(
        mode=args.cmd,
        sink_in=args.sink or "",
        meet_out=getattr(args, "meet_out", None) or "",
        mic=args.mic or "",
        headphones=args.headphones or "",
        ja_volume=args.ja_volume,
        es_volume=getattr(args, "es_volume", None),
        duck_factor=getattr(args, "duck_factor", None),
        ja_forward=not args.no_ja,
        es_forward=bool(getattr(args, "es_bg", False)),
        speak_es=not args.no_speak,
        speak_ja=not getattr(args, "no_speak_ja", False),
        auto_language=bool(getattr(args, "auto_language", False)) or cfg.stt.auto_language,
        input_wav=args.input,
        inject_wav=args.inject,
        fast=args.fast,
        seconds=args.seconds,
        latency_log=args.latency_log or "",
    )


async def _execute(cfg, args, mode: str) -> int:
    from .ui import build_ui

    if args.input and mode == "run":
        print("ERROR: --input no se combina con 'run'.")
        return 2

    options = _options_from_args(cfg, args)
    resolved, errors = resolve(cfg, options)
    if errors:
        for message in errors:
            print(f"ERROR: {message}")
        return 2

    state = make_state(cfg, options, resolved)
    ui = build_ui(state, args.ui or cfg.ui.mode, show_original=cfg.ui.show_original)
    session = Session(cfg, options, ui)

    await ui.run(session.serve, on_action=session.runtime.apply)

    if session.summary:
        print()
        for line in session.summary:
            print(line)
    if session.error:
        return 3
    return 0


# ---------------------------------------------------------------- comandos
def _maybe_reexec_with_cuda(cfg) -> None:
    """Reejecuta el proceso con ``LD_LIBRARY_PATH`` que incluya las libs CUDA.

    ctranslate2 carga ``libcublas``/``libcudnn`` de forma perezosa con ``dlopen``,
    y glibc lee ``LD_LIBRARY_PATH`` del entorno **inicial**; cambiarlo con
    ``os.environ`` en marcha no sirve. Por eso, si faltan las libs, nos
    reemplazamos por nosotros mismos con el entorno ya preparado.
    """
    import os

    # "auto" también necesita las libs CUDA cargadas desde el arranque: si no,
    # ctranslate2 no las encuentra y el modelo cae a CPU sin avisar.
    if not (cfg.stt.device.startswith("cuda") or cfg.stt.device == "auto"):
        return
    if os.environ.get("INTERPRETE_REEXEC") == "1":
        return

    from .stt.faster_whisper import cuda_lib_dirs

    dirs = cuda_lib_dirs(cfg.stt.cuda_lib_path)
    if not dirs:
        return
    current = os.environ.get("LD_LIBRARY_PATH", "")
    have = set(current.split(":")) if current else set()
    if all(d in have for d in dirs):
        return

    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = ":".join(dirs + ([current] if current else []))
    env["INTERPRETE_REEXEC"] = "1"
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("reexec con LD_LIBRARY_PATH=%s", env["LD_LIBRARY_PATH"])
    os.execve(sys.executable, [sys.executable, "-m", "interprete", *sys.argv[1:]], env)


def _setup_logging(verbose: bool, to_file: str | None) -> None:
    """Logs a stderr, o a fichero si una TUI/GUI ocupa la pantalla."""
    level = logging.DEBUG if verbose else logging.INFO
    if to_file:
        Path(to_file).parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(to_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(logging.DEBUG if verbose else logging.WARNING)
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _add_common_channel_args(p) -> None:
    p.add_argument("--seconds", type=float, default=None, help="para tras N segundos")
    p.add_argument("--fast", action="store_true", help="con --input: no espera en tiempo real")
    p.add_argument("--input", default=None, help="reproduce un WAV por el pipeline (sin PipeWire)")
    p.add_argument("--latency-log", default=None, help="ruta del CSV de latencias")
    p.add_argument("--es-bg", action="store_true", help="envía tu voz original a Meet (de fondo)")
    p.add_argument("--es-volume", type=float, default=None, help="volumen del ES de fondo (0-1)")
    p.add_argument(
        "--duck-factor",
        dest="duck_factor",
        type=float,
        default=None,
        help="cuánto se atenúa el fondo mientras suena la traducción (0-1)",
    )
    p.add_argument(
        "--auto-language",
        action="store_true",
        help="deja que el STT detecte el idioma (mezcla JA/ES)",
    )
    p.add_argument(
        "--ui",
        choices=("auto", "tui", "subtitles", "plain"),
        default=None,
        help="interfaz: auto (tui si hay terminal), tui, subtitles o plain",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="interprete", description="Intérprete JA ⇄ ES")
    parser.add_argument("--version", action="version", version=f"interprete {__version__}")
    parser.add_argument("--config", default=None, help="ruta a config.toml (por defecto ./config.toml)")
    parser.add_argument("-v", "--verbose", action="store_true", help="logs de depuración")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("nodes", help="muestra el estado de los nodos de audio")
    p_gui = sub.add_parser("gui", help="abre la aplicación de escritorio (GTK4)")
    p_gui.add_argument("--toggle", action="store_true", help="iniciar/parar en la app abierta")
    p_gui.add_argument("--start", action="store_true", help="iniciar la sesión en la app abierta")
    p_gui.add_argument("--subtitles", action="store_true", help="mostrar/ocultar los subtítulos")
    p_gui.add_argument("--quit", action="store_true", help="cierra la app abierta")

    p_doc = sub.add_parser("doctor", help="comprobación previa a la reunión")
    p_doc.add_argument("--listen", action="store_true", help="comprueba solo el canal de escucha")
    p_doc.add_argument("--speak", action="store_true", help="comprueba solo el canal de habla")
    p_doc.add_argument("--live", action="store_true", help="hace una traducción real de prueba")
    p_doc.add_argument("--fix", action="store_true", help="aplica arreglos (nodos, VOICEVOX)")
    p_doc.add_argument("--no-color", action="store_true", help="sin colores")

    p_tr = sub.add_parser("translate", help="traduce un texto (prueba del proveedor)")
    p_tr.add_argument("text")
    p_tr.add_argument("--from", dest="source", default="ja", help="idioma origen (ja/es)")
    p_tr.add_argument("--to", dest="target", default="es", help="idioma destino (ja/es)")

    p_li = sub.add_parser("listen", help="canal de escucha JA→ES (tú oyes español)")
    p_li.add_argument("--sink", default=None, help="sink del que capturar el monitor")
    p_li.add_argument("--inject", default=None, help="WAV a inyectar en el sink antes de escuchar")
    p_li.add_argument("--headphones", default=None, help="nodo de salida (default: sink por defecto)")
    p_li.add_argument("--no-speak", action="store_true", help="solo texto (sin voz en español)")
    p_li.add_argument("--no-ja", action="store_true", help="no reenvía el japonés original")
    p_li.add_argument("--ja-volume", type=float, default=None, help="volumen del japonés de fondo (0-1)")
    _add_common_channel_args(p_li)

    p_sp = sub.add_parser("speak", help="canal de habla ES→JA (los demás oyen japonés)")
    p_sp.add_argument("--mic", default=None, help="fuente del micrófono (default: micro del sistema)")
    p_sp.add_argument("--meet-out", dest="meet_out", default=None, help="sink que ve Meet (default meet_out)")
    p_sp.add_argument("--no-speak-ja", action="store_true", help="solo texto (sin voz en japonés)")
    _add_common_channel_args(p_sp)

    p_rn = sub.add_parser("run", help="intérprete completo: escucha y habla a la vez")
    p_rn.add_argument("--sink", default=None, help="sink del que capturar el monitor")
    p_rn.add_argument("--mic", default=None, help="fuente del micrófono")
    p_rn.add_argument("--meet-out", dest="meet_out", default=None, help="sink que ve Meet (default meet_out)")
    p_rn.add_argument("--headphones", default=None, help="nodo de salida (default: sink por defecto)")
    p_rn.add_argument("--no-speak", action="store_true", help="solo texto (sin voz en español)")
    p_rn.add_argument("--no-speak-ja", action="store_true", help="solo texto (sin voz en japonés)")
    p_rn.add_argument("--no-ja", action="store_true", help="no reenvía el japonés original")
    p_rn.add_argument("--ja-volume", type=float, default=None, help="volumen del japonés de fondo (0-1)")
    p_rn.add_argument("--es-bg", action="store_true", help="envía tu voz original a Meet (de fondo)")
    p_rn.add_argument("--es-volume", type=float, default=None, help="volumen del ES de fondo (0-1)")
    p_rn.add_argument("--duck-factor", dest="duck_factor", type=float, default=None,
                      help="cuánto se atenúa el fondo al traducir (0-1)")
    p_rn.add_argument("--auto-language", action="store_true", help="deja que el STT detecte el idioma")
    p_rn.add_argument("--seconds", type=float, default=None, help="para tras N segundos")
    p_rn.add_argument("--latency-log", default=None, help="ruta del CSV de latencias")
    p_rn.add_argument(
        "--ui",
        choices=("auto", "tui", "subtitles", "plain"),
        default=None,
        help="interfaz: auto (tui si hay terminal), tui, subtitles o plain",
    )

    # Valores por defecto para los flags que no existen en todos los subcomandos.
    parser.set_defaults(
        sink=None,
        inject=None,
        headphones=None,
        no_speak=False,
        no_speak_ja=False,
        no_ja=False,
        ja_volume=None,
        es_bg=False,
        es_volume=None,
        duck_factor=None,
        auto_language=False,
        mic=None,
        meet_out=None,
        input=None,
        fast=False,
        seconds=None,
        latency_log=None,
        ui=None,
        listen=False,
        speak=False,
        live=False,
        fix=False,
        no_color=False,
        toggle=False,
        start=False,
        subtitles=False,
        quit=False,
    )

    args = parser.parse_args(argv)

    load_env_file()  # claves desde ~/.config/interprete/env si existe
    config_path = args.config
    if config_path is None and Path("config.toml").exists():
        config_path = "config.toml"
    cfg = load_config(config_path)

    if args.cmd in ("listen", "speak", "run"):
        from .ui import is_interactive

        ui_mode = args.ui or cfg.ui.mode
        tui = is_interactive() and ui_mode in ("auto", "tui", "subtitles")
        _setup_logging(args.verbose, "logs/interprete.log" if tui else None)
    else:
        _setup_logging(args.verbose, None)

    if args.cmd == "nodes":
        return _cmd_nodes(cfg)
    if args.cmd == "doctor":
        return _cmd_doctor(cfg, args)
    if args.cmd == "gui":
        from .gui.main import run_gui

        # El modelo de voz necesita las libs CUDA desde el arranque del proceso.
        _maybe_reexec_with_cuda(cfg)
        return run_gui(
            config_path,
            toggle=bool(getattr(args, "toggle", False)),
            start=bool(getattr(args, "start", False)),
            subtitles=bool(getattr(args, "subtitles", False)),
            quit_=bool(getattr(args, "quit", False)),
        )
    if args.cmd == "translate":
        return asyncio.run(_translate(cfg, args.text, args.source, args.target))
    if args.cmd in ("listen", "speak", "run"):
        _maybe_reexec_with_cuda(cfg)
        return asyncio.run(_execute(cfg, args, args.cmd))

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
