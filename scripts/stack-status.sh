#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
docker compose ps
printf '\nMain PostgreSQL readiness:\n'
docker compose exec -T postgres sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' || true
printf '\nAPI live:\n'
curl -fsS http://127.0.0.1:8000/api/v1/health/live || true
printf '\nAPI ready:\n'
curl -fsS http://127.0.0.1:8000/api/v1/health/ready || true
printf '\n'
