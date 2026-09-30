# OrderNexa — ordered installation and completion runbook

**Applies to:** your September 29 latest source backup on **Windows 8 GB / WSL Ubuntu**, current `~/projects/ordernexa-ai` directory, Docker Desktop, Windows-native Ollama at `http://host.docker.internal:11434`. Your personal `.env` and named Docker volumes are **not** supplied and must be preserved. Apply steps **in order**. External integrations are opt-in; do NOT expose the private development Console publicly.

**Expected current local AI evidence:** the user's Qwen 1.5B extracted the canonical PO with **7/10 raw** critical checks and **10/10 source-grounded** checks in one live test, and correctly demanded human review. Grounded correction is not a claim of better raw AI quality. The canonical PO source is `sample-data/purchase-orders/po-88192-upload.txt`. It states September 30, 2026, Northstar Engineering, Manchester, XTR-42 (40×£260 requested) and BRK-90 (15×£165 requested). Customer domain isn't in the source; never invent one. Live business-reference expectation from previous seed: **£13,995 / APPROVAL_REQUIRED**, which must be reverified.

## A. Apply only the overlay and migrate — you do these first

**1. Protect existing source and live data.** In Ubuntu:

```bash
cd ~/projects/ordernexa-ai
mkdir -p "$HOME/ordernexa-backups"
chmod 700 "$HOME/ordernexa-backups"
# This tar stays private and includes your .env (which contains credentials).
tar -czf "$HOME/ordernexa-backups/pre-20260929-$(date +%Y%m%d-%H%M).tar.gz" \
  --exclude='ordernexa-ai/.git' --exclude='ordernexa-ai/.venv' \
  --exclude='ordernexa-ai/node_modules' --exclude='*/__pycache__' \
  -C "$HOME/projects" ordernexa-ai
# Make an OrderNexa DB dump; never paste its contents into chat.
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  > "$HOME/ordernexa-backups/ordernexa-20260929-preupgrade.sql"
ls -lh "$HOME/ordernexa-backups" | tail -5
```

A project ZIP or PostgreSQL SQL dump alone does **not** back up Odoo, n8n, MinIO or Docker Ollama volumes. For a full disaster-recovery archive, also export the Odoo and n8n databases and MinIO objects using your authorized service accounts before any potentially risky changes. Do **not** delete named volumes or reseed. If `pg_dump` returns an error, stop and fix backup access before continuing.

**2. Verify and extract patch.** The patch has paths relative to your existing project root; the larger source ZIP includes a parent `ordernexa-ai/` folder and is for clean reference only:

```bash
PATCH='/mnt/c/Users/Hammad/Downloads/OrderNexa_20260929_Upgrade_Patch.zip'
test -f "$PATCH" && unzip -tq "$PATCH" || { echo 'Patch missing or invalid; STOP'; exit 1; }
cd ~/projects/ordernexa-ai
unzip -o "$PATCH" -d .
export COMPOSE_FILE=docker-compose.yml
docker compose config --quiet
```

Preserve your real `.env`. `.env.example` is a reference, not an instruction to overwrite existing secrets. Old ancillary patch READMEs are historical, not the current installation instructions.

**3. Confirm private local config without printing keys.** Keep existing `AI_PROVIDER=ollama`, `OLLAMA_BASE_URL=http://host.docker.internal:11434`, `OLLAMA_TEXT_MODEL=qwen2.5:1.5b` (provided Windows Ollama already has it), the current vision model and the existing timeout settings. Make sure your existing role-specific operator keys still work. Append **one instance** of each new env field only when you're ready:

```dotenv
# New optional durable queue; starting safe defaults:
AUTOMATION_WORKER_ENABLED=false
AUTOMATION_LIVE_WRITES=false
AUTOMATION_MAX_ATTEMPTS=5
N8N_INGEST_SECRET=
GRAPH_CLIENT_STATE=
GRAPH_SUBSCRIPTION_ID=
GRAPH_TENANT_ID=
GRAPH_CLIENT_ID=
GRAPH_CLIENT_SECRET=
GRAPH_MAILBOX=
GRAPH_DRIVE_ID=
TEAMS_APPROVAL_WEBHOOK_URL=
HUBSPOT_ACCESS_TOKEN=
VOICE_SERVER_SECRET=
CUSTOMER_EMAIL_ENABLED=false
```

If an existing `.env` contains an overlapping setting, **edit it** instead of appending duplicates. Generate *independent* random secrets inside your own WSL terminal (`python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`) and never include them in screenshots or chat. Keep all external writes off for now.

**4. Start minimum dependencies and run the NEW migration before accessing automation:**

