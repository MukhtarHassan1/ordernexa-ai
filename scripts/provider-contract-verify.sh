#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== External provider contracts (offline; no remote writes) =="
if docker compose config --services >/dev/null 2>&1 && docker image inspect ordernexa-api >/dev/null 2>&1; then
  echo "Using dedicated api-tests image/profile when available."
fi

docker compose --profile test run --rm api-tests \
  tests/test_external_provider_contracts.py \
  tests/test_integration_contracts.py \
  tests/test_automation_contracts.py \
  tests/test_automation_routes.py \
  tests/test_stripe_sandbox.py

echo "PASS: offline provider contract suite completed."
echo "NOTE: this does not claim live Microsoft/Vapi/Twilio/HubSpot/Teams/Stripe acceptance."
