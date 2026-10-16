#!/usr/bin/env bash
# Non-destructive local verification. Never removes named volumes and never enables external writes.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

echo '== Safety =='
echo 'This script will NOT run docker compose down -v and will NOT enable external writes.'

echo '== Compose =='
docker compose config -q

echo '== Start local authoritative core =='
docker compose up -d postgres redis minio minio-init api

echo '== Wait for PostgreSQL =='
for i in $(seq 1 40); do
  if docker compose exec -T postgres sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then break; fi
  sleep 2
  if [ "$i" = 40 ]; then echo 'ERROR: PostgreSQL did not become ready.' >&2; exit 1; fi
done

echo '== Migrations =='
docker compose exec -T -w /app api python -m alembic -c /app/alembic.ini upgrade head
docker compose exec -T -w /app api python -m alembic -c /app/alembic.ini current

echo '== API readiness =='
for i in $(seq 1 40); do
  if curl -fsS http://127.0.0.1:8000/api/v1/health/ready >/tmp/ordernexa-ready.json 2>/dev/null; then
    cat /tmp/ordernexa-ready.json; echo; break
  fi
  sleep 2
  if [ "$i" = 40 ]; then echo 'ERROR: API readiness did not pass.' >&2; exit 1; fi
done

echo '== Tests =='
bash scripts/test-all.sh

echo '== Health =='
bash scripts/health-check.sh

echo 'PASS: non-destructive local verification completed. External providers are separate acceptance gates.'