```bash
cd ~/projects/ordernexa-ai
export COMPOSE_FILE=docker-compose.yml
docker compose up -d postgres redis minio minio-init api
docker compose exec -T api alembic current
docker compose exec -T api alembic upgrade head
docker compose exec -T api alembic current
curl --fail --max-time 20 http://127.0.0.1:8000/api/v1/health/ready
```

Expected Alembic current head: `20260929_auto`. The migration **creates two new tables** (automation jobs and human-reviewable voice requests); it does not delete your previous transaction schema. If migration fails, **STOP**. Do not drop DBs, rerun seed scripts or use `docker compose down -v`. Debug with `docker compose logs --tail=100 api postgres` (remove secrets if sharing).

**5. Test backend and browser basics:**

```bash
docker compose exec -T api python -m compileall -q app
docker compose exec -T api python -m pip install -r requirements-dev.txt
docker compose exec -T api python -m pytest -q tests
curl --fail --max-time 20 -I http://127.0.0.1:8000/console/
```

The source build's 89 tests passed *offline with mocks and unavailable asyncpg stub*; run the ordinary test suite **inside your actual Docker API** to establish real local dependency compatibility. The pip step is temporary in the running container; you may have to reinstall test extras after an API image recreate unless you build a dev image. In Windows open `http://localhost:8000/console/`, hard-refresh (`Ctrl+Shift+R`), configure your local **operations-manager** key and inspect Automation queue, Audit explorer, AI reports, and existing Transactions. Leave Docker Ollama stopped if Windows-native Ollama is the configured host.

## B. Prove existing local transaction before enabling external automation

**6. Resume, don't reupload, the canonical document.** Your earlier saved source artifact reference was `5c5bf862-30c1-40c1-a1f2-4b59f37ef015`. Inspect existing transactions and/or this saved artifact in the Console's Document intake. If the original exists, select **Check status → Download original → Preview for human review → verify every field → Confirm & validate**. Only upload the sample once if there is no existing saved source/transaction. Disagreeing AI fields must require explicit human review and must not be displayed as automatic extraction success.

**7. Business validation evidence:** Inspect the exact transaction (record its *real* public ID). The reference case must resolve authoritative customer/SKUs XTR-420/BRK-090, contract pricing, warehouse availability and credit, and should report £13,995 / `APPROVAL_REQUIRED` against the same seeded dataset. The source customer's requested prices are **not** executable contract prices. If expected amount/status differs, check actual DB agreements, SKU alias data and review flags; do not manually insert £13,995 into the output.

**8. Role approvals and local Odoo:** Use SALES_MANAGER for sales exception and FINANCE_MANAGER for credit exception as prompted by the real approval records; never bypass the policy. Start Odoo only when needed, e.g. free 8 GB RAM by asking Windows Ollama to unload idle models if inference is finished, then:

```bash
docker compose up -d odoo-db odoo
# Then use the approved transaction's ERP action in the Console.
```

The transaction must reach `READY` before creating the Odoo order. Verify the Odoo GET/readback and original external ID, then invoke the **same** authorized ERP operation again to confirm idempotency (`replayed`, not a second order). Use existing explicit ERP retry only after investigating uncertainty.

**9. Local archive and recovery:** On the existing ERP_CREATED transaction, trigger an **intentional local archive failure only in the authorized test scenario**; observe DEGRADED and the original external ERP ID. Resume **the archive step**, not ERP creation, from the Recovery center and inspect the stored confirmation in MinIO. This is local MinIO recovery; it is **not** proof of SharePoint archival. Capture these results for your Upwork demo.

## C. Activate the durable queue and import n8n (no external writes)

**10. Start the optional low-memory worker** only after migration and local tests. Set `AUTOMATION_WORKER_ENABLED=true` in your private `.env` but keep `AUTOMATION_LIVE_WRITES=false`, then recreate the API (so its configuration page sees the new settings) and start the optional worker:

```bash
export COMPOSE_FILE=docker-compose.yml
docker compose up -d --no-deps --force-recreate api
docker compose --profile automation build automation-worker
docker compose --profile automation up -d automation-worker
docker compose --profile automation logs --tail=70 automation-worker
```

Open the Console's **Automation queue** with an OPERATIONS_MANAGER key. The queue uses real PostgreSQL rows; the UI must not show a job as completed merely because it was enqueued. A restarted worker that lost an in-flight external write deliberately sets `BLOCKED_UNCERTAIN` so you can investigate and reconcile instead of duplicating side effects.

