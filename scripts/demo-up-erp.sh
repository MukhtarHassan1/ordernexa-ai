#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
docker compose up -d odoo-db odoo
echo "Odoo started without touching its named volume: http://127.0.0.1:8069"
