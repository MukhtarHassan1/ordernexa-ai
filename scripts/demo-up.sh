#!/usr/bin/env bash
# Non-destructive local OrderNexa startup. Never removes named volumes.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

test -f .env || { echo "ERROR: private .env is missing. Copy values manually from your existing installation; do not regenerate working secrets." >&2; exit 1; }

docker compose config --quiet
# Keep the default footprint small for an 8 GB workstation. Odoo/n8n can be
# started separately when the demo step actually needs them.
docker compose up -d postgres redis minio minio-init api

echo "OrderNexa core started without resetting any volume."
echo "Console (development only): http://127.0.0.1:8000/console/"
echo "Use ./scripts/health-check.sh next."
