#!/usr/bin/env bash
# Recreate only stateless application containers; never call docker compose down -v.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
docker compose up -d --force-recreate api
if docker compose --profile automation ps --status running automation-worker 2>/dev/null | grep -q automation-worker; then
  docker compose --profile automation up -d --force-recreate automation-worker
fi
echo "API/worker recreated. Persistent PostgreSQL/Odoo/MinIO/n8n volumes were preserved."
