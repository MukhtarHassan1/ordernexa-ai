# OrderNexa External Live Setup — exact operator checklist

Use this **after** the development-completion patch and local test suite are clean. Do not paste credentials into ChatGPT or commit them to Git.

## A. Microsoft Entra / Graph

### A1. Create or reuse the Entra application

1. Microsoft Entra admin center -> App registrations -> select the OrderNexa app.
2. Record the Tenant ID and Application (client) ID locally.
3. Create a client secret and store it only in your private `.env` / secret manager.
4. Add the minimum application permissions required for the exact demo. Start with mailbox read only. Add send/write permissions only when that feature is about to be tested.
5. Grant admin consent only after reviewing the list.
6. Restrict mailbox access using Microsoft application access controls where available instead of granting unrestricted organizational mailbox access.

Set locally:

```dotenv
GRAPH_TENANT_ID=...
GRAPH_CLIENT_ID=...
GRAPH_CLIENT_SECRET=...
GRAPH_MAILBOX=orders@your-test-domain.example
GRAPH_CLIENT_STATE=<random 32+ character secret>
```

### A2. Public HTTPS callback

Graph cannot deliver production webhooks to `localhost`.

Expose the OrderNexa API through a controlled HTTPS endpoint and set:

```dotenv
GRAPH_NOTIFICATION_URL=https://YOUR_HOST/api/v1/automation/graph/notifications
GRAPH_LIFECYCLE_URL=https://YOUR_HOST/api/v1/automation/graph/lifecycle
```

Add `YOUR_HOST` to `TRUSTED_HOSTS`.

Do not expose the development console publicly.

### A3. Migration and worker

```bash
docker compose exec api alembic upgrade head
docker compose --profile automation up -d automation-worker
```

Keep `AUTOMATION_LIVE_WRITES=false` during read-only mailbox verification.

### A4. Create/inspect the Graph subscription

Use the OrderNexa Graph subscription management endpoint/CLI only after callback validation works. Creation/renewal is a real Microsoft write; the code requires explicit authorization and the external-write gate.

After you are ready:

```dotenv
AUTOMATION_LIVE_WRITES=true
```

Create the subscription, capture the returned Graph subscription ID, and persist it in `.env` if you want explicit pinning:

```dotenv
GRAPH_SUBSCRIPTION_ID=...
```

Restart API/worker after `.env` changes.

### A5. Verify delta recovery

The completed code stores a durable delta link. Test the failure case deliberately:

1. stop the worker temporarily;
2. send a test email to the authorized mailbox;
3. start the worker;
4. run/trigger delta recovery;
5. verify exactly one durable `GRAPH_MESSAGE` job exists for the message;
6. verify a duplicate notification/delta record does not create a second job.

Do not call Graph webhook delivery “reliable” until this recovery path has been demonstrated.

## B. SharePoint

1. Create/select one SharePoint site/library dedicated to the demo.
2. Use `Sites.Selected` instead of broad tenant-wide site access where possible.
3. Have a tenant admin grant the Entra app explicit access to that one site.
4. Obtain the target drive ID and set:

```dotenv
GRAPH_DRIVE_ID=...
```

5. Keep a synthetic transaction ready whose Odoo order is already verified.
6. Enable automation writes only for the controlled test window.
7. Queue SharePoint archive.
8. Verify the file exists remotely and OrderNexa read-back content hash matches the local confirmation.
9. Deliberately deny/revoke the site grant once in a test environment and verify the transaction becomes recoverable rather than recreating Odoo.

## C. HubSpot

1. Create a HubSpot private app in a sandbox/developer/test account.
2. Grant only contact/company scopes needed for the demo.
3. Copy the token into private `.env`:

```dotenv
HUBSPOT_ACCESS_TOKEN=...
```

4. Restart API/worker.
5. Use a synthetic customer with a verified domain/email.
6. Queue CRM sync.
7. Verify:
   - company identity is upserted by domain;
   - contact identity is upserted by verified email;
   - OrderNexa records stable external IDs;
   - read-after-write values match;
   - a second identical sync reuses the same identities.
8. Test a 401/403 by using an intentionally expired/revoked test token and confirm the provider circuit opens/operation blocks rather than retrying forever.

