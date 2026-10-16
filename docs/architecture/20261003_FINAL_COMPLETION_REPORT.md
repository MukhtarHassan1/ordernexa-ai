# OrderNexa AI — final source completion report (2026-10-03)

## Design contract preserved

OrderNexa keeps the blueprint's core separation: AI handles ambiguity, deterministic services own authority, ERP remains system-of-record truth, and consequential exceptions stay human-governed. FastAPI/PostgreSQL own transaction state; n8n is a transport/orchestration surface rather than a hidden second state machine.

## Source-level completion in this patch

### Developer/release reliability

- API Dockerfile now has a `runtime` target and an opt-in `test` target containing `requirements-dev.txt`.
- Compose now exposes `api-tests` and `console-tests` only under the `test` profile.
- `scripts/test-all.sh` runs compose validation, backend tests, JavaScript tests and offline preflight in a repeatable sequence.
- `scripts/final-local-verify.sh` starts only the authoritative local core, waits for PostgreSQL, applies Alembic, verifies API readiness, runs tests and health checks without deleting volumes or enabling external writes.
- host preflight writes bytecode to `/tmp`, preventing the root-owned `__pycache__` permission problem caused by bind-mounted containers.
- evaluation validator now supports the JSON output contract already expected by preflight/CI.

### n8n

Five importable workflows are now supplied and remain inactive by default:

1. synthetic intake / replay smoke test;
2. authenticated generic intake bridge;
3. read-only KPI digest;
4. controlled external-sync scheduler that asks the backend to create guarded durable jobs rather than calling providers directly;
5. approval-notification scheduler that never becomes approval authority.

No secrets are embedded in workflow JSON. The two required Header Auth credentials are configured in n8n UI.

### Operations frontend

The existing same-origin Operations Console remains the canonical V1 frontend. It now explicitly covers the blueprint's required operational surfaces, including:

- Operations Overview;
- Transaction Inbox and Transaction Detail;
- dedicated Decision Inspector;
- Approval Center;
- Exception Workbench;
- Recovery Center;
- Document Intake / human review;
- Integration Health + AI Quality Lab;
- Model Routing / authority boundary;
- Policy & Autonomy;
- Ask Ops;
- Automation Queue;
- Voice Review;
- Audit Explorer;
- evidence-backed Release Readiness.

The new readiness page intentionally separates IMPLEMENTED, CONFIGURED, OBSERVED and VERIFIED states so the portfolio cannot accidentally present a token or configuration value as proof of a working external integration.

### AI quality

The 500-case generated dataset remains explicitly uncurated. A new curation-progress command reports reviewed vs pending cases without changing any labels. This prevents fabricated accuracy claims while making the path to the blueprint's 500-case quality gate operational.

## Verification performed in the packaging environment

- Python compile: PASS.
- Backend isolated unit/contract tests: **112 passed** using an import-only `asyncpg` stub because this packaging runtime has no Docker/PostgreSQL. The stub never returns fake database data.
- Node console tests: **10 passed**.
- n8n: five workflow JSON files parsed successfully, all inactive, node names unique.
- offline preflight: PASS.
- generated 500-case dataset: exactly 500 cases, all still marked human-review-required, release-claim-ineligible.
- Docker/live-provider execution was not possible in this packaging runtime because Docker is unavailable here.

## What still requires the owner

Only account/runtime evidence remains: real Docker database/Odoo/MinIO acceptance on the owner's machine, Microsoft/SharePoint/HubSpot/Teams/Outlook credentials and live tests, Vapi/Twilio call wiring, Stripe test account, production OIDC, n8n imported credential assignment/live executions, browser visual review, and human curation/model evaluation. These are not source-code omissions; they require external systems or human judgment.
