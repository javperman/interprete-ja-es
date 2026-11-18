#!/usr/bin/env bash
# ver-llamada.sh — fotografía (solo lectura) del audio DURANTE una llamada.
#
# Sirve para saber exactamente quién reproduce en `meet_in` y quién lee cada
# micrófono, y para capturar las propiedades reales del flujo del navegador
# (media.role, application.name) antes de escribir una regla de aislamiento.
#
#   ./scripts/ver-llamada.sh          # imprime el informe y guarda una copia
#
# No modifica nada: solo consulta pactl / pw-dump / pw-link.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="$REPO_DIR/logs"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$OUT_DIR/llamada-$STAMP.txt"

mkdir -p "$OUT_DIR"

streams_report() {
    pw-dump 2>/dev/null | python3 -c '
import json, sys

try:
    data = json.load(sys.stdin)
except Exception:
    print("  (pw-dump no devolvio JSON)")
    raise SystemExit(0)

for node in data:
    props = (node.get("info") or {}).get("props") or {}
    media_class = props.get("media.class", "")
    if media_class not in ("Stream/Output/Audio", "Stream/Input/Audio"):
        continue
    target = props.get("node.target") or props.get("target.object") or "?"
    print("  [{cls}] app={app!r} node.name={node!r} media.role={role!r} target={target!r}".format(
        cls=media_class,
        app=props.get("application.name"),
        node=props.get("node.name"),
        role=props.get("media.role"),
        target=target,
    ))
print("  (fin)")
'
}

{
    echo "# Informe de audio de llamada — $(date -Iseconds)"
    echo
    echo "## Nodos por defecto"
    echo "sink por defecto:   $(pactl get-default-sink 2>/dev/null || echo '?')"
    echo "source por defecto: $(pactl get-default-source 2>/dev/null || echo '?')"
    echo
    echo "## Sinks"
    pactl list short sinks
    echo
    echo "## Sources"
    pactl list short sources
    echo
    echo "## Flujos de audio (reproducción y captura)"
    streams_report
    echo
    echo "## Enlaces de los nodos del intérprete"
    pw-link -l 2>/dev/null | grep -E "meet_in|meet_out|meet_mic" || echo "  (sin enlaces)"
    echo
    echo "## Reproducciones hacia los sinks (pactl -f json list sink-inputs)"
    pactl -f json list sink-inputs 2>/dev/null
    echo
    echo "## Capturas de micrófono (pactl -f json list source-outputs)"
    pactl -f json list source-outputs 2>/dev/null
} | tee "$OUT"

echo
echo "Informe guardado en: $OUT"
echo
echo "Interpretación rápida:"
"$REPO_DIR/.venv/bin/python" -c "
from interprete.config import load_config
from interprete.routing import routing_report
print(chr(10).join(routing_report(load_config())))
" 2>/dev/null || echo "  (no se pudo resumir)"
