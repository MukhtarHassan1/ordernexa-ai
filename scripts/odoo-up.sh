#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
docker compose up -d odoo-db odoo
echo 'Odoo: http://127.0.0.1:8069'
