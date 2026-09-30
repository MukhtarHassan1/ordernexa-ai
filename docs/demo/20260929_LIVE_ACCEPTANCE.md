# Live acceptance sheet — fill from real running system, not source claims

Use this sheet after applying the September 29 patch. Keep passwords and customer private data out of any public portfolio screenshots. Write the actual screenshot/video filename, real transaction public ID, real external object ID and timestamp for every successful step. **Do not mark an integration PASS merely because a request was enqueued.**

| Gate | Exact observation required | Status and evidence |
|---|---|---|
| Deployment | Existing `.env` preserved, no named volume reset; Alembic shows `20260929_auto`; FastAPI ready | PENDING — local operator |
| Reproducible code quality | User's Docker `python -m pytest -q tests` passes; UI loads on Windows; new pages populated only by real saved state | PENDING |
| Source-grounded extraction | One actual PO processed; raw result and grounded evidence visibly distinct; conflicting model output routed to saved-artifact **human review** | User previously demonstrated 7/10 raw vs 10/10 grounded offline/live test; redo against installed release only if desired |
| Canonical business rules | Existing saved PO resolves correct customer/SKUs and authoritative `GBP 13,995`, correct warehouse, credit, and `APPROVAL_REQUIRED` | PENDING; check seeded DB, don't hardcode |
| Human governance | Required separate sales/finance approvals, wrong-role denial, audited actors, READY state only after all approvals | PENDING |
| Odoo | One real verified external ID; replay of same command does NOT create another order | PENDING |
| Local archive/recovery | Deliberate MinIO failure yields DEGRADED with original ERP ID; recovery verifies same ERP ID, archives once, final local COMPLETED | PENDING |
| Durable transport | New `automation_jobs` real DB rows; n8n synthetic request accepted once; identical event deduped; conflicting event rejected 409 | PENDING |
| Graph real mail | Administrator-approved app and restricted mailbox; public HTTPS callback validated; single authentic email/attachment persisted and reviewed | PENDING, external prerequisites |
| SharePoint | User-consented local COMPLETE order; same remote path, byte-for-byte verified archive readback | PENDING, external prerequisites |
| HubSpot | Approved/verified recipient, upsert contact exactly once by email and read back remote ID/email | PENDING, external prerequisites |
| Outlook | Human-verified recipient, accurate UNSENT draft GET readback; optional separate operator-released existing draft; actual Sent Items checked | PENDING, external prerequisites |
| Teams | Real Workflows notification ACK and separately confirmed channel display; web operator remains decision authority | PENDING, external prerequisites |
| Vapi | Real guarded status tool, voice event dedupe and review-only request appears in Console; caller identity reviewed manually | PENDING; telephony not implemented by this source package |
| AI quality | Independently curated 500 labeled samples; actual measured critical-field accuracy, prompt injection safety and escalation rates; release gates | PENDING; generated 500 drafts do not count |
| Real dashboard / portfolio | Actual transaction KPIs, event hashes, recovery timeline and measured AI report visible; 4–6 minute film contains only verified real actions | PENDING |

**Do not claim production readiness:** SSO, public access controls, rate limits, Graph missed-notification delta recovery, actual DR restore exercise, compliance review and full integration failure testing remain engineering gates. V1.5 Stripe, Ask Ops, full voice and optional Next.js rewrite are separately tracked in `docs/architecture/20260929_BLUEPRINT_GAP_AND_EVIDENCE.md`.

## Suggested 4–6 minute truthful video sequence

1. Show one incoming PO and explain ambiguity and source evidence in ~30 seconds.
2. Show raw vs corrected model fields and **real** human review in ~40 seconds.
3. Open the **same** transaction's customer/SKU/contract/warehouse/credit evidence in ~50 seconds.
4. Role approvals → real Odoo order → idempotent replay in ~80 seconds.
5. Deliberately fail the local archive and recover without recreating ERP order in ~60 seconds.
6. Show the persistent automation queue and genuine Graph/HubSpot/SharePoint actions only if they're actually working in the configured test accounts. Otherwise clearly label them as integration-ready and show local synthetic ingestion in ~45 seconds.
7. Show measured raw/grounded eval report, real KPI dashboard and next-stage voice review if proven in ~40 seconds.
