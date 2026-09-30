# OrderNexa — 2026-09-29 source integration release status

**Evidence basis:** user-provided `OrderNexa_Full_Backup_20260929_0031.zip`, the 38-page NECTELIS master blueprint and PO-88192 sample. This source build does **not** alter or access the user's live WSL database, Windows Ollama installation, Odoo objects or external accounts.

| Area | Code available in this source | Known verification boundary |
|---|---|---|
| Existing transaction, domain, approval and Odoo workflows | Typed models, stage transitions, authoritative lookup/pricing/stock/credit, role-gated approvals, Odoo idempotency and local MinIO recovery | User previously verified Stage 2 scenario and bootstrap, but this new release cannot assert current live Odoo state. |
| Source-grounded AI document intake | Multi-format extraction, model routing, confidence anomaly detection, source evidence and human verification; source preserved | User's real Qwen 1.5B run: **raw 7/10** and **grounded 10/10** on one PO; review remained mandatory. This is NOT a population quality metric. |
| Backend durable integration automation | New schema/migration, idempotent queue, optional worker, failure isolation and manual proof-based reconciliation | Unit/contract tested offline. New migration/worker must be exercised in the user's actual PostgreSQL/Docker environment. |
| n8n and Microsoft Graph | Signed/shared-secret n8n ingestion, email subscription webhook/lifecycle handlers, basic Graph app-only helpers, three inactive n8n JSON workflow templates | No live Entra administrative grant, publicly reachable HTTPS Graph webhook, verified real email or live imported n8n workflow yet. No delta resync implementation. |
| Optional downstream | Verified local completion required before SharePoint archive, HubSpot contact, unsent Outlook draft or informational Teams notification; preview-and-authorize a one-time send of an existing draft | All external writes default OFF. Real permissions, HTTPS, verified recipients, consent, live read-after-write and Outlook Sent Items still user-tested tasks. Notifications acknowledged by transport are not confirmed displayed. |
| Frontend | Extended locally served responsive UI for transactions, human review, local approvals/recovery, durable jobs, voice review, audit and real eval reports | JavaScript static/Node tests passed. No visual/browser integration or production Next.js/SSO claim. |
| Vapi | Restricted voice lookup and human-verified request creation; voice cannot execute changes | Vapi/Twilio wiring and caller identification require accounts, route-specific HTTPS and real calls. |
| AI evaluation | Existing labeled synthetic evals, source-grounded/raw separation; 500 synthetic **uncurated draft** cases generated for *human label review* | 500 uncurated draft cases do not satisfy the blueprint's 500 curated scored cases; 97%/98% accuracy goals NOT measured. |
| Security/recovery | Existing localhost-only operator keys, policy checks, durable queue, bounded retries/quarantined uncertain external writes and readback on supported actions | Operator keys are not production OAuth. Real DR backup/restore, Microsoft delta recovery and broad fault injection remain. |

## Offline verification actually performed

- Python source compilation: passed.
- Docker Compose YAML parse: passed (Docker daemon/WSL runtime not available in this build environment).
- n8n JSON structural parse: passed; n8n UI import/credential and live webhook tests not performed.
- Python unit/contract suite: **89 passed** with an in-memory replacement for `app.db.session` because this build sandbox lacks `asyncpg`. All external I/O was mocked; run ordinary pytest in the user's Docker API, which installs the pinned driver.
- JavaScript Node contract suite: **8 passed**; `app.js`, `automation.js` and review JS syntax validated.
- Generated evaluation draft: exactly **500 parseable JSONL cases**, explicitly uncurated/unscored.
- **Not verified here:** a live Alembic migration, Docker build, Windows-native Ollama extraction after this code change, Graph/SharePoint/HubSpot/Outlook/Teams actions, Vapi calls, browser rendering, production auth and full end-to-end acceptance.

## Safety and completion gates

1. Preserve existing `.env` and named volumes; back up database/MinIO/n8n *separately* and run the new Alembic migration without reseeding.
2. Prove the **existing** PO-88192 (do not repeatedly reupload): verified human review → expected **GBP 13,995 / APPROVAL_REQUIRED** against actual seeded data → authorized sales/finance decisions → exactly one verified Odoo order → local archive and deliberate downstream failure/recovery.
3. Opt in to worker with `AUTOMATION_WORKER_ENABLED=true`; leave `AUTOMATION_LIVE_WRITES=false` until the core local workflow is verified. Check job states and manual reconciliation.
4. Import and credential *inactive* n8n templates; verify event deduplication and existing-artifact review. Add Graph subscription only after the administrator supplies permissions and a route-limited publicly reachable HTTPS callback.
5. Opt in to individual external actions with verified identities/recipients, trace logs and remote readback. Separate Outlook draft verification from human-authorized sending; check Sent Items.
6. Conduct actual measured, **curated** multi-document AI evaluation plus prompt-injection, unauthorized-action, duplicate and recovery tests before widening autonomy.

See `docs/runbooks/ORDERNEXA_20260929_INSTALL_AND_FINISH.md` for exact commands and the human/external-account responsibilities.
