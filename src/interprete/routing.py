"""Enrutado en vivo: quién reproduce en `meet_in` y quién lee qué micrófono.

La app **no** se integra con la pestaña del navegador: trabaja con nodos de
PipeWire. Este módulo permite *ver* lo que está pasando en cada momento (con
`pactl -f json`) y avisar de los dos fallos típicos:

- nadie reproduce en ``meet_in`` → Meet no está usando esa salida y oirías el
  japonés sin traducir;
- una aplicación lee el **micrófono físico** → Meet estaría enviando la voz
  original en vez de la traducción.

Todo es **solo lectura**.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

# Aplicaciones internas de PipeWire que no son "de la llamada".
_INTERNAL_PREFIXES = ("input.", "output.", "monitor.")
DEFAULT_NAMES = {"", None}


@dataclass(slots=True)
class StreamInfo:
    """Un flujo de audio (reproducción o captura) y su destino."""

    index: int
    app: str
    node_name: str
    media_name: str
    media_role: str
    target: str  # nombre del sink (reproducción) o source (captura)
    internal: bool = False

    @property
    def label(self) -> str:
        return self.app or self.node_name or self.media_name or f"#{self.index}"


def _pactl(kind: str) -> list[dict]:
    try:
        out = subprocess.run(
            ["pactl", "-f", "json", "list", kind],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0 or not out.stdout.strip():
        return []
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def names_by_index(kind: str) -> dict[int, str]:
    """Mapa índice → ``node.name`` para ``sinks`` o ``sources``."""
    result: dict[int, str] = {}
    for entry in _pactl(kind):
        props = entry.get("properties") or {}
        name = props.get("node.name") or entry.get("name") or ""
        if name:
            try:
                result[int(entry.get("index"))] = name
            except (TypeError, ValueError):
                continue
    return result


def parse_streams(
    entries: list[dict], target_key: str, names: dict[int, str]
) -> list[StreamInfo]:
    """Convierte las entradas JSON de pactl en ``StreamInfo`` (función pura)."""
    streams: list[StreamInfo] = []
    for entry in entries:
        props = entry.get("properties") or {}
        node_name = str(props.get("node.name") or "")
        try:
            target_index = int(entry.get(target_key))
        except (TypeError, ValueError):
            target_index = -1
        internal = node_name.startswith(_INTERNAL_PREFIXES) or props.get("client") == "pipewire"
        streams.append(
            StreamInfo(
                index=int(entry.get("index", -1)),
                app=str(props.get("application.name") or ""),
                node_name=node_name,
                media_name=str(props.get("media.name") or ""),
                media_role=str(props.get("media.role") or ""),
                target=names.get(target_index, f"#{target_index}"),
                internal=internal,
            )
        )
    return streams


def sink_inputs() -> list[StreamInfo]:
    """Reproducciones activas (con su sink destino)."""
    return parse_streams(_pactl("sink-inputs"), "sink", names_by_index("sinks"))


def source_outputs() -> list[StreamInfo]:
    """Capturas activas (con su source de origen)."""
    return parse_streams(_pactl("source-outputs"), "source", names_by_index("sources"))


def external(streams: list[StreamInfo]) -> list[StreamInfo]:
    """Solo los flujos de aplicaciones reales (sin los módulos internos)."""
    return [s for s in streams if not s.internal]


# --------------------------------------------------------------------------
def routing_report(cfg) -> list[str]:
    """Resumen legible de quién está conectado a los nodos del intérprete."""
    lines: list[str] = []
    playing = external(sink_inputs())
    capturing = external(source_outputs())

    call_playback = [s for s in playing if s.target == cfg.audio.sink_in]
    mic_capture = [s for s in capturing if s.target == cfg.audio.mic]
    virtual_capture = [s for s in capturing if s.target == cfg.audio.source_mic]

    lines.append(f"En {cfg.audio.sink_in} (lo que oyes tú):")
    if call_playback:
        for stream in call_playback:
            lines.append(f"  · {stream.label} ({stream.media_role or 'sin rol'})")
    else:
        lines.append("  · nada (¿reunión sin empezar?)")

    lines.append(f"En {cfg.audio.source_mic} (lo que oyen ellos):")
    if virtual_capture:
        for stream in virtual_capture:
            lines.append(f"  · {stream.label} (correcto)")
    else:
        lines.append("  · nada (Meet debería usar este micrófono)")

    if cfg.audio.mic:
        lines.append(f"En {cfg.audio.mic} (tu micro físico):")
        if mic_capture:
            for stream in mic_capture:
                lines.append(f"  · {stream.label} → ¡NO debería leerlo Meet!")
        else:
            lines.append("  · nada (correcto)")
    return lines
