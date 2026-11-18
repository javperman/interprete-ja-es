#!/usr/bin/env bash
# gcp-setup.sh — prepara Vertex AI en Google Cloud para el intérprete (sin root).
#
# Idempotente. Fija la cuenta con --account (no toca la config global de gcloud):
#   * habilita la API aiplatform.googleapis.com
#   * crea la cuenta de servicio y le da roles/aiplatform.user
#   * descarga la clave JSON a ~/.config/interprete/gcp-sa.json (0600)
#
#   ./scripts/gcp-setup.sh --dry-run
#   ./scripts/gcp-setup.sh
#
# Variables: GCP_ACCOUNT, GCP_PROJECT, GCP_SA_NAME.
# Example:
#   GCP_ACCOUNT=you@example.com GCP_PROJECT=your-gcp-project ./scripts/gcp-setup.sh

set -euo pipefail

: "${GCP_ACCOUNT:?set GCP_ACCOUNT to your Google account}"
: "${GCP_PROJECT:?set GCP_PROJECT to your GCP project id}"

ACC="$GCP_ACCOUNT"
PROJ="$GCP_PROJECT"
SA_NAME="${GCP_SA_NAME:-interprete-vertex}"
SA="${SA_NAME}@${PROJ}.iam.gserviceaccount.com"
KEY_DIR="$HOME/.config/interprete"
KEY="$KEY_DIR/gcp-sa.json"

info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ok\033[0m %s\n' "$*"; }
run()  { if [[ "$MODE" == "dry" ]]; then echo "  [dry] $*"; else "$@"; fi; }

MODE=install
[[ "${1:-}" == "--dry-run" ]] && MODE=dry
command -v gcloud >/dev/null || { echo "falta gcloud"; exit 1; }

info "Cuenta GCP:  $ACC"
info "Proyecto:    $PROJ"
info "Cuenta servicio: $SA"

info "1) Habilitar Vertex AI API"
run gcloud services enable aiplatform.googleapis.com --project="$PROJ" --account="$ACC"

info "2) Crear cuenta de servicio (si no existe)"
if gcloud iam service-accounts describe "$SA" --project="$PROJ" --account="$ACC" >/dev/null 2>&1; then
    ok "ya existe $SA"
else
    run gcloud iam service-accounts create "$SA_NAME" --project="$PROJ" --account="$ACC" \
        --display-name="Interprete JA-ES (Vertex)"
fi

info "3) Rol Vertex AI User"
run gcloud projects add-iam-policy-binding "$PROJ" --account="$ACC" \
    --member="serviceAccount:${SA}" --role="roles/aiplatform.user" --condition=None

info "4) Clave JSON privada"
if [[ -f "$KEY" ]]; then
    ok "la clave ya existe en $KEY (no se regenera)"
else
    run mkdir -p "$KEY_DIR"
    run gcloud iam service-accounts keys create "$KEY" --iam-account="$SA" --account="$ACC"
    run chmod 600 "$KEY"
fi
ok "listo. Credencial en $KEY"
