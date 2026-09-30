# OrderNexa AI — NECTELIS Customer-to-Cash flagship

**A source-grounded, human-governed AI operations system for B2B purchase orders.**

**Architecture:** customer documents and emails → persistent intake → local Ollama document understanding → source-grounded review → authoritative customer, SKU, pricing, inventory and credit policies → role-based approval → idempotent, verified Odoo execution → archive and optional external sync → audit, recovery and actual evaluation.

> AI handles ambiguity. Software handles authority. ERP handles truth. Humans govern consequential exceptions.

## Install this release

**First read [`INSTALL-NEW-RELEASE.md`](INSTALL-NEW-RELEASE.md)** and follow [`docs/runbooks/ORDERNEXA_20260929_INSTALL_AND_FINISH.md`](docs/runbooks/ORDERNEXA_20260929_INSTALL_AND_FINISH.md). Applying the overlay to your running, backed-up project is safer than replacing the source tree. Neither archive includes `.env`, PostgreSQL/Odoo/MinIO volumes, n8n data or Ollama models.

```bash
cd ~/projects/ordernexa-ai
# Back up project and databases; overlay the downloaded patch as described in the runbook.
export COMPOSE_FILE=docker-compose.yml
docker compose config --quiet
docker compose up -d postgres redis minio minio-init api
docker compose exec -T api alembic upgrade head
curl --fail --max-time 20 http://127.0.0.1:8000/api/v1/health/ready
```

Local Operations Console: **http://127.0.0.1:8000/console/**. Provide the existing local role-specific operator key for restricted actions. Normal ingestion stays review-gated when model output or source evidence conflicts.

## What this release implements

- Existing multi-format document intake, audited transaction state, deterministic commercial checks, role-approved Odoo execution and recoverable **local** MinIO confirmations.
- Existing local Ollama integration with separate Windows-native text and vision models, confidence-format normalization, source-grounding, and human-verified review; **raw Qwen accuracy is not autonomous-release quality**.
- Extended responsive local frontend: Operations overview, transaction detail, approval and recovery, document review, integration/AI health, **durable automation jobs, explicit external-sync consent, voice change-request review, audit search and real evaluation report listing**.
- New PostgreSQL migration and optional low-memory **durable automation worker**: lease-based job queue, idempotent event ingress, safe partial recovery/reconciliation, real Graph transport/authorization helpers, S3/MinIO document persistence and optional **explicitly authorized** SharePoint, HubSpot, Teams-notification and *unsent* Outlook-draft operations.
- Three **inactive**, importable n8n workflow templates, a local source-grounded evaluation harness, a separate set of **500 generated UNCURATED DRAFT cases requiring human labeling**, and offline safety/contract tests.
- Guarded voice lookup and **review-only** change-request API for later Vapi wiring. No voice call can directly change or approve an order.

**What is not claimed complete:** verified live Microsoft/HubSpot/Vapi permissions and external behavior; Graph missed-notification delta resync; production OAuth/OIDC; an external-hosted frontend; measured 500-case accuracy; autonomous L4 execution; Stripe sandbox payment; full Ask Ops AI; or production rollout. Detailed evidence and remaining dependencies are in [`RELEASE-STATUS.md`](RELEASE-STATUS.md) and [`docs/architecture/20260929_BLUEPRINT_GAP_AND_EVIDENCE.md`](docs/architecture/20260929_BLUEPRINT_GAP_AND_EVIDENCE.md).

The API owns authoritative transaction state. n8n is transport/orchestration **only**. External writes remain off by default (`AUTOMATION_LIVE_WRITES=false`), and ambiguous remote results are quarantined rather than silently replayed.
