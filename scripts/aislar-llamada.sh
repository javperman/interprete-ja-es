#!/usr/bin/env bash
# aislar-llamada.sh — (OPCIONAL) enruta solo el audio de la LLAMADA a `meet_in`.
#
# Sirve para que el audio de otras pestañas (música, vídeos) no acabe en
# `meet_in` y se traduzca por error.
#
#   ./scripts/aislar-llamada.sh             # muestra la regla (no instala nada)
#   ./scripts/aislar-llamada.sh --install   # la instala y reinicia WirePlumber
#   ./scripts/aislar-llamada.sh --revert    # la elimina
#
# ⚠️ PENDIENTE DE VERIFICAR EN UNA LLAMADA REAL: el valor exacto de las
# propiedades del flujo (media.role / application.name) hay que confirmarlo con
# `scripts/ver-llamada.sh` durante una llamada. Si tu navegador no marca
# `media.role = Communication`, ajusta la coincidencia antes de instalarla.
#
# Solo escribe (o borra) un fichero de usuario:
#   ~/.config/wireplumber/wireplumber.conf.d/60-interprete-llamadas.conf

set -euo pipefail

CONF_DIR="$HOME/.config/wireplumber/wireplumber.conf.d"
CONF="$CONF_DIR/60-interprete-llamadas.conf"
MEET_IN="${MEET_IN:-meet_in}"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ok\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

RULE="# Generado por scripts/aislar-llamada.sh del proyecto interprete-ja-es.
# Enruta SOLO los flujos de comunicación (llamadas) al nodo $MEET_IN.
# Revierte con: scripts/aislar-llamada.sh --revert
node.rules = [
  {
    matches = [
      { media.role = \"Communication\" }
    ]
    actions = {
      update-props = {
        node.target = \"$MEET_IN\"
      }
    }
  }
]
"

MODE=dry
case "${1:-}" in
    --install) MODE=install ;;
    --revert)  MODE=revert ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    "") ;;
    *) die "opción desconocida: $1" ;;
esac

if [[ "$MODE" == "revert" ]]; then
    rm -f "$CONF"
    systemctl --user restart wireplumber 2>/dev/null || true
    ok "regla eliminada de $CONF"
    exit 0
fi

if [[ "$MODE" == "dry" ]]; then
    echo "Instalaría esto en $CONF:"
    echo
    printf '%s\n' "$RULE"
    echo "No se ha tocado nada. Usa --install para aplicarlo."
    exit 0
fi

info "Aviso: comprueba antes el valor real con scripts/ver-llamada.sh durante una llamada."
mkdir -p "$CONF_DIR"
printf '%s' "$RULE" > "$CONF"
ok "regla escrita en $CONF"
systemctl --user restart wireplumber 2>/dev/null || true
ok "WirePlumber reiniciado. Comprueba con: ./scripts/ver-llamada.sh"
