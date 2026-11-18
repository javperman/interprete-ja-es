#!/usr/bin/env bash
# make-test-clip.sh — genera un clip de voz japonesa con VOICEVOX para las pruebas.
#
#   ./scripts/make-test-clip.sh [TEXTO] [SALIDA]
#
# Por defecto escribe tests/clips/ja_sample.wav. Requiere VOICEVOX en marcha
# (systemctl --user start interprete-voicevox).
set -euo pipefail

TEXT="${1:-お世話になっております。本日の打ち合わせを始めます。よろしくお願いします。}"
OUT="${2:-tests/clips/ja_sample.wav}"
URL="${VOICEVOX_URL:-http://127.0.0.1:50021}"
SPEAKER="${VOICEVOX_SPEAKER:-13}"  # 13 = 青山龍星

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

if ! curl -s --max-time 5 "$URL/version" >/dev/null; then
    echo "ERROR: VOICEVOX no responde en $URL" >&2
    echo "       arráncalo con: systemctl --user start interprete-voicevox" >&2
    exit 1
fi

mkdir -p "$(dirname "$OUT")"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo "==> Sintetizando ($SPEAKER): $TEXT"
# /audio_query exige POST con los parámetros en la query (verificado en 0.26.1).
curl -s -X POST -G "$URL/audio_query" \
    --data-urlencode "text=$TEXT" \
    -d "speaker=$SPEAKER" -o "$tmp/query.json"
curl -s -X POST "$URL/synthesis?speaker=$SPEAKER" \
    -H 'Content-Type: application/json' -d @"$tmp/query.json" -o "$OUT"

if ! file "$OUT" | grep -q "WAVE"; then
    echo "ERROR: la síntesis no devolvió un WAV:" >&2
    head -c 200 "$OUT" >&2; echo >&2
    exit 1
fi

echo "  ok clip: $OUT ($(du -h "$OUT" | cut -f1))"
ffprobe -hide_banner "$OUT" 2>&1 | grep -E "Duration|Stream" | sed 's/^/     /' || true
