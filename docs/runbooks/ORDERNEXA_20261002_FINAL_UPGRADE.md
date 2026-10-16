# OrderNexa 2026-10-02 Development Completion Upgrade

This upgrade is designed to be applied **over the latest 2026-10-02 source without resetting Docker volumes, replacing the private `.env`, changing `N8N_ENCRYPTION_KEY`, or switching away from local Ollama**.

## 0. What this package changes

The patch completes the credential-independent development that can be implemented safely before live Microsoft/HubSpot/Vapi/Stripe/n8n verification:

- atomic customer-PO business identity and amendment/revision model;
- cross-transaction ERP idempotency key derived from customer + normalized PO + revision;
- legacy duplicate detection so old transactions still block a new revision-1 duplicate;
- richer duplicate/history UX and decision summary;
- retry/failure classification and persisted circuit-breaker state;
- worker lease fencing, heartbeat, expired-lease quarantine and database startup retry;
- uncertain remote outcome handling that blocks blind write replay;
- durable Microsoft Graph subscription state, renewal logic and delta-sync recovery;
- deeper HubSpot company/contact identity verification;
- scoped knowledge-document retrieval with effective-date/customer isolation;
- production identity abstraction (local keys in development, OIDC/JWT boundary for deployment);
- request-size/rate-limit/security-header middleware;
- database-backed business/technical metrics;
- Exception Workbench, Integration Health, Policy & Autonomy and Ask Ops read-only console sections;
- per-action progressive-autonomy policy model that remains disabled/fail-closed by default;
- Stripe **test-mode-only** adapter with signed webhook validation and authoritative amount/currency checks;
- local scripts for safe startup, health checking and release preflight;
- stronger evaluation dataset guardrails and saved benchmark-report surfacing.

## 1. Make a backup first

From WSL:

```bash
cd ~/projects
cp -a ordernexa-ai "ordernexa-ai-backup-$(date +%Y%m%d-%H%M%S)"
```

Do **not** use `docker compose down -v`.

## 2. Preserve your private environment

Your existing `.env` is authoritative. Do not replace it with `.env.example`.

```bash
cd ~/projects/ordernexa-ai
cp .env ".env.backup-$(date +%Y%m%d-%H%M%S)"
```

The patch archive intentionally contains no `.env`.

## 3. Overlay the patch files

Extract `OrderNexa_20261002_Development_Completion_PATCH.zip` somewhere outside the repository, then copy its `ordernexa-ai/` tree over your existing repository.

Example:

```bash
mkdir -p ~/projects/ordernexa-upgrade
cd ~/projects/ordernexa-upgrade
unzip /mnt/c/Users/Hammad/Downloads/OrderNexa_20261002_Development_Completion_PATCH.zip
rsync -av --exclude '.env' --exclude '.env.*' ordernexa-ai/ ~/projects/ordernexa-ai/
```

If your ZIP is in another Windows folder, change only the ZIP path.

## 4. Review new optional environment keys

Do not regenerate existing passwords or secrets. Add only settings you intend to use. Most new settings have safe defaults in code.

For the local development phase you may keep external integrations disabled.

Recommended explicit local values:

```dotenv
AUTOMATION_LEASE_SECONDS=900
AUTOMATION_HEARTBEAT_SECONDS=30
AUTOMATION_DB_RETRY_MAX_SECONDS=60
CIRCUIT_FAILURE_THRESHOLD=3
CIRCUIT_COOLDOWN_SECONDS=120
TRUSTED_HOSTS=localhost,127.0.0.1,testserver,api
SECURITY_MAX_REQUEST_BYTES=20971520
RATE_LIMIT_REQUESTS_PER_MINUTE=120
WEBHOOK_RATE_LIMIT_REQUESTS_PER_MINUTE=300
AUTH_MODE=auto
ASK_OPS_ENABLED=true
STRIPE_ENABLED=false
```

Keep:

```dotenv
AUTOMATION_LIVE_WRITES=false
CUSTOMER_EMAIL_ENABLED=false
```

