#!/usr/bin/env bash
# Regenerate packages/client-py/src/decision_engine_client/_generated (ADR 0006). Dev-time only.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# `uv run` puts the locked ruff on PATH for the generator's post_hooks (deterministic formatting).
(cd "$ROOT/apps/api" && uv run uvx openapi-python-client@0.29.1 generate \
  --path "$ROOT/packages/openapi.json" \
  --config "$ROOT/packages/client-py/openapi-python-client.yaml" \
  --meta pdm --output-path "$TMP/out" --overwrite)
DEST="$ROOT/packages/client-py/src/decision_engine_client/_generated"
rm -rf "$DEST"
cp -R "$TMP/out/_generated" "$DEST"
find "$DEST" -name __pycache__ -type d -prune -exec rm -rf {} +
