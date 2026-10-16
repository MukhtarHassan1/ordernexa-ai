# OrderNexa n8n workflows

These workflows make n8n a **transport/orchestration layer only**. FastAPI/PostgreSQL remain the source of truth and all consequential writes are guarded by the backend.

## Import order

1. `OrderNexa_01_Manual_Synthetic_Intake.json` — deterministic smoke test and duplicate replay.
2. `OrderNexa_02_Authenticated_Intake_Bridge.json` — authenticated generic email/web envelope bridge.
3. `OrderNexa_03_Readonly_KPI_Digest.json` — read-only metrics, no generated claims.
4. `OrderNexa_04_Controlled_External_Sync.json` — schedules backend-owned SharePoint/HubSpot/Outlook/Teams jobs for a locally completed transaction.
5. `OrderNexa_05_Approval_Notification.json` — queues approval context notification; it never grants approval.

All templates ship **inactive**. This is deliberate.

## Credentials to create in n8n

Create two credentials in n8n UI; do not put secrets in workflow JSON.

- Header Auth `OrderNexa Ingest`
  - Header name: `X-OrderNexa-Ingest-Secret`
  - Value: the same private `N8N_INGEST_SECRET` from OrderNexa `.env`.
  - Assign it to the HTTP Request nodes in workflows 01 and 02.

- Header Auth `OrderNexa Operator`
  - Header name: `X-OrderNexa-Operator-Key`
  - Value: an operations-manager/admin development key from your private `.env`.
  - Assign it to workflows 04 and 05.

Workflow 02 also uses n8n **Basic Auth** on its webhook. Create a separate n8n webhook credential for that inbound boundary.

## Acceptance sequence

Keep `AUTOMATION_LIVE_WRITES=false` initially.

1. Execute workflow 01 once. OrderNexa must return one durable `N8N_DOCUMENT` job.
2. Execute the exact same event again. It must reuse/deduplicate rather than create a second business side effect.
3. Change the body while keeping the same `event_id`. OrderNexa must reject it with HTTP 409.
4. Run workflow 03 and compare the output with `/api/v1/ops/overview`; values must match because n8n does not invent KPIs.
5. After a real locally `COMPLETED` transaction has verified Odoo + MinIO evidence, use workflow 04. With live writes disabled, jobs may queue but the worker must not perform remote writes.
6. Use workflow 05 only for a transaction currently in `APPROVAL_REQUIRED`. The notification is informational; make the actual decision in the protected OrderNexa Approval Center.

Only activate production-like schedules/webhooks after these acceptance tests pass and execution-retention/privacy settings are reviewed.
