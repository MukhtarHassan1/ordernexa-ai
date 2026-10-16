#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

echo "== containers =="
docker compose ps postgres redis minio api || true

echo "== PostgreSQL =="
docker compose exec -T postgres sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' || true

echo "== FastAPI liveness =="
curl --fail --silent --show-error --max-time 15 http://127.0.0.1:8000/api/v1/health/live | python3 -m json.tool

echo "== FastAPI readiness =="
curl --fail --silent --show-error --max-time 30 http://127.0.0.1:8000/api/v1/health/ready | python3 -m json.tool

echo "== Alembic =="
docker compose exec -T -w /app api python -m alembic -c /app/alembic.ini current

echo "Health check completed. This script does not test n8n or live external providers."
