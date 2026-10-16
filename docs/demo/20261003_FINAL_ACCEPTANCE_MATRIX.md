# Final acceptance matrix

Mark PASS only from a real observation. Source code presence is never enough.

| Gate | Required evidence |
|---|---|
| Core | API ready, Alembic head, backend + JS tests green |
| Document/AI | real source preserved, structured extraction, source conflict -> human review |
| Deterministic rules | customer/SKU/pricing/inventory/credit evidence from stored authority |
| Approval | wrong-role denied; required authorized approvals recorded |
| Duplicate | same business PO/replay does not create second ERP side effect |
| Odoo | exactly one verified sales order + read-after-write |
| Recovery | post-ERP failure -> DEGRADED -> safe plan -> COMPLETED, Odoo count remains one |
| n8n | first ingress queued once, exact replay deduped, conflicting replay rejected 409 |
| Graph | real webhook + missed-event delta recovery exactly once |
| SharePoint | remote file verified by readback/hash |
| HubSpot | stable company/contact IDs reused on replay |
| Outlook | unsent draft verified; explicit send only after preview approval |
| Teams | HTTP ACK + actual channel display; OrderNexa remains approval authority |
| Voice | real Vapi/Twilio call creates review-only request; no order mutation |
| Stripe | signed test webhook verifies reference/amount/currency |
| OIDC/RBAC | valid role access + invalid token/role denial |
| AI eval | human-curated dataset + saved measured report; no generated-label claims |
| Frontend | required operations screens load real data and Release Readiness tells the truth |
