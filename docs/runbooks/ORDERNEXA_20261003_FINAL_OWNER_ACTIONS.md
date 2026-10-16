# OrderNexa — final owner-only actions

Do these **after** the final patch is overlaid and local tests are green. Do not paste secrets into chat or commit `.env`.

## 1. Local authoritative acceptance

Use the memory-friendly core first:

```bash
cd ~/projects/ordernexa-ai
bash scripts/core-up.sh
bash scripts/final-local-verify.sh
```

Then start Odoo and rerun the already documented exactly-once + recovery scenario:

```bash
bash scripts/odoo-up.sh
```

Acceptance evidence must show one verified Odoo order, a deliberate downstream failure, DEGRADED state, recovery to COMPLETED, and the Odoo order count still exactly one.

## 2. n8n

```bash
bash scripts/n8n-up.sh
```

Open `http://127.0.0.1:5678`, import all five JSON files under `workflows/n8n/`, then create:

- Header Auth `OrderNexa Ingest` -> `X-OrderNexa-Ingest-Secret` = your private `N8N_INGEST_SECRET`;
- Header Auth `OrderNexa Operator` -> `X-OrderNexa-Operator-Key` = an operations/admin development key;
- a separate n8n Basic Auth credential for workflow 02 webhook.

Keep workflows inactive while testing. Execute workflow 01 once, repeat the identical event and confirm dedupe, then reuse the same event ID with changed content and confirm HTTP 409. Test workflow 03 against the API KPI values. Only after a real local completed transaction has verified Odoo + MinIO evidence should you run workflow 04. Workflow 05 is notification only; approval stays in OrderNexa.

## 3. Microsoft Graph + SharePoint + Outlook + Teams

You must provide a real Entra app and test tenant/account. Configure `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `GRAPH_MAILBOX`, a random 32+ char `GRAPH_CLIENT_STATE`, and public HTTPS notification/lifecycle URLs. Keep least privilege and mailbox/site scoping.

Create/renew the durable Graph subscription through OrderNexa, test a real email attachment, then deliberately miss a webhook and prove delta sync recovers the message exactly once. For SharePoint use `Sites.Selected`, set `GRAPH_DRIVE_ID`, upload a synthetic confirmation and verify remote read-back bytes/hash. For Outlook first create/read back an **unsent draft** with `CUSTOMER_EMAIL_ENABLED=false`. For Teams verify both HTTP acknowledgement and actual channel display; Teams never becomes approval authority.

## 4. HubSpot

Create a sandbox/private app with only required company/contact scopes. Set `HUBSPOT_ACCESS_TOKEN`. Use a synthetic verified domain/email, run company/contact upsert, verify stored remote IDs and read-after-write values, then repeat the same sync and confirm identities are reused. Revoke the token once in a test and confirm the operation fails/circuits instead of retrying forever.

## 5. Vapi + Twilio

Set a random 32+ char `VOICE_SERVER_SECRET`. Configure the Vapi tools from `integrations/vapi/OrderNexa_Vapi_Tool_Contracts.json`, expose only the guarded status/change-request routes, connect a Twilio test number, then make a real call. Prove status lookup works and a requested change creates one `PENDING_VERIFICATION` Voice Review record while Odoo remains unchanged.

## 6. Stripe sandbox

Use test mode only:

```dotenv
STRIPE_ENABLED=true
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

Create a checkout session only from an authoritative OrderNexa transaction, complete a Stripe test payment and prove webhook signature + test-mode + transaction reference + amount + currency all match before `PAID` is stored.

## 7. Production OIDC/RBAC

For public deployment use `APP_ENV=production`, `AUTH_MODE=oidc`, real issuer/audience/JWKS and role mapping. Test each role separately: Admin/Operations/Sales/Finance/Auditor. Verify invalid issuer/audience/signature fails closed and Auditor cannot execute external writes.

## 8. Curate the 500-case quality set

Generated labels are not gold labels. Track progress with:

```bash
python3 evals/runners/curation_progress.py \
  evals/datasets/generated_draft_500_REQUIRES_REVIEW.jsonl
```

A human must inspect/correct each case and explicitly clear its review flag. Only then run the evaluation runner and use measured accuracy/safety/latency results in the AI Quality Lab. Do not enable broad L4 autonomy before the configured quality and recovery gates pass.

## 9. Browser/demo release

Open `http://127.0.0.1:8000/console/`, verify every navigation screen at desktop and narrow widths, inspect the Release Readiness matrix, and capture only real evidence. The final 4–6 minute demo should use one transaction across intake -> evidence -> approval -> Odoo -> downstream sync -> voice -> deliberate failure -> recovery -> KPI/quality views.
