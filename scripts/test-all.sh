#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo '== 1/5 Compose validation =='
docker compose config -q

echo '== 2/5 Python test image =='
docker compose --profile test build api-tests

echo '== 3/5 Backend tests =='
docker compose --profile test run --rm api-tests

echo '== 4/5 Console JavaScript tests =='
if command -v node >/dev/null 2>&1; then
  node --check apps/api/app/console/app.js
  node --check apps/api/app/console/automation.js
  node --check apps/api/app/console/intake_review.js
  node --test apps/api/tests-js/*.test.cjs
else
  docker compose --profile test run --rm console-tests
fi

echo '== 5/5 Offline release preflight =='
bash scripts/preflight-release.sh

echo 'PASS: local code-quality suite completed.'