**11. Import the three n8n templates** using `http://localhost:5678` after `docker compose up -d n8n-db n8n` if memory permits. From the repo's `workflows/n8n/` folder import the inactive JSONs one at a time in n8n UI: `01_Manual_Synthetic_Intake` for duplicate test; `02_Authenticated_Intake_Bridge` for your own authenticated local webhook; `03_Readonly_KPI_Digest` for real stored metric reads. The templates are inactive deliberately. Configure the HTTP Request node **Header Auth** credential with header `X-OrderNexa-Ingest-Secret` and the same secret as your local `N8N_INGEST_SECRET`; configure the inbound n8n webhook's **separate Basic Auth** credentials. The configured URL `http://api:8000/api/v1/automation/n8n/intake` works only when n8n shares the Compose network. Set n8n execution-history retention to avoid storing raw customer documents or request secrets. Verify one synthetic ingress returns HTTP **202** and a durable job ID, then repeat the same event ID and payload: **same** job ID / no second transaction; same event ID with modified PO must be **409**. If n8n import node versions differ, use the UI to remap fields rather than activating an unreviewed workflow. Do **not** use the synthetic template's fixed example event ID for real production email.

**12. Validate new intake asynchronously:** For an approved, privately created test document, call the new n8n webhook once and inspect Automation queue. If Qwen conflicts with a source field, `REVIEW_REQUIRED` is **correct**, and the original remains in local MinIO. Review the saved artifact in the Console; do not modify job payloads, directly update DB status or reupload to force acceptance. Recorded n8n acceptance is not proof of real Outlook email intake.

## D. Real Microsoft/HubSpot external accounts — tasks you must do

**13. Obtain Entra/Exchange/SharePoint permissions from YOUR admin** (not possible from an offline source ZIP). Create a dedicated confidential app with application `Mail.Read` for the specified mailbox; add `Mail.ReadWrite` only if enabling unsent draft creation, and `Mail.Send` only after operator-approved customer sending is in scope. Use Exchange app-access scoping/RBAC; request `Sites.Selected` plus grant to the one site hosting an `OrderNexa/` folder in the selected SharePoint drive. Record the actual tenant/app/drive IDs and secret locally. Set `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `GRAPH_MAILBOX`, `GRAPH_DRIVE_ID`. Do not paste app credentials into chat; a Microsoft 365 admin must give consent and site/mailbox grants.

**14. Publish a restricted Graph callback** if you want live mailbox automation: Microsoft Graph cannot call `localhost` or `host.docker.internal`. Arrange an authenticated, route-limited public HTTPS proxy exposing **only** `/api/v1/automation/graph/notifications` and `/api/v1/automation/graph/lifecycle`; keep the console, docs and all operator paths private. Set `GRAPH_CLIENT_STATE` to a new random 32+ character secret and recreate API/worker for the env to take effect. In API container, only after admin setup and proxy validation:

```bash
docker compose exec -T api python -m app.automation.manage_graph \
  --create https://YOUR-AUTHORIZED-HTTPS-DOMAIN/api/v1/automation/graph/notifications
