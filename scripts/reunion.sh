#!/usr/bin/env bash
# reunion.sh — prepara y arranca el intérprete para una reunión real.
#
#   1. Comprueba el sistema (interprete doctor) y arranca VOICEVOX si hace falta.
#   2. Lanza 'interprete run' (los dos canales) con la UI en pantalla completa.
#
#   ./scripts/reunion.sh                 # comprueba y arranca
#   ./scripts/reunion.sh --skip-doctor   # arranca sin comprobar
#   ./scripts/reunion.sh --seconds 120   # arranca y para a los 2 minutos
#
# Cualquier otro argumento se pasa tal cual a 'interprete run' (--mic, --headphones…).

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$REPO_DIR/.venv/bin/python"
cd "$REPO_DIR"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

[[ -x "$PY" ]] || { echo "ERROR: no encuentro $PY (crea el entorno virtual)"; exit 1; }

SKIP_DOCTOR=0
ARGS=()
for arg in "$@"; do
    case "$arg" in
        --skip-doctor) SKIP_DOCTOR=1 ;;
        *) ARGS+=("$arg") ;;
    esac
done

if [[ "$SKIP_DOCTOR" -eq 0 ]]; then
    info "Comprobando el sistema antes de la reunión…"
    if ! "$PY" -m interprete doctor; then
        echo
        echo "El doctor encontró bloqueos. Corrígelos (o 'interprete doctor --fix')"
        echo "y vuelve a intentarlo. Para arrancar igualmente: --skip-doctor"
        exit 1
    fi
fi

info "Arrancando el intérprete. Recuerda: auriculares puestos y, en Meet/Teams,"
info "salida = 'Meet in' y micrófono = 'Meet mic' (sin cancelación de eco)."
echo
exec "$PY" -m interprete run "${ARGS[@]}"
