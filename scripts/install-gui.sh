#!/usr/bin/env bash
# install-gui.sh — instala la app de escritorio (lanzador + icono), SIN root.
#
#   ./scripts/install-gui.sh            # instala (idempotente)
#   ./scripts/install-gui.sh --dry-run  # muestra qué haría
#   ./scripts/install-gui.sh --revert   # desinstala lanzador e icono
#
# Instala únicamente ficheros de usuario:
#   ~/.local/share/applications/io.github.javperman.interprete.desktop
#   ~/.local/share/icons/hicolor/scalable/apps/io.github.javperman.interprete.svg
# y escribe (sin tocar tu config) una regla de Hyprland lista para copiar en
# docs/hyprland-interprete.conf.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_BIN="$REPO_DIR/.venv/bin/interprete"
ICON_SRC="$REPO_DIR/src/interprete/gui/assets/icon.svg"

APPS_DIR="$HOME/.local/share/applications"
ICONS_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
DESKTOP="$APPS_DIR/io.github.javperman.interprete.desktop"
ICON="$ICONS_DIR/io.github.javperman.interprete.svg"
HYPR_SNIPPET="$REPO_DIR/docs/hyprland-interprete.conf"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ok\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

MODE=install
case "${1:-}" in
    --dry-run) MODE=dry ;;
    --revert)  MODE=revert ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    "") ;;
    *) die "opción desconocida: $1" ;;
esac

if [[ "$MODE" == "revert" ]]; then
    info "Desinstalando lanzador e icono…"
    rm -f "$DESKTOP" "$ICON" "$HYPR_SNIPPET"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS_DIR" 2>/dev/null || true
    ok "hecho (la app y su entorno no se tocan)"
    exit 0
fi

[[ -x "$VENV_BIN" ]] || die "no encuentro $VENV_BIN (crea el entorno virtual: pip install -e .)"

VENV_PY="$REPO_DIR/.venv/bin/python"
PYVENV_CFG="$REPO_DIR/.venv/pyvenv.cfg"

if [[ "$MODE" != "dry" ]] && [[ ! "$("$VENV_PY" -c 'import gi' >/dev/null 2>&1 && echo sí)" == "sí" ]]; then
    info "El entorno no ve GTK4: activo include-system-site-packages (reversible)…"
    [[ -f "$PYVENV_CFG" ]] || die "no encuentro $PYVENV_CFG"
    sed -i 's/^include-system-site-packages = .*/include-system-site-packages = true/' "$PYVENV_CFG"
    if ! "$VENV_PY" -c 'import gi' >/dev/null 2>&1; then
        die "sigue sin ver GTK4; instala gtk4, libadwaita y python-gobject"
    fi
    ok "$PYVENV_CFG actualizado"
fi

read -r -d '' DESKTOP_CONTENT <<EOF || true
[Desktop Entry]
Type=Application
Version=1.0
Name=Intérprete JA ⇄ ES
Comment=Intérprete simultáneo japonés ⇄ español para Meet/Teams
Exec=$VENV_BIN gui
Icon=io.github.javperman.interprete
Terminal=false
Categories=AudioVideo;Audio;Utility;
Keywords=japones;español;traductor;reunion;voicevox;meet;
StartupWMClass=io.github.javperman.interprete
EOF

read -r -d '' HYPR_CONTENT <<EOF || true
# Regla de Hyprland para la app del intérprete (cópiala a tu hyprland.conf
# o inclúyela). Deja la ventana flotante y centrada, y añade un atajo.
#
#   windowrulev2 = float,class:^(io\.github\.javperman\.interprete)$
#   windowrulev2 = size 1120 800,class:^(io\.github\.javperman\.interprete)$
#   windowrulev2 = center,class:^(io\.github\.javperman\.interprete)$
#   windowrulev2 = float,title:^(Subtítulos)$
#   windowrulev2 = pin,title:^(Subtítulos)$
#   windowrulev2 = size 900 180,title:^(Subtítulos)$
#   windowrulev2 = move 100%-910 100%-200,title:^(Subtítulos)$
#
# Atajo para iniciar/parar sin abrir la ventana (instancia única por D-Bus):
#   bind = SUPER SHIFT, I, exec, $VENV_BIN gui --toggle
EOF

if [[ "$MODE" == "dry" ]]; then
    echo "Instalaría:  $DESKTOP"
    echo "Instalaría:  $ICON"
    echo "Escribiría:  $HYPR_SNIPPET"
    echo
    echo "$DESKTOP_CONTENT"
    exit 0
fi

info "Instalando lanzador…"
mkdir -p "$APPS_DIR" "$ICONS_DIR"
install -m 0644 "$ICON_SRC" "$ICON"
printf '%s\n' "$DESKTOP_CONTENT" > "$DESKTOP"
chmod 0644 "$DESKTOP"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS_DIR" 2>/dev/null || true
ok "$DESKTOP"
ok "$ICON"

info "Escribiendo regla de Hyprland de ejemplo…"
printf '%s\n' "$HYPR_CONTENT" > "$HYPR_SNIPPET"
ok "$HYPR_SNIPPET (cópiala a tu config si la quieres)"

echo
ok "Listo. Busca «Intérprete» en wofi/la barra, o lanza: $VENV_BIN gui"
