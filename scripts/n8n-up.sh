#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
docker compose up -d n8n-db n8n
echo 'n8n: http://127.0.0.1:5678'
echo 'Import workflows from workflows/n8n/ and keep them inactive until credentials are configured.'
