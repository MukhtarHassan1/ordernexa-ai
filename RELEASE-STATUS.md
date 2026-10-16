# OrderNexa AI — 2026-10-09 reference-release status

OrderNexa is a production-style reference implementation with evidence-gated release claims. “Implemented”, “configured”, “acknowledged” and “verified” intentionally mean different things.

| Area | Current evidence | Remaining live proof |
|---|---|---|
| Transaction/business core | Implemented; deterministic state/policy authority, transaction digital twin, business-order dedupe and amendment revisions; isolated suite passes | Owner environment/database acceptance is already part of the local test campaign |
| Odoo ERP | Exactly-once command/replay/recovery design; owner-session test created an order, replayed the same external ID, and kept one verified command | Re-run only if Odoo configuration changes |
| n8n | Five inactive workflows, JSON-valid; owner-session smoke tests completed all five with authority preserved | Re-run after n8n version/credential changes |
| Reliability/recovery | Command journal, retries, circuit breaker, lease/fencing/heartbeat, uncertain-state quarantine, checkpoints and protected-side-effect recovery | Provider-specific failure campaigns when live accounts are available |
| Microsoft Graph / Outlook / SharePoint | Current source contracts and webhook/subscription/lifecycle/delta logic are offline-tested; public callback and clientState guards strengthened | Real Entra tenant, mailbox/site permissions and live notification/archive/draft acceptance |
| HubSpot | Contact/company upsert/readback contracts and uncertainty handling implemented/tested | Real private-app/sandbox token and read-after-write acceptance |
| Teams | URL boundary, notification-only authority, uncertainty handling and ACK-vs-delivery distinction implemented/tested | Human-observed message in target channel |
| Vapi / Twilio | API Request contracts match backend OpenAPI; status lookup is privacy-minimized and change requests are review-only; Twilio credentials stay outside FastAPI | Real Vapi assistant + Twilio number/call acceptance |
| Stripe | Test-mode-only Checkout, idempotency, amount/currency verification and signature/replay controls are tested offline | Real Stripe test account/session/webhook acceptance |
| OIDC/RBAC | OIDC/JWT boundary and five-role local RBAC test coverage | Real identity provider role-by-role acceptance |
| Document intelligence | Hybrid deterministic-first + Ollama fallback; native PDF tables, XLSX and CSV grounding; ambiguous/image-only sources remain review-gated | Re-run representative customer document set when onboarding a new format family |
| AI quality | Dataset guards, quality reporting and shadow/eval infrastructure exist | Human curate the generated 500 cases and run a measured model evaluation before publishing accuracy percentages |
| Frontend | Required operations surfaces present; branding/interaction/accessibility polish upgraded; 11 JS tests pass | Browser/live-data visual acceptance after overlay |

## Packaging-environment evidence

- Python compile: **PASS**.
- Python isolated tests: **139 passed** using an import-only `asyncpg` stub; no database results were fabricated.
- External-provider subset: **19 provider-focused tests** in `test_external_provider_contracts.py` after callback hardening, plus existing integration/automation contract coverage in the full suite.
- Node console tests: **11 passed**.
- n8n templates: **5**, JSON-valid, inactive and unique node names.
- Docker Compose YAML: parsed; `api`/worker target `runtime`, `api-tests` targets `test` and mounts repository read-only for release checks.
- Offline release preflight: **PASS**.
- Generated evaluation draft: **500/500 labels still require human review**, so it is not benchmark-eligible.
- Live Microsoft/Vapi/Twilio/HubSpot/Teams/Stripe accounts were not available in the packaging sandbox and are **not** claimed verified.

Use `ORDERNEXA-20261009-INTAKE-HARDENING-START-HERE.md` for the latest intake hardening, plus the existing reference-release documentation.
