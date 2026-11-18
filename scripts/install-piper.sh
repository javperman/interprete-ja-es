#!/usr/bin/env bash
# install-piper.sh — instala Piper (TTS español) SIN root.
#
#   * instala el paquete `piper-tts` en el venv del proyecto
#   * descarga la voz a ~/.local/share/interprete/piper/<voz>/
#
#   ./scripts/install-piper.sh                 # instala (idempotente)
#   ./scripts/install-piper.sh --dry-run       # muestra qué haría
#   ./scripts/install-piper.sh --revert        # desinstala piper-tts y borra voces
#
# Variables: PIPER_VOICE (es_ES-davefx-medium), PIPER_VOICES_DIR
#            (~/.local/share/interprete/piper), PIPER_VOICES_BASE (HF rhasspy/piper-voices)

set -euo pipefail

VOICE="${PIPER_VOICE:-es_ES-davefx-medium}"
VOICES_DIR="${PIPER_VOICES_DIR:-$HOME/.local/share/interprete/piper}"
BASE="${PIPER_VOICES_BASE:-https://huggingface.co/rhasspy/piper-voices/resolve/main}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="$REPO_DIR/.venv/bin/python"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ok\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# es_ES-davefx-medium -> es/es_ES/davefx/medium
hf_path() {
    local v="$1" lang spk qual
    lang="$(cut -d- -f1 <<<"$v")"   # es_ES
    spk="$(cut -d- -f2 <<<"$v")"    # davefx
    qual="$(cut -d- -f3 <<<"$v")"   # medium
    echo "${lang%%_*}/$lang/$spk/$qual"
}

MODE=install
case "${1:-}" in
    --dry-run) MODE=dry ;;
    --revert)  MODE=revert ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
esac

if [[ "$MODE" == "revert" ]]; then
    info "Desinstalando Piper…"
    "$VENV_PY" -m pip uninstall -y piper-tts >/dev/null 2>&1 || true
    rm -rf "$VOICES_DIR"
    ok "Piper eliminado"
    exit 0
fi

[[ -x "$VENV_PY" ]] || die "no encuentro el venv en $VENV_PY (crea el entorno primero)"

P="$(hf_path "$VOICE")"
DEST="$VOICES_DIR/$VOICE"

if [[ "$MODE" == "dry" ]]; then
    echo "Instalaría:   piper-tts (pip, en el venv)"
    echo "Descargaría:  $BASE/$P/$VOICE.onnx"
    echo "              $BASE/$P/$VOICE.onnx.json"
    echo "En:           $DEST"
    exit 0
fi

info "Instalando piper-tts en el venv…"
"$VENV_PY" -m pip install --quiet piper-tts
ok "piper-tts $("$VENV_PY" -m pip show piper-tts | awk '/^Version/{print $2}')"

mkdir -p "$DEST"
for ext in onnx onnx.json; do
    f="$VOICE.$ext"
    if [[ -f "$DEST/$f" ]]; then
        ok "ya existe $f"
    else
        info "Descargando $f…"
        curl -sL --fail -o "$DEST/$f" "$BASE/$P/$f?download=true"
        ok "$(du -h "$DEST/$f" | cut -f1)  $DEST/$f"
    fi
done

info "Prueba rápida de síntesis…"
VOICE="$VOICE" VOICES_DIR="$VOICES_DIR" "$VENV_PY" - <<'PY'
import os, numpy as np
from interprete.tts import PiperTts
tts = PiperTts(voice=os.environ["VOICE"], voices_dir=os.environ["VOICES_DIR"])
out = tts.synthesize("Prueba de voz en español.", "es")
print(f"  ok síntesis: {out.audio.size / out.sample_rate:.2f} s @ {out.sample_rate} Hz")
PY
ok "Piper listo. Voz: $VOICE"