```

Save the **real** returned subscription ID in `GRAPH_SUBSCRIPTION_ID`, recreate both processes and test with **a new authorized email** (never assume the old PO from manual testing is a fresh Graph notification). Record event-to-source-artifact and dedupe. Before subscription expiry, renew explicitly:

```bash
docker compose exec -T api python -m app.automation.manage_graph --renew YOUR_REAL_SUBSCRIPTION_ID
```

The CLI supports `--status ID`. Current basic webhook handlers do **not** automatically resubscribe or perform Graph delta reconciliation for missed messages. If a `GRAPH_LIFECYCLE` job appears, investigate manually before claiming no emails were missed.

**15. Enable individual external destinations cautiously.** Set a valid HubSpot private app token (contacts read/write), verify its account and API scopes, and configure Teams Workflows inbound HTTPS URL if authorized. Only after **local** COMPLETED + VERIFIED Odoo **and** VERIFIED MinIO archive, test each integration separately: SharePoint first (same path / actual byte readback), then HubSpot (a **human-confirmed recipient email** / remote contact GET), then optional informational Teams webhook, then **unsent** Outlook draft (real authorized mailbox/verified email and Mail.ReadWrite). For each action, explicitly check the Console's external-data-transfer checkbox. Only set `AUTOMATION_LIVE_WRITES=true` once the necessary permissions and identities have been reviewed; recreate API/worker. Record external IDs and fetch the remote object before marking a connector accepted. Do not enable all connectors simultaneously on the first live test.

**16. Send email only as an entirely separate human decision.** An Outlook draft by itself sends nothing. When/if real customer email sending is authorized and the app has Mail.Send, set `CUSTOMER_EMAIL_ENABLED=true`, recreate API, open the job's **live Outlook preview** in Automation queue, independently confirm the verified recipient and the exact content hash, explicitly approve the action. On Graph acknowledgment, **inspect Outlook Sent Items**, since 202 is not proof of delivery. If the request times out, do not press Send again; a pending/uncertain send must be manually reconciled. Use test mailbox recipients for initial demo.

## E. Voice, AI quality, security and portfolio closure

**17. Voice cross-channel feature (V1.5, not a working phone agent yet):** Set a separate 32+ character `VOICE_SERVER_SECRET`. Configure only the two guarded server tool endpoints in your own Vapi account through a separate TLS reverse-proxy route: `GET /api/v1/automation/voice/status/{public_id}` for broad redacted status, and `POST /api/v1/automation/voice/change-request` with `X-OrderNexa-Voice-Secret` and schema-required `event_id`, `call_id`, `transaction_public_id`, `request_type`, `request_note`. The voice agent must tell callers it cannot verify identity or change orders by itself. Configure Twilio/Vapi telephony only if you control appropriate phone access. Verify the request appears in **Voice review**; a real person verifies identity and acknowledges/declines it. No script here pretends that Vapi/Twilio are already connected.

**18. Evaluate rather than guess model accuracy.** The repo retains the existing manually labeled small dataset and generated `evals/datasets/generated_draft_500_REQUIRES_REVIEW.jsonl`; the latter is **500 draft synthetic examples, not 500 independently verified gold labels**. A person must inspect, reject or correct every draft before counting it as a curated evaluation set. Run the existing `evals/runners/eval_local_ollama.py` with a small 5-case batch first on your 8 GB machine; allow model cold start and record real latency. Review the Console's measured AI Quality reports; compare raw-model and source-grounded accuracy and explicitly count human-review escalation and prompt-injection failures. The current user-observed **7/10 raw** on one PO does **not** qualify for autonomous L4. Keep approval guards enabled until diverse evaluations meet agreed criteria.

**19. Production-bound tasks not supplied by a source patch:** externally hosted SSO/OAuth/OIDC replacing local demo keys, restricted secret rotation, durable backups/restore drills, webhook/public route controls, release/CI deployment, Graph missed-event delta recovery, cross-app rollback/fault injection, full Next.js dashboard if required, actual live Teams interactive approvals, Stripe sandbox and Ask Ops AI. These require deliberate subsequent builds/account access, not just toggling `.env` flags. Consult `docs/architecture/20260929_BLUEPRINT_GAP_AND_EVIDENCE.md` and `docs/security/20260929_INTEGRATION_SECURITY.md`.

**20. Film a truthful 4–6 minute Upwork demonstration** only after actual acceptance: one real source document with an AI/source conflict, authorized human-reviewed PO, evidence-grounded customer/SKU/pricing/inventory/credit, role approval, a single verified Odoo external ID, local MinIO failure/recovery without duplicate ERP writes, actual queue timeline, actual AI Quality result. Include external Graph/SharePoint/HubSpot/Teams and voice scenes **only after** those exact live integration tests pass. No hard-coded business figures or staged connectors represented as live production services.

## If a stage fails

- **API/DB migration:** `docker compose logs --tail=100 api postgres`, `docker compose exec -T api alembic current`; STOP before any reseeding/reset. Be alert to the `COMPOSE_FILE` setting so you don't run a different Compose file.
- **Windows-native Ollama:** keep Docker Ollama stopped; use the already verified `host.docker.internal` address. Check the text model installed on Windows and the config in the API container. Do not treat HTTP `/api/tags` 200 as successful model generation; use the real inference probe.
- **User's Docker RAM:** don't run Windows Ollama inference, Odoo, n8n and large evaluation concurrently on 8 GB. Prefer Stage A/B minimal containers, then run the optional worker and only one additional integration at a time.
- **Unsafe retries:** `BLOCKED_UNCERTAIN` means **inspect the remote side effect first**. Use the job's **Reconcile** path with investigation notes; never directly edit its status in SQL or repeatedly click an ERP/Outlook action.
- **Unknown artifact status:** inspect the saved original rather than reupload. A required human review is a deliberate safety gate, not automatically an error.

**Definition of done for V1:** A *real* authorized email/document can be received (once), grounded and reviewed or safely auto-accepted when policy/evaluation permits, validated commercially, approved as necessary, create exactly one verified ERP order, archive and synchronize real permitted downstream state, recover from injected partial failure without replaying ERP, and show actual trace, business KPI and quality data. New source files alone do not satisfy this definition.
