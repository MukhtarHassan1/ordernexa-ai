# OrderNexa 2026-10-02 — development completion hardening

## Added

- business-order identity and explicit amendment/revision model;
- cross-transaction Odoo idempotency for newly hardened transactions;
- legacy duplicate-history protection;
- persisted integration circuit breakers and explicit failure taxonomy;
- automation job correlation IDs, lease fencing, heartbeat and uncertain-state quarantine;
- Graph subscription persistence, renewal support, lifecycle state and delta recovery;
- deeper HubSpot company/contact identity verification;
- scoped knowledge documents/chunks and effective-date/customer retrieval;
- production OIDC/JWT authentication boundary and role mapping;
- request safety middleware, rate limiting, security headers and trusted-host enforcement;
- per-action progressive autonomy controls;
- constrained read-only Ask Ops endpoint/UI;
- optional Stripe test-mode-only payment workflow;
- Exception Workbench, governance and integration/AI quality UI improvements;
- Vapi tool contract and external live-setup runbooks;
- safe startup/health/release scripts;
- new hardening/evaluation/security tests.

## Preserved intentionally

- existing private `.env` and passwords;
- named Docker volumes;
- Odoo database/data;
- n8n database and encryption key;
- Windows-native Ollama development architecture;
- existing canonical transaction/audit history;
- existing n8n workflow JSON files (live n8n testing remains postponed).

## Verification in packaging environment

- Python compilation: pass;
- backend isolated unit/contract tests: 109 passed;
- Node console tests: 8 passed;
- JSON/YAML structural validation: pass;
- Alembic single head: `20261002_hardening`.

No external live integrations were exercised in the packaging environment.
