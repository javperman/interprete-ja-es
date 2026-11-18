#!/usr/bin/env bash
# install-git-hooks.sh — activa los hooks de git del repo (una vez por clon).
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

chmod +x .githooks/pre-commit scripts/update-changelog.py scripts/interprete-audio
git config core.hooksPath .githooks
echo "Hooks instalados (core.hooksPath=.githooks)."
