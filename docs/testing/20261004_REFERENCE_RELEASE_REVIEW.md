# OrderNexa AI — full source review and reference-release hardening

Date: 2026-10-04  
Reviewed source: `OrderNexa_Current_20261004_0109.zip`  
Blueprint basis: 38-page Autonomous Customer-to-Cash master project blueprint supplied with the review.

## 1. Executive assessment

The supplied project already had a substantial production-style core: a FastAPI/PostgreSQL transaction digital twin, deterministic business authority, Odoo exactly-once execution, durable automation jobs, recovery/checkpointing, policy/RBAC, local AI/document review, n8n orchestration, integration adapters, quality/evaluation plumbing and a broad operations console.

The release hardening focused on **correctness, evidence, integration boundaries and product polish**, rather than adding connector logos for appearance. This follows the blueprint principle that the application/API owns business state while n8n orchestrates around it, and that external-system claims require observable evidence.

The current source is suitable as a strong reference/portfolio system. It must still be described truthfully: offline mocks cannot guarantee a customer's credentials, tenant permissions, provider availability, quotas, remote workflow configuration or end-to-end telephony. Those are deployment acceptance items, not missing source code.

## 2. Blueprint coverage review

| Blueprint capability | Source review result |
|---|---|
| Omnichannel/document intake | Implemented: file upload, n8n ingress, Graph mail path and voice/API boundaries |
| Transaction orchestrator / digital twin | Implemented in PostgreSQL with lifecycle states, events, approvals, checkpoints, incidents and integration commands |
| Document intelligence | Implemented with PDF/image/text/spreadsheet handling, Ollama structured extraction, source preservation and human fallback |
| Customer & product resolution | Implemented with deterministic verification/evidence boundaries and review escalation |
| Knowledge/RAG | Implemented with scoped/effective-date evidence retrieval and prompt-injection treatment as untrusted data |
| Pricing / inventory / credit authority | Deterministic services own executable values; AI cannot override authority |
| Human approvals | Role-aware approval center and server-side RBAC |
| ERP | Odoo connector, idempotency keys, external ID persistence and read-after-write/replay protection |
| CRM | HubSpot company/contact upsert/readback adapter and durable command tracking |
| Microsoft 365 | Graph mail subscription/lifecycle/delta, SharePoint archive/readback, Outlook draft, Teams notification boundaries |
| Reliability/recovery | Bounded retry, classification, circuit breaker, leases/fencing, uncertain state, checkpoints, safe resume |
| Audit/lineage | Transaction events, payload hashes, trace/correlation IDs and Audit Explorer |
| AI Quality / shadow controls | Eval dataset/runner/report plumbing and accuracy-claim guards; 500-case draft still requires human labels |
| Progressive autonomy | Per-action L0–L4 policies with deterministic/RBAC constraints |
| Ask Ops | Constrained read-only operations analyst; no arbitrary generated SQL |
| Voice | Vapi-compatible guarded API contracts; review-only change requests |
| Payments | Stripe sandbox/test-mode boundary with signed webhook and amount/currency matching |
| Operations UX | Overview, inbox/detail, Decision Inspector, Approval Center, Exception Workbench, Recovery Center, Intake, Integration Health, AI Quality, Model Routing, Policy/Autonomy, Ask Ops, Automation Queue, Voice Review, Audit Explorer and Release Readiness |

## 3. Defects / weaknesses corrected in this review

### 3.1 Local role-key collision
The environment generator assigned the legacy operator key the exact `OPERATIONS_MANAGER` role-key value. Because the backend correctly rejects one secret mapped to conflicting identities, this could produce `Duplicate operator key assigned to conflicting roles.` The generator now leaves the legacy key blank and uses the five-role map as the authoritative development identity source.

### 3.2 Missing safe `.env.example`
The supplied source manifest/tests expected `.env.example`, but the ZIP did not contain it. A safe template has been restored with placeholders only and a warning not to duplicate the legacy operator key.

### 3.3 Release Readiness provider evidence mismatch
The worker persists SharePoint/Outlook actions under provider `MICROSOFT_GRAPH`, but readiness previously looked for provider names that the worker did not record. The readiness query now uses the actual provider/action/status tuples. Teams `ACKNOWLEDGED` is kept distinct from visible-channel verification.

