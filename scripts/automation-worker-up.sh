#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
if ! grep -Eq '^AUTOMATION_WORKER_ENABLED=(true|True|1)$' .env; then
  echo "ERROR: AUTOMATION_WORKER_ENABLED is not true in your private .env." >&2
  exit 1
fi
docker compose --profile automation up -d --force-recreate automation-worker
echo "Automation worker recreated only; databases/volumes were not reset."
docker compose --profile automation logs --tail=60 automation-worker
