"""Listado de dispositivos de audio para la GUI (solo lectura).

Se usa ``pactl -f json`` para obtener el nombre del nodo *y* una descripción
legible. Los nodos del propio intérprete se ofrecen donde corresponde:

- ``meet_out``/``meet_in`` **no** aparecen como "salida" (haría realimentación);
- ``meet_mic`` **no** aparece como micrófono (es el destino, no la fuente).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from ..audio import default_sink, default_source


@dataclass(slots=True)
class Device:
    name: str
    label: str


def _list(kind: str) -> list[Device]:
    try:
        out = subprocess.run(
            ["pactl", "-f", "json", "list", kind],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        data = json.loads(out.stdout) if out.returncode == 0 else []
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return []
    devices: list[Device] = []
    for entry in data if isinstance(data, list) else []:
        props = entry.get("properties") or {}
        name = props.get("node.name") or entry.get("name") or ""
        if not name:
            continue
        description = entry.get("description") or name
        devices.append(Device(name=str(name), label=f"{description}"))
    return devices


def sinks(exclude: tuple[str, ...] = ()) -> list[Device]:
    return [d for d in _list("sinks") if d.name not in exclude]


def sources(exclude: tuple[str, ...] = ()) -> list[Device]:
    return [d for d in _list("sources") if d.name not in exclude]


def microphones(exclude: tuple[str, ...] = ()) -> list[Device]:
    """Solo micrófonos de verdad: sin monitores de altavoces ni de nodos virtuales."""
    result: list[Device] = []
    for device in _list("sources"):
        if device.name in exclude:
            continue
        if device.name.endswith(".monitor"):
            continue
        if device.label.lower().startswith("monitor of"):
            continue
        result.append(device)
    return result


def default_sink_label() -> str:
    try:
        return default_sink()
    except Exception:  # noqa: BLE001
        return ""


def default_source_label() -> str:
    try:
        return default_source()
    except Exception:  # noqa: BLE001
        return ""


AUTO = ""  # valor para "seguir el dispositivo por defecto del sistema"
