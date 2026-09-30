# September 29 integration development changelog

Basis: the actual `OrderNexa_Full_Backup_20260929_0031.zip` uploaded with the master blueprint and canonical PO sample. All previous source-grounding, model-routing and human-review fixes are retained rather than regenerated blindly.

### New backend and schema

- New `20260929_auto` Alembic migration for PostgreSQL-persisted automation jobs and *non-executing* voice change requests.
- Optional `automation-worker` profile: PostgreSQL SKIP LOCKED leases, durable source checksums, event-level idempotency, bounded retry for safe transient errors, and quarantine/reconciliation for uncertain remote writes.
- Authenticated n8n intake, basic Microsoft Graph message/lifecycle webhook processing, source saved to MinIO before AI execution, persistent audit traces, restricted Vapi read-only status and human-only review requests.
- Optional policy-gated external operations only after local verified Odoo + MinIO completion: SharePoint same-path upload and actual byte readback, HubSpot verified email/contact readback, Outlook unsent draft/readback then separate two-confirmation operator send of *existing* draft, Teams *informational* notification ACK.

### Updated local frontend

- Existing live Operations Console enhanced with durable job queue, per-transaction external-sync authorization, audit inspector, real evaluation-report list, voice request human review, role-aware ERP/archive next-step buttons, source-artifact review jump and Outlook draft preview/send warning.
- Retained existing human-review workflow and safeguards rather than allowing Qwen guesses to execute pricing, credit or ERP writes.

### Automation/quality documentation

- Three **inactive** n8n JSON templates: synthetic authenticated ingress, authenticated local webhook bridge, real KPI read-only digest.
- 500 **uncurated generated synthetic draft** evaluation cases are provided for independent human curation; not measured results or a substitute for the blueprint's 500 labeled evaluation target.
- Updated dev CI to compile and run offline Python/Node tests and check n8n templates/draft count.
- Detailed install, blueprint-to-evidence, security and 4–6 minute real-demo acceptance documents.

### Verified source checks; pending runtime gates

- 89 offline Python tests passed with mocked dependencies using a stub for `app.db.session` (the local build container lacks `asyncpg`; the user's Docker image installs it), 8 Node UI tests passed, Python and JS syntax/Compose/n8n JSON passed.
- No independent access to the user's running WSL/Windows Ollama/Docker or external OAuth accounts; **no** claim of production-ready or fully completed 38-page scope. Consult `RELEASE-STATUS.md` for remaining acceptance gates.
