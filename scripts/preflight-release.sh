#!/usr/bin/env bash
# Offline release evidence only. Does not call n8n or live external integrations.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: $PYTHON_BIN is required on the host for the offline preflight." >&2
  exit 1
fi

# Never write root-owned __pycache__ files into the bind-mounted repository.
export PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/ordernexa-preflight-pycache-${USER:-user}"
rm -rf "$PYTHONPYCACHEPREFIX"

"$PYTHON_BIN" -m compileall -q apps/api/app apps/api/tests infra/docker/odoo/addons/ordernexa_connector

if command -v node >/dev/null 2>&1; then
  node --check apps/api/app/console/app.js
  node --check apps/api/app/console/automation.js
  node --check apps/api/app/console/intake_review.js
  node --test apps/api/tests-js/*.test.cjs
else
  echo "NOTICE: host Node.js not found; JavaScript checks are skipped by this host preflight."
  echo "        Run: docker compose --profile test run --rm console-tests"
fi

"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path
paths = sorted(Path('workflows/n8n').glob('*.json'))
assert paths, 'No n8n workflows found.'
for path in paths:
    obj=json.loads(path.read_text())
    assert obj.get('active') is False, path
    assert obj.get('nodes') and obj.get('connections'), path
    names=[n.get('name') for n in obj['nodes']]
    assert len(names)==len(set(names)), f'duplicate node names: {path}'
print(f'n8n templates: {len(paths)} JSON-valid and inactive (not live-tested)')
PY

"$PYTHON_BIN" evals/runners/validate_dataset.py evals/datasets/generated_draft_500_REQUIRES_REVIEW.jsonl --json-out /tmp/ordernexa-eval-dataset.json
"$PYTHON_BIN" - <<'PY'
import json
r=json.load(open('/tmp/ordernexa-eval-dataset.json'))
assert r['release_claim_eligible'] is False
print('generated 500-case dataset correctly remains ineligible for measured accuracy claims')
PY

# Reject dangerous release contents. Local private env files may exist in a developer checkout,
# but never belong in a release ZIP or Git index.
if find . -maxdepth 1 -type f -name '.env*' ! -name '.env.example' | grep -q .; then
  echo 'NOTICE: private env files exist locally. They MUST NOT be included in a public/full-source release archive.'
fi
if find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -print -quit | grep -q .; then
  echo 'NOTICE: bytecode exists in the local checkout; release packaging must exclude it.'
fi

rm -rf "$PYTHONPYCACHEPREFIX"
echo 'Offline preflight complete.'
echo 'For authoritative Python tests run: docker compose --profile test run --rm api-tests'
