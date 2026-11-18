#!/usr/bin/env bash
# install-voicevox.sh — instala VOICEVOX Engine (build CPU) SIN root.
#
# Descarga el paquete oficial linux-cpu-x64 y lo deja en
# ~/.local/share/voicevox-engine/<version>/ (raíz de datos del usuario).
# Instala una unidad systemd de usuario para lanzarlo en 127.0.0.1:50021.
#
#   ./scripts/install-voicevox.sh            # descarga, extrae e instala el servicio
#   ./scripts/install-voicevox.sh --dry-run  # solo muestra qué haría
#   ./scripts/install-voicevox.sh --revert   # desinstala (detiene y borra)
#
# Variables: VOICEVOX_VERSION (0.26.1), VOICEVOX_VARIANT (linux-cpu-x64),
#            VOICEVOX_HOME (~/.local/share/voicevox-engine).

set -euo pipefail

VERSION="${VOICEVOX_VERSION:-0.26.1}"
VARIANT="${VOICEVOX_VARIANT:-linux-cpu-x64}"
FILE="voicevox_engine-${VARIANT}-${VERSION}.7z.001"
URL="https://github.com/VOICEVOX/voicevox_engine/releases/download/${VERSION}/${FILE}"
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/voicevox"
HOME_DIR="${VOICEVOX_HOME:-$HOME/.local/share/voicevox-engine}"
DEST="$HOME_DIR/$VERSION"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_SRC="$REPO_DIR/systemd/user/interprete-voicevox.service"
UNIT_DST="$HOME/.config/systemd/user/interprete-voicevox.service"
UNIT_NAME=interprete-voicevox.service

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ok\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

MODE=install
case "${1:-}" in
    --dry-run) MODE=dry ;;
    --revert)  MODE=revert ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
esac

if [[ "$MODE" == "revert" ]]; then
    info "Desinstalando VOICEVOX…"
    systemctl --user disable --now "$UNIT_NAME" 2>/dev/null || true
    rm -f "$UNIT_DST"
    systemctl --user daemon-reload
    rm -rf "$HOME_DIR" "$CACHE"
    ok "VOICEVOX eliminado"
    exit 0
fi

if [[ "$MODE" == "dry" ]]; then
    echo "Descargaría:  $URL"
    echo "Caché:        $CACHE/$FILE"
    echo "Extraería en: $DEST"
    echo "Instalaría:   $UNIT_DST"
    exit 0
fi

command -v 7z >/dev/null || die "falta '7z' (paquete p7zip)"
command -v curl >/dev/null || die "falta 'curl'"

mkdir -p "$CACHE"
if [[ ! -f "$CACHE/$FILE" ]]; then
    info "Descargando VOICEVOX $VERSION (~1,8 GB)…"
    curl -L --fail -C - -o "$CACHE/$FILE" "$URL"
fi
ok "paquete en caché: $CACHE/$FILE"

if [[ ! -x "$DEST/run" ]]; then
    info "Extrayendo…"
    # Extraer en el disco real (no en /tmp, que es tmpfs pequeño).
    extract_root="${VOICEVOX_EXTRACT_DIR:-$CACHE}"
    mkdir -p "$extract_root"
    tmp="$(mktemp -d "$extract_root/extract.XXXXXX")"
    trap 'rm -rf "$tmp"' EXIT
    7z x -y -o"$tmp" "$CACHE/$FILE" >/dev/null
    runpath="$(find "$tmp" -maxdepth 3 -type f -name run | head -n1)"
    [[ -n "$runpath" ]] || die "no encuentro el script 'run' dentro del paquete"
    srcdir="$(dirname "$runpath")"
    mkdir -p "$DEST"
    cp -a "$srcdir/." "$DEST/"
    chmod +x "$DEST/run" 2>/dev/null || true
    ok "extraído en $DEST"
else
    ok "ya extraído en $DEST"
fi

ln -sfn "$VERSION" "$HOME_DIR/current"
ok "enlace $HOME_DIR/current -> $VERSION"

mkdir -p "$(dirname "$UNIT_DST")"
install -m 0644 "$UNIT_SRC" "$UNIT_DST"
systemctl --user daemon-reload
ok "unidad instalada: $UNIT_DST"

info "Arrancando VOICEVOX…"
systemctl --user enable --now "$UNIT_NAME"
sleep 3
if curl -s --max-time 5 http://127.0.0.1:50021/version >/dev/null; then
    ok "VOICEVOX responde: $(curl -s http://127.0.0.1:50021/version)"
else
    echo "AVISO: aún no responde en :50021; revisa 'systemctl --user status $UNIT_NAME'" >&2
fi