## D. Teams

The current design keeps OrderNexa as approval authority. Teams is notification/context, not the source of truth.

1. Create a test Teams/Power Automate/Workflow incoming webhook endpoint.
2. Put its URL in:

```dotenv
TEAMS_APPROVAL_WEBHOOK_URL=...
```

3. Queue a notification for a synthetic approval-required transaction.
4. Confirm the card/message contains transaction reference, PO, customer context, value/exception summary and link to OrderNexa.
5. Make the actual approval in OrderNexa, not by trusting an unsigned arbitrary Teams callback.

## E. Outlook customer confirmation

Keep:

```dotenv
CUSTOMER_EMAIL_ENABLED=false
```

while testing draft creation.

1. Create a draft for a synthetic completed transaction.
2. Open Outlook and inspect recipient, amounts, delivery details and transaction reference.
3. Verify OrderNexa reads back the draft ID.
4. Only after repeated sandbox checks, set `CUSTOMER_EMAIL_ENABLED=true` for an explicit approved-send test.
5. Use a test recipient you control.

## F. Vapi + Twilio

### F1. Generate the server secret locally

Generate a random 32+ byte value and set:

```dotenv
VOICE_SERVER_SECRET=...
```

Do not put it in a prompt.

### F2. Configure Vapi tools

Use `integrations/vapi/OrderNexa_Vapi_Tool_Contracts.json` as the contract.

Tool 1: safe status lookup

```text
GET https://YOUR_HOST/api/v1/automation/voice/status/{transaction_public_id}
Header: X-OrderNexa-Voice-Secret: <secret>
```

Tool 2: change request

```text
POST https://YOUR_HOST/api/v1/automation/voice/change-request
Header: X-OrderNexa-Voice-Secret: <secret>
```

The assistant prompt must state that it cannot modify an ERP order, approve discounts/credit, change payment destination or issue refunds. A requested change becomes `PENDING_VERIFICATION` in Voice Review.

### F3. Connect Twilio to Vapi

1. Buy/use a test-capable Twilio number.
2. Connect it to Vapi according to the Vapi/Twilio account UI.
3. Call the number yourself.
4. Ask for a transaction status using a synthetic transaction ID.
5. Request a quantity/date change.
6. Verify OrderNexa created exactly one Voice Review request and Odoo was unchanged.

## G. Stripe sandbox (optional V1.5)

Only test mode is accepted by the adapter.

```dotenv
STRIPE_ENABLED=true
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

1. Configure a test webhook to `https://YOUR_HOST/api/v1/payments/stripe/webhook`.
2. Create Checkout only for a synthetic transaction whose amount/currency are authoritative in OrderNexa.
3. Verify the returned session starts with `cs_test_`.
4. Complete a Stripe test payment.
5. Verify webhook signature, test-mode flag, transaction reference, amount and currency all pass before OrderNexa records payment verification.
6. Never use the adapter with a live key.

## H. Production OIDC/RBAC

Local role keys are for development only.

For deployment set:

```dotenv
APP_ENV=production
AUTH_MODE=oidc
OIDC_ISSUER=...
OIDC_AUDIENCE=...
OIDC_JWKS_URL=...
OIDC_ROLE_MAP_JSON={"OrderNexa.Sales":"SALES_MANAGER","OrderNexa.Finance":"FINANCE_MANAGER","OrderNexa.Operations":"OPERATIONS_MANAGER","OrderNexa.Admin":"ADMIN","OrderNexa.Auditor":"AUDITOR"}
```

1. Create application roles/groups in your identity provider.
2. Assign a test user to one role at a time.
3. Verify signed JWT issuer/audience/algorithm/JWKS validation.
4. Verify Finance cannot perform Admin-only policy mutation.
5. Verify Auditor cannot execute external writes.
6. Verify production startup/API fails closed when OIDC is incomplete.

## I. n8n — intentionally postponed

Do not continue until all local development/migration/tests above are complete.

When you return to n8n, resume exactly where you stopped: configure Header Auth using `N8N_INGEST_SECRET`, execute Workflow 01 once, execute the exact same event again, and confirm durable event deduplication before testing Workflows 02/03.
