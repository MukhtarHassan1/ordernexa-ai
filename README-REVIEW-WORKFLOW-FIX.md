# OrderNexa: safe, one-click human review of source conflicts

## What the supplied response means

The error `DOCUMENT_NEEDS_REVIEW` is **not an Ollama crash**. The original was
saved in MinIO and the model supplied some claims that disagree with source
anchors. The system correctly stopped before creating or executing an order.
Do **not** disable `REVIEW_REQUIRED_*` flags or trust the AI's confidence number.

For the report you shared, the saved artifact is:
`5c5bf862-30c1-40c1-a1f2-4b59f37ef015`.

## What this patch changes

1. Detects FastAPI's real nested `detail.details.artifact_id` response (the
   old UI missed this exact location). Automatically retains the existing
   artifact ID and opens its deterministic review preview after 422.
2. Shows human-readable explanations and original source-line evidence; does
   not repeat Ollama or silently create a transaction.
3. Lets authorized sales/operations reviewers download the **original** from
   MinIO through a restricted endpoint, with checksum verification and forced
   attachment download. Preview and retries also verify the saved checksum.
4. Offers explicit, initially **blank** manual entry if strict parsing cannot
   support a scanned/ambiguous/unknown document. The reviewer must read the
   saved original and check the confirmation box; no values are invented.
5. Recognizes duplicate-document responses and links to the existing
   transaction, rather than suggesting another upload.
6. Returns additive, machine-readable `workflow_state`, top-level `artifact_id`
   and `next_step` for 422 source conflicts, helping future n8n workflows
   route review cases. HTTP remains 422 to fail closed for unattended clients.
7. Records only the last artifact **UUID** in browser session storage. It does
   not save source documents, AI output, or operator keys there; pre-existing
   operator-key handling remains unchanged.

## Installation: preserves existing .env and Docker data

Download `OrderNexa_Human_Review_Workflow_Fix_20260929.zip` into Windows Downloads.

```bash
cd ~/projects/ordernexa-ai
mkdir -p ~/ordernexa-backups
STAMP=$(date +%Y%m%d-%H%M)
tar -czf "$HOME/ordernexa-backups/before-review-workflow-$STAMP.tar.gz"   apps/api/app/api/routes/intake.py   apps/api/app/services/intake_service.py   apps/api/app/console

PATCH=$(find /mnt/c/Users -maxdepth 5 -type f   -name 'OrderNexa_Human_Review_Workflow_Fix_20260929.zip'   -print -quit 2>/dev/null)
test -n "$PATCH" && unzip -tq "$PATCH" && unzip -o "$PATCH" -d .
# Existing patched Compose binds ./apps/api to /app.
docker compose restart api
```

If `test -n "$PATCH"` fails, provide the exact downloaded ZIP path; do not
run unzip with an empty variable. Never use `docker compose down -v` here.

## Tests

```bash
docker compose exec -T api python -m pytest -q tests
curl -fsS http://127.0.0.1:8000/api/v1/health/ready
```

The reconstructed source passed **62 isolated offline Python tests**, using
an import stub for `asyncpg` in this build environment (which has no live DB),
plus **8 Node.js browser-logic/UI tests**. Authenticated preview and download
were additionally smoke-tested with a FastAPI test client and fake storage.
These are NOT live database, MinIO, Odoo or Ollama acceptance tests. Re-run
Python tests in your Docker API container to test its real dependencies.

## Continue the exact EXISTING artifact (no new upload / no Ollama wait)

1. Hard-refresh `http://localhost:8000/console/` (Ctrl+Shift+R).
2. Under **Operator access**, use your private existing `SALES_MANAGER` or
   `OPERATIONS_MANAGER` key; do NOT send the key to anyone.
3. Open **Document intake**. In **Artifact ID**, paste
   `5c5bf862-30c1-40c1-a1f2-4b59f37ef015`.
4. Click **Check status** (expect `NEEDS_REVIEW`). If `PROCESSED` or
   `HUMAN_REVIEWED`, inspect its existing transaction instead.
5. Click **Download original** and open the saved file. Click
   **Preview for human review**: the form will prefill only values supported
   by the strict source parser and display source-line evidence. If this
   document format has no safe strict preview, use **Enter fields manually**
   and fill every field after inspecting the original.
6. For the canonical Atlas test, compare the original against the preview:
   PO-88192; Northstar Engineering Ltd; GBP; Manchester (`MAN` demo warehouse,
   *confirm* this interpretation); 2026-09-30; XTR-42 x40 at requested £260;
   BRK-90 x15 at requested £165. Leave customer_domain null if the source
   and verified account channel do not establish it. **Requested prices are
   not authorized contract prices.**
7. Only after comparing every field with the saved original, check the
   human-verification checkbox, then click **Confirm & validate through
   transaction engine** ONCE. The UI disables the button while processing.
8. Save the returned `public_id`, status, value and policy decisions. If
   `APPROVAL_REQUIRED`, review the stored evidence in Transactions and the
   pending approvals. Do not create an ERP order or approve blindly. If the
   response reports a resolution conflict, follow its existing transaction
   ID rather than uploading again.

## Important scope

This finishes the **review handoff** for saved original artifacts, not the
entire NECTELIS project. Validating actual commercial results, role approvals,
Odoo's exactly-once writes, full recovery, Microsoft 365/HubSpot/n8n, evaluation
and voice still require their corresponding end-to-end tests and credentials.
Do not claim a source parser is universal: unsupported or ambiguous formats
must use the explicit, auditable human-review route.
