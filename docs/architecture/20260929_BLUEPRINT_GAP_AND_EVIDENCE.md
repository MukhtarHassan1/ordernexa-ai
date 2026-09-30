# NECTELIS blueprint-to-code assessment | September 29 source ZIP

Source of truth: `docs/NECTELIS_Master_Project_Blueprint.docx` (38 pages). Scope is the **entire customer transaction**, not an arbitrary number of agents or logos. V1 is one deep end-to-end reference lane. An implemented method, imported template, passing isolated test or vendor-token placeholder **is not a verified operational integration**.

| Blueprint target | Existing / newly added in updated source | Remaining acceptance evidence / scope |
|---|---|---|
| Omnichannel intake | File, PDF/image/Excel/TXT parser; n8n authenticated shared-secret document queue; Graph basic webhook, app-only attachment fetch | Public Graph HTTPS callback, admin app permissions, real inbox intake and re-subscription; future messaging channel is out of V1. |
| AI triage & extraction | Schema-bound local Ollama model-routing, source-grounded deterministic correction, strict review when any critical conflict | Curated real/representative PO/RFQ multilingual evals, measured accuracy and OCR/vision acceptance on hardware. |
| Transaction digital twin | PostgreSQL existing transactions, append-only-like events, source artifacts, typed policy outcomes, evidence, approvals, checkpoints | Real user verification that the canonical PO safely resumes and completes after upgrading. |
| Customer / SKU resolution | Existing seeded identity resolution and aliases with human ambiguity guard | Multiple customer/alias ambiguous cases and actual CRM/ERP cross-check where used. |
| Contract RAG | Existing customer/date-scoped contract evidence query; deterministic commercial/pricing authority | Retrieval recall testing, doc-ingestion schedule and optional true vector ranking. Current query must not be described as proven vector RAG. |
| Pricing / inventory / credit | Existing deterministic contract price, warehouse allocation and credit policy | Canonical £13,995 scenario from live seeded DB and exception-role tests. |
| Human approval | Existing web role-scoped approvals; new informational Teams Workflows notification | Actual Teams notification ACK vs channel visibility; interactive Teams approve/reject not implemented. Web console is sole decision authority. |
| ERP Odoo | Existing custom connector, read-before-replay, verified order idempotency | Fresh live Odoo order and repeated same idempotency key with no duplicate; source ZIP has no Odoo DB records. |
| Archive / CRM / Outlook | Verified **local** MinIO archive + recovery; guarded SharePoint same-path upload and byte readback, HubSpot email upsert/GET, Outlook *unsent* draft/GET and operator-only existing-draft send | Microsoft and HubSpot credentials/permissions, Graph proxy, approved external consent, verified customer email and remote readback tests. External commands not yet all journaled into the existing `IntegrationCommand` table; automation jobs own their state. |
| Reliability | Existing local downstream checkpoint+safe replay; NEW durable DB job claims, event keys, bounded retries, uncertain-write quarantine/reconciliation | Integration fault-injection suite, actual outbox delivery, high-availability leases and full remote compensation; Graph missed-notification delta backfill not implemented. |
| AI Quality Lab / shadow | Existing labeled sample dataset and runner with raw/grounded separation; 500 **uncurated draft** examples generated; real-eval report UI | Human curation and independently labeled ≥500 cases; run live models, record field accuracy, safety gates, shadow comparisons. Uncurated draft ≠ achieved benchmark. |
| Dashboard / trace | Existing local responsive HTML+JS console now includes durable automation queue, evaluation report listing, audit explorer, restricted voice review | Live browser usability on actual Windows, production Next.js/React implementation if that technology remains a hard requirement, and SSO/CSRF/accessibility testing. |
| Vapi voice V1.5 | Authenticated coarse read-only status + idempotent review-only change requests | Configure Vapi tools + publicly accessible route-limited webhook, authenticated caller verification, full live call and change-request review. Not a working phone agent yet. |
| Stripe / Ask Ops V1.5 | No executable payment connector or safe read-only ops-language runtime included | Actual sandbox credentials, signature-validated webhook and safe analytics policy remain separate work. |
| Progressive autonomy | Existing explicit human-review and policy guard; external writes off by default | Shadow-evaluation evidence and **per-action**, not agent-wide, maturity. Do not enable L4 for the current Qwen results. |
| Security | Local demonstration keys, token-protected ingress, narrow voice actions, redacted job API, local host port bindings | External IdP SSO, signed JWT scope authorization, proxy TLS and IP/rate-limit controls, Exchange mailbox scoping, Graph app permission review, threat model and independent security test. |
| Observability / portfolio | Existing real DB metrics, correlation IDs and automation trace events; new docs and 4–6 minute demo checklist | Distributed tracing to each real service, recorded actual KPI/time/quality data, screenshot/video only when genuinely demonstrated. |

## Verified vs observed vs not tested

- **Observed by user before this release:** Windows-native Qwen extraction on original PO: raw 7/10, source-grounded 10/10, correct human-review result; prior PostgreSQL/FastAPI health and Odoo bootstrap. They have not submitted a live post-release migration or external integration transcript.
- **Verified in this sandbox:** Python/Node offline tests with the documented local stub of unavailable asyncpg; source compilation; Compose/JSON parsing; exactly 500 *draft* evaluation lines. None of these involve live database, WSL Docker runtime, API credentials or browser visual testing.
- **Release gate:** API ready + Alembic migration, API tests, saved-artifact review/transaction id, local role approvals + Odoo exactly-once + local recover, n8n async/dup, restricted external write/verify, curated AI/safety quality, realistic demo.

## Scope priority

**Now:** reliably complete the existing reviewed PO local transaction; make the optional worker and n8n transport observable. **After real account access:** deep Microsoft + CRM vertical slice, not a dozen unverified connectors. **Then:** actual quality/risk measurements, production identity/dashboard hosting, Vapi cross-channel demonstration and optional Stripe sandbox. Follow the blueprint's depth-before-connector-count principle.