### 3.4 Microsoft Graph preflight hardening
Graph subscription callbacks now require syntactically public HTTPS endpoints rather than merely any `https://` string, reject credentials/fragments/local/private literal addresses, and enforce the Graph clientState 32–128 character boundary before remote creation. SharePoint byte readback uses the injectable HTTP transport, improving deterministic contract tests.

### 3.5 Provider testability
Stripe and Graph transports can now be injected for offline HTTP contract tests. The provider suite checks request paths, authorization headers, idempotency, payload values, exact amount/currency, read-after-write behavior and fail-closed mismatches without pretending to contact a live account.

### 3.6 Product identity / UX
The active console no longer displays `NECTELIS / ATLAS DEMO`. It presents `OrderNexa AI` with `ATLAS INDUSTRIAL SYSTEMS` as the fictional reference organization. The release adds stronger focus/accessibility states, responsive feedback, selected navigation, refresh visibility, reduced-motion support and useful keyboard navigation without replacing the stable same-origin frontend architecture.

### 3.7 Runtime default
The production/runtime API image no longer starts Uvicorn with `--reload`; the test stage remains separate.

## 4. External provider verification

The offline suite covers Microsoft Graph, SharePoint, Outlook, HubSpot, Teams, Vapi/Twilio and Stripe boundaries. It verifies the source contracts and safety behavior, not external-account provisioning. See `EXTERNAL_PROVIDER_CONTRACT_MATRIX.md` for the exact distinction.

Source behavior was also cross-checked against current provider documentation for the core contracts used by this project: Microsoft Graph subscriptions/change notifications, Vapi API Request tools and reusable credentials, Twilio-number import into Vapi, HubSpot v3 batch upsert, and Stripe Checkout/idempotent requests.

## 5. Verification performed on the hardened tree

- `python3 -m compileall`: PASS.
- Full isolated Python suite: **127 passed**.
- Dedicated external provider contract file: PASS.
- JavaScript syntax: PASS.
- Node console tests: **11 passed**.
- Five n8n workflow JSON files: parse successfully, inactive, unique node names.
- Docker Compose: YAML parses; explicit runtime/test targets are present.
- Offline release preflight: PASS.
- 500-case generated eval draft: correctly remains release-claim ineligible until human curation.

The Python test environment uses an **import-only asyncpg stub** because the packaging sandbox does not run the owner's PostgreSQL. The stub supplies imports only and refuses database use; it does not fabricate database answers.

## 6. Owner-session evidence already established separately

During the owner's local acceptance session, the Odoo connector became healthy, a sales order was created, the exact same idempotency key replayed to the same external order, only one verified create command remained, a simulated downstream failure produced `DEGRADED`, and recovery completed without recreating the ERP side effect. The owner also completed smoke tests of all five n8n workflows with `AUTOMATION_LIVE_WRITES=false` for the controlled-sync test.

These observations are valuable local acceptance evidence but are intentionally kept separate from the packaging sandbox's offline test claims.

## 7. Remaining acceptance items — not source-code failures

1. **Microsoft 365:** live Entra/Exchange/SharePoint/Teams acceptance requires an authorized Microsoft 365 business tenant and admin-granted permissions.
2. **Vapi/Twilio:** a real call requires provider accounts/number and public HTTPS connectivity.
3. **HubSpot:** remote verification requires a real private-app/sandbox token and scopes.
4. **Stripe:** remote payment evidence requires a Stripe test account/session and signed webhook.
5. **Production OIDC:** requires a real IdP/JWKS/role mapping and login matrix.
6. **AI benchmark:** the generated 500 cases must be human-curated before any 97–98% accuracy target can be claimed.

## 8. Product-positioning conclusion

OrderNexa should be positioned on its **focused, demonstrable advantages**: evidence-backed decisions, deterministic authority, cross-channel transaction continuity, per-action autonomy, open adapters, exactly-once/replay safety, transaction-level recovery and explicit release evidence. It should not claim universal superiority over every ERP, automation suite or agent platform; the strongest portfolio position is that these controls are inspectable and demonstrated in one coherent customer-to-cash system.
