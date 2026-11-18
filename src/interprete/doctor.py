"""Comprobación previa a la reunión (``interprete doctor``).

Revisa, **en solo lectura**, todo lo que suele fallar antes de una reunión: nodos
de PipeWire, sink/auriculares y micrófono por defecto, VOICEVOX, voz de Piper, STT
y credenciales del traductor. Con ``--live`` además hace una traducción mínima real
para verificar red y autenticación.

Nada de esto modifica el sistema salvo con ``--fix`` explícito (que solo ejecuta
``scripts/interprete-audio setup`` y arranca VOICEVOX como servicio de usuario).
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Config

ICONS = {"ok": "✓", "warn": "!", "error": "✗", "skip": "·"}
COLORS = {
    "ok": "\x1b[32m",
    "warn": "\x1b[33m",
    "error": "\x1b[31m",
    "skip": "\x1b[2m",
}
RESET = "\x1b[0m"
REPO_DIR = Path(__file__).resolve().parents[2]
REQUIRED_COMMANDS = ("pw-cat", "pw-record", "pactl", "ffmpeg")


@dataclass(slots=True)
class Check:
    name: str
    status: str  # ok | warn | error | skip
    detail: str = ""
    fix: str | None = None  # tipo de arreglo automático: "nodes" | "voicevox"


# --------------------------------------------------------------------------
def _check_commands(cfg: Config) -> Check:
    missing = [c for c in REQUIRED_COMMANDS if shutil.which(c) is None]
    if missing:
        return Check("comandos", "error", f"faltan: {', '.join(missing)}")
    return Check("comandos", "ok", ", ".join(REQUIRED_COMMANDS))


def _check_nodes(cfg: Config) -> Check:
    from .audio import list_sink_names, list_source_names

    sinks = list_sink_names()
    sources = list_source_names()
    missing = []
    if cfg.audio.sink_in not in sinks:
        missing.append(cfg.audio.sink_in)
    if cfg.audio.sink_out not in sinks:
        missing.append(cfg.audio.sink_out)
    if cfg.audio.source_mic not in sources:
        missing.append(cfg.audio.source_mic)
    if missing:
        return Check(
            "nodos de audio",
            "error",
            f"faltan {', '.join(missing)}",
            fix="nodes",
        )
    return Check(
        "nodos de audio",
        "ok",
        f"{cfg.audio.sink_in}, {cfg.audio.sink_out}, {cfg.audio.source_mic}",
    )


def _check_default_sink(cfg: Config) -> Check:
    from .audio import default_sink

    try:
        sink = default_sink()
    except Exception as exc:  # noqa: BLE001
        return Check("salida por defecto", "error", f"no se pudo consultar: {exc}")
    if sink == cfg.audio.sink_in:
        return Check(
            "salida por defecto",
            "error",
            f"{sink} es {cfg.audio.sink_in}: provocaría realimentación",
        )
    extra = ""
    if cfg.audio.headphones and cfg.audio.headphones != sink:
        extra = f" (config dice {cfg.audio.headphones})"
    return Check("salida por defecto", "ok", f"{sink}{extra}")


def _check_mic(cfg: Config) -> Check:
    from .audio import default_source, list_source_names

    sources = list_source_names()
    mic = cfg.audio.mic
    if mic and mic not in sources:
        return Check("micrófono", "error", f"config apunta a {mic}, que no existe")
    if not mic:
        try:
            mic = default_source()
        except Exception as exc:  # noqa: BLE001
            return Check("micrófono", "error", f"no se pudo consultar: {exc}")
        if cfg.audio.mic == "":
            pass
    if mic == cfg.audio.source_mic:
        return Check(
            "micrófono",
            "error",
            f"el micro por defecto es {cfg.audio.source_mic} (el virtual): "
            "configura [audio] mic en config.toml",
        )
    return Check("micrófono", "ok", mic)


def _check_voicevox(cfg: Config) -> Check:
    import httpx

    url = cfg.tts_ja.url
    try:
        resp = httpx.get(f"{url}/version", timeout=3.0)
        if resp.status_code == 200:
            return Check("VOICEVOX", "ok", f"{url} · versión {resp.text.strip('\"')}")
        return Check("VOICEVOX", "error", f"{url} respondió HTTP {resp.status_code}", fix="voicevox")
    except Exception:  # noqa: BLE001
        return Check(
            "VOICEVOX",
            "error",
            f"no responde en {url} (¿servicio parado?)",
            fix="voicevox",
        )


def _check_piper(cfg: Config) -> Check:
    voice = cfg.tts_es.voice
    path = Path(cfg.tts_es.voices_dir).expanduser() / voice / f"{voice}.onnx"
    if path.exists():
        return Check("Piper (es)", "ok", f"{voice} · {path}")
    return Check(
        "Piper (es)",
        "warn",
        f"no encuentro {path}; ejecuta scripts/install-piper.sh (solo texto)",
    )


def _check_stt(cfg: Config) -> Check:
    if not cfg.stt.device.startswith("cuda"):
        return Check("STT", "skip", f"device={cfg.stt.device} (CPU: más lento)")
    from .stt.faster_whisper import cuda_lib_dirs

    dirs = cuda_lib_dirs(cfg.stt.cuda_lib_path)
    if not dirs:
        return Check(
            "STT",
            "warn",
            f"no encuentro libs CUDA en {cfg.stt.cuda_lib_path}; el STT caerá a CPU",
        )
    dispositivo = cfg.stt.device
    if dispositivo == "auto" and not dirs:
        return Check(
            "STT",
            "warn",
            f"auto · sin libs CUDA en {cfg.stt.cuda_lib_path}: irá en CPU (más lento)",
        )
    return Check("STT", "ok", f"{dispositivo} · {len(dirs)} dirs CUDA · {cfg.stt.model}")


def _check_mt_credentials(cfg: Config) -> Check:
    provider = cfg.mt.provider
    if provider == "vertex":
        path = Path(cfg.mt.service_account).expanduser()
        if not path.exists():
            return Check(
                "traductor", "error", f"falta la clave de servicio {path} (scripts/gcp-setup.sh)"
            )
        mode = oct(path.stat().st_mode & 0o777)
        extra = "" if mode == "0o600" else f" (permisos {mode}, se recomienda 600)"
        return Check(
            "traductor",
            "ok" if mode == "0o600" else "warn",
            f"vertex · {cfg.mt.project} · {path.name}{extra}",
        )
    if provider in ("gemini", "deepseek"):
        env = cfg.mt.api_key_env or {
            "gemini": "GEMINI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
        }[provider]
        if os.environ.get(env):
            return Check("traductor", "ok", f"{provider} · {env} definida")
        return Check("traductor", "error", f"{provider} · falta {env}")
    return Check("traductor", "error", f"proveedor desconocido: {provider}")


_BROWSERS = ("brave", "chromium", "chrome", "firefox", "vivaldi", "edge", "msedge")


def _check_routing(cfg: Config) -> Check:
    """¿Meet/la reunión está usando los nodos virtuales? (solo lectura)"""
    from .routing import external, sink_inputs, source_outputs

    capturing = external(source_outputs())
    playing = external(sink_inputs())
    on_physical = [s for s in capturing if cfg.audio.mic and s.target == cfg.audio.mic]
    on_virtual = [s for s in capturing if s.target == cfg.audio.source_mic]
    on_meet_in = [s for s in playing if s.target == cfg.audio.sink_in]

    if on_physical:
        who = on_physical[0].label
        extra = " (¿Meet usa el micro físico?)" if who.lower() in _BROWSERS else ""
        return Check(
            "enrutado",
            "error",
            f"{who} lee tu micro físico{extra}: pon el micrófono de Meet en "
            f"{cfg.audio.source_mic}",
        )
    if not playing and not on_virtual:
        return Check("enrutado", "skip", "sin reunión activa (no hay flujos de audio)")
    detail = []
    if on_meet_in:
        detail.append(f"{on_meet_in[0].label} reproduce en {cfg.audio.sink_in}")
    else:
        detail.append(f"nadie reproduce en {cfg.audio.sink_in}: revisa la salida de Meet")
    if on_virtual:
        detail.append(f"{on_virtual[0].label} usa {cfg.audio.source_mic}")
    else:
        detail.append(f"nadie usa {cfg.audio.source_mic}: revisa el micro de Meet")
    estado = "ok" if (on_meet_in and on_virtual) else "warn"
    return Check("enrutado", estado, " · ".join(detail))


def _check_gtk(cfg: Config) -> Check:
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gtk
    except Exception as exc:  # noqa: BLE001
        return Check("app GTK4", "warn", f"no disponible: {type(exc).__name__} (¿gtk4/python-gobject?)")
    return Check(
        "app GTK4",
        "ok",
        f"GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()} · Adw {Adw.MAJOR_VERSION}.{Adw.MINOR_VERSION}",
    )


def _check_memory(cfg: Config) -> Check:
    try:
        info = Path("/proc/meminfo").read_text(encoding="utf-8")
    except OSError:
        return Check("memoria", "skip", "no disponible")
    available_kb = 0
    for line in info.splitlines():
        if line.startswith("MemAvailable:"):
            available_kb = int(line.split()[1])
            break
    gib = available_kb / 1024 / 1024
    if gib < 1.5:
        return Check("memoria", "warn", f"{gib:.1f} GiB libres: cierra pestañas antes de la reunión")
    return Check("memoria", "ok", f"{gib:.1f} GiB libres")


def _check_mt_live(cfg: Config) -> Check:
    from .mt import build_translator

    async def _probe() -> str:
        translator = build_translator(cfg.mt)
        try:
            parts: list[str] = []
            async for chunk in translator.translate_stream(
                "こんにちは", source="ja", target="es"
            ):
                parts.append(chunk)
            return "".join(parts).strip()
        finally:
            await translator.aclose()

    try:
        text = asyncio.run(_probe())
    except Exception as exc:  # noqa: BLE001
        return Check("traducción real", "error", f"falló: {type(exc).__name__}: {exc}")
    if not text:
        return Check("traducción real", "warn", "respuesta vacía")
    return Check("traducción real", "ok", f"'こんにちは' -> '{text}'")


# --------------------------------------------------------------------------
def run_checks(
    cfg: Config, *, listen: bool = True, speak: bool = True, live: bool = False
) -> list[Check]:
    checks: list[Check] = [_check_commands(cfg)]
    if listen or speak:
        checks.append(_check_nodes(cfg))
        checks.append(_check_default_sink(cfg))
    if speak:
        checks.append(_check_mic(cfg))
        checks.append(_check_voicevox(cfg))
    if listen:
        checks.append(_check_piper(cfg))
    checks.append(_check_stt(cfg))
    checks.append(_check_mt_credentials(cfg))
    if live:
        checks.append(_check_mt_live(cfg))
    if listen or speak:
        checks.append(_check_routing(cfg))
    checks.append(_check_gtk(cfg))
    checks.append(_check_memory(cfg))
    return checks


def worst_status(checks: list[Check]) -> str:
    for level in ("error", "warn", "ok", "skip"):
        if any(c.status == level for c in checks):
            return level
    return "skip"


def format_checks(checks: list[Check], *, color: bool = True) -> str:
    lines = []
    for check in checks:
        icon = ICONS.get(check.status, "·")
        prefix = f"{COLORS[check.status]}{icon}{RESET}" if color else icon
        detail = f"  {check.detail}" if check.detail else ""
        lines.append(f"  {prefix} {check.name:<18}{detail}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
def apply_fixes(checks: list[Check]) -> list[str]:
    """Arreglos explícitos (``--fix``): nodos y VOICEVOX. Devuelve lo aplicado."""
    applied: list[str] = []
    for check in checks:
        if check.status == "ok" or check.fix is None:
            continue
        if check.fix == "nodes":
            script = REPO_DIR / "scripts" / "interprete-audio"
            if script.exists():
                subprocess.run(["bash", str(script), "setup"], check=False)
                applied.append("scripts/interprete-audio setup")
        elif check.fix == "voicevox":
            subprocess.run(
                ["systemctl", "--user", "start", "interprete-voicevox.service"], check=False
            )
            applied.append("systemctl --user start interprete-voicevox.service")
    return applied
