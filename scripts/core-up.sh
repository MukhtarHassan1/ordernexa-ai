#!/usr/bin/env bash
# Memory-friendly authoritative core for local development/testing.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Optional heavy services are not required for ordinary API/database tests.
for svc in n8n n8n-db odoo odoo-db ollama; do
  docker compose stop "$svc" >/dev/null 2>&1 || true
done

docker compose up -d postgres redis minio minio-init api
printf '\nCore started. Check with: docker compose ps\n'
