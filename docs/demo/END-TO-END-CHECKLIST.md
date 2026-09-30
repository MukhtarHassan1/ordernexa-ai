# Canonical OrderNexa demonstration: acceptance checklist

The blueprint's test case is Northstar Engineering PO-88192, XTR-42 / BRK-90
customer aliases resolving to XTR-420 / BRK-090, authoritative contract
pricing, distributed stock, credit exception, human approval, exactly-one
verified Odoo sales order, document archive and safe partial-failure recovery.
Stage 2's previously seeded deterministic validator reportedly produced
**GBP 13,995** and `APPROVAL_REQUIRED`. Treat that as a test expectation to
recheck against the actual running database, not as a newly verified result.

1. **Source and health.** After applying the patch and configuring the private
   `.env`, start API/Postgres/Redis/MinIO only. `curl -sS
   http://127.0.0.1:8000/api/v1/health/live` should return `status: ok`.
   Browse the local `/console/` route. Set your generated SALES_MANAGER key.
2. **Proof of real AI runtime:** Open Integrations & AI and run **Run real
   inference probe**. An HTTP 503 means the local Ollama runner still cannot
   generate; `/api/tags` availability does not change that conclusion.
3. **AI unavailable: real manual fallback.** Choose Document intake, select the
   existing `sample-data/purchase-orders/po-88192-upload.txt`, and upload.
   A 503 after the bounded timeout should include `artifact_id`. Use Check
   status to confirm `AI_UNAVAILABLE`; use Preview for human review and compare
   every line, date and price against the original before confirming. This
   route records `FILE_UPLOAD_HUMAN_REVIEW` and never pretends AI succeeded.
   If the model probe succeeded, test AI extraction before relying on it.
4. **Deterministic validation.** The resulting transaction must have evidence
   for customer, alias resolution, contract/pricing, warehouse allocations,
   projected credit and required approvals. Inspect the timeline, evidence,
   policy decisions and checkpoints. Do not override the price with the
   customer's requested unit price.
5. **Human approvals.** Enter the SALES_MANAGER key for pricing exceptions,
   FINANCE_MANAGER for credit and OPERATIONS_MANAGER for warehouse operations.
   Each action must appear in audit history. Verify that mismatched local keys
   cannot approve other roles. Test rejection on a separate synthetic PO,
   never on the canonical order you intend to execute.
6. **Odoo setup:** Start `odoo-db` and `odoo`; verify the existing connector's
   authenticated health/bootstrap (the user previously observed these
   successfully). Approvals must place the transaction in READY before
   attempting ERP execution. Use an OPERATIONS_MANAGER or FINANCE_MANAGER key
   with `/api/v1/execution/transactions/{public_id}/erp` or an authorized UI
   workflow when available.
7. **Read-after-write and idempotency.** The ERP command must be VERIFIED and
   the Odoo GET endpoint must return the same external order by the original
   idempotency key. Repeating the **same** successful API action must show
   `replayed: true` and must not create another Odoo order. A lost response
   should be routed to the explicit `/erp/retry` endpoint only after a
   documented transient/uncertain failure.
8. **Downstream failure injection.** With an OPERATIONS_MANAGER key, POST to
   `/api/v1/execution/transactions/{public_id}/downstream` with JSON body
   `{"simulate_failure":true}`. Verify the state is DEGRADED and the Odoo
   order retains its previous external ID; use `/recover` on that transaction.
   Recovery must verify/archive the original Odoo order and finish **the local
   MinIO demonstration** without an ERP POST. A new explicit real-object read
   verifies that a preexisting archive is reused rather than rewritten.
9. **Actual external integrations remain separate.** The Graph and HubSpot
   transport contracts can be unit-tested, but email, Teams approval messages,
   SharePoint archive, CRM writes and Outlook confirmation require real
   accounts, permission grants, integration commands and end-to-end tests.
   Do not record those as completed until their live results are verified.
10. **Quality lab:** Run the 32-case synthetic offline evaluation when Ollama
    can actually generate. Review reported field accuracy and prompt-injection
    safety; no model/version is cleared for autonomous operation on mock tests
    or an unrun labeled dataset.

Avoid resetting PostgreSQL/Odoo, clearing MinIO, deleting Docker volumes or
rerunning the same PO repeatedly to "fix" transport errors. The original
upload checksum, PO reference and ERP idempotency key exist precisely to
prevent that behavior.