until live integrations are deliberately tested.

## 5. Rebuild the API image

The release adds `PyJWT` and `cryptography`, so rebuild instead of only restarting:

```bash
cd ~/projects/ordernexa-ai
export COMPOSE_FILE=docker-compose.yml
docker compose build api automation-worker
```

## 6. Start only the local services needed for migration

```bash
docker compose up -d postgres redis minio minio-init api
```

Wait until PostgreSQL and the API are healthy:

```bash
docker compose ps
```

## 7. Apply the new Alembic migration

Run this **inside the API container** so the same Python dependencies and database hostname are used:

```bash
docker compose exec api alembic upgrade head
```

Expected head:

```text
20261002_hardening
```

Verify:

```bash
docker compose exec api alembic current
```

The migration adds new tables/columns. It does not delete your existing transactions, Odoo data, MinIO data, n8n data, or Docker volumes.

## 8. Run the backend tests

```bash
docker compose exec api pytest -q
```

The package was statically compiled and its isolated unit/contract suite passed in the build environment. Your Docker run is the authoritative verification because it has real `asyncpg` and your exact dependency image.

## 9. Run the JavaScript console tests

```bash
docker compose exec api node --test tests-js/*.test.cjs
```

If Node is not installed in the API image, run from WSL instead:

```bash
cd ~/projects/ordernexa-ai/apps/api
node --test tests-js/*.test.cjs
```

## 10. Start/recreate the automation worker only after migration

Do not test n8n yet. This step only verifies worker/database resilience.

```bash
cd ~/projects/ordernexa-ai
docker compose --profile automation up -d --force-recreate automation-worker
```

Then inspect only recent logs:

```bash
docker compose logs --since=3m automation-worker
```

The worker now retries database startup with bounded exponential backoff and uses lease/heartbeat/fencing fields. It must not permanently die merely because PostgreSQL is recovering during Docker startup.

## 11. Open the upgraded console

```text
http://localhost:8000/console/
```

Verify these sections render:

- Operations Overview
- Transactions
- Decision Inspector
- Approval Center
- Exception Workbench
- Recovery Center
- Document Intake
- Integrations & AI / AI Quality Lab
- Policy & Autonomy
- Ask Ops AI
- Automation Queue
- Voice Review
- Audit Explorer

## 12. Verify the old canonical transaction remains intact

Open `TXN-2026-000036`. Do not re-run or modify older `TXN-2026-000002` / `TXN-2026-000003` simply to test the new duplicate layer.

The upgrade is intentionally backward-compatible: legacy transactions without a new `business_order_identities` record retain their transaction-scoped Odoo key, so an already-created ERP order remains discoverable and is not silently re-keyed.

## 13. Verify cross-transaction duplicate protection with a NEW synthetic PO

Use a new test customer PO, not PO-88192. Create it once. Then submit the same customer + same normalized PO again.

Expected second result:

- transaction enters `DUPLICATE_REVIEW`;
- ERP write is not allowed;
- duplicate candidate/history is shown;
- same-content vs unknown legacy-content evidence is surfaced when available.

For a legitimate amendment, submit `order_revision=2` plus the exact previous `amendment_of_public_id`. Revision 2 must follow revision 1; arbitrary revision skipping is rejected.

## 14. Do not continue n8n yet

The existing n8n workflows are preserved unchanged. Leave the current Header Auth checkpoint alone until the codebase verification above is complete.

## 15. Run the release preflight

```bash
cd ~/projects/ordernexa-ai
bash scripts/preflight-release.sh
```

Then:

```bash
bash scripts/health-check.sh
```

These scripts are intentionally non-destructive.

## 16. Live integrations are a separate verification phase

Nothing in this upgrade claims that Microsoft Graph, SharePoint, HubSpot, Teams, Outlook, Vapi/Twilio, Stripe, OIDC or n8n is live-verified on your accounts. The code contracts are implemented; account-specific setup remains in `docs/runbooks/ORDERNEXA_EXTERNAL_LIVE_SETUP.md`.
