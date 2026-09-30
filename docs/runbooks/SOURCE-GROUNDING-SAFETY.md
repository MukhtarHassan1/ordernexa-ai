# Source grounding and safe AI extraction — OrderNexa

## Why the raw Qwen result was 6/10

The original PO-88192 text places several key-value labels on one line and the
value on the **next non-empty line**. The 1.5B model returned schema-valid JSON
with a missing PO number, an incorrect customer and an invented date. Pydantic
validated the *shape*, not factual accuracy; `overall_confidence=1` was a
self-reported model value, not a statistically calibrated probability.

Upgrading the model alone cannot guarantee trustworthy purchase orders.

## What this patch changes

1. It scans **unambiguous, explicitly labelled native source text** for original
   PO number, customer, delivery location/date, currency and structured line
   blocks. All extracted anchors carry literal source-line references.
2. It independently compares the raw LLM prediction against those anchors.
   Source-based corrections appear in the **display draft**, while the original
   raw model response remains available in memory for evaluation. Model/source
   conflicts, missing critical source anchors and ambiguous data always flag
   `REVIEW_REQUIRED_*` and cap draft confidence to 0.5.
3. The intake service now checks `REVIEW_REQUIRED_*` before creating an order,
   preserving the original artifact in MinIO and storing **only field-level
   review flags**, not raw customer documents, in the artifact's metadata.
4. The already-existing human-confirmation flow can inspect the now-corrected
   multi-line preview. A human must still check the saved source and authorize
   confirmation. AI **does not** generate an executable price or waive policy.
5. Image-only requests remain review-required until a separate vision quality
   and source-evidence validation path is qualified.
6. The local evaluation runner now reports **raw model** accuracy separately
   from **source-grounded pipeline** accuracy. A corrected 10/10 is never
   mislabeled as 10/10 model performance.
7. Basic independent detection flags a few obvious embedded malicious
   instructions. It is a fail-closed screening rule, **not** a complete
   prompt-injection defense or a general cybersecurity guarantee.

## Installation on the existing WSL project

Keep your existing `.env`, `compose.yaml`/`docker-compose.yml` and all Docker
volumes. The ZIP overlays only explicitly listed application/test/runbook files.

From `~/projects/ordernexa-ai`:

```bash
BACKUP="$HOME/ordernexa-backups/source-grounding-$(date +%Y%m%d-%H%M).tar.gz"
mkdir -p "$HOME/ordernexa-backups"
tar -czf "$BACKUP" \
  apps/api/app/services/document_intelligence.py \
  apps/api/app/services/intake_service.py \
  apps/api/app/services/manual_document_preview.py \
  apps/api/app/api/routes/intake.py \
  evals/runners/eval_local_ollama.py
unzip -t /mnt/c/Users/Hammad/Downloads/OrderNexa_Source_Grounding_Safety_Patch_20260928.zip
unzip -o /mnt/c/Users/Hammad/Downloads/OrderNexa_Source_Grounding_Safety_Patch_20260928.zip -d .
docker compose restart api
```

If the actual Windows user or downloaded filename differs, locate the ZIP and
use its exact `/mnt/c/...` path. `docker compose restart` is sufficient when
`./apps/api:/app` is bind-mounted, as in the supplied project. If the container
uses a different Compose file, verify `/app` mounts before assuming restart is
sufficient.

## Test without contacting Ollama or databases

```bash
docker compose exec -T api python /app/tools/check_po_grounding.py --offline
```

The deliberately inaccurate **synthetic regression** should display:

- Raw model checks: `6/10` (synthetic, NOT a new measured Qwen score).
- Source-grounded checks: `10/10`.
- Corrected fields: PO number, customer, requested delivery date.
- `Requires human review: True`. **The full API still refuses automatic order
  creation when raw AI and source disagree.**

Run the offline unit suite (no Ollama requests):

```bash
docker compose exec -T api python -m pytest -q tests
```

If `No module named pytest` appears after an image rebuild:

```bash
docker compose exec -T api python -m pip install -r requirements-dev.txt
```

## Test with your actual Windows Ollama (read-only)

Before running this, ensure the API container's `OLLAMA_BASE_URL` points to
`http://host.docker.internal:11434`, `OLLAMA_TEXT_MODEL` to your already-tested
Windows model, and Windows Ollama is running.

```bash
docker compose exec -T api python /app/tools/check_po_grounding.py --live
```

This tests the **raw prediction** and the **source-grounded pipeline** for
PO-88192. It cannot create a transaction, alter the DB, access MinIO or call
Odoo. A `10/10` *grounded* result accompanied by review flags means human review
is still required; it does not establish raw model reliability.

Only after inspection of raw scores should you try a few additional synthetic
cases:

```bash
docker compose exec -T api python /evals/runners/eval_local_ollama.py \
  --dataset /evals/datasets/synthetic_po_eval.jsonl \
  --out /evals/reports/source-grounded-initial.json --limit 3
```

The slow local 8GB model can take several minutes. Release gates explicitly use
**raw** model accuracy rather than laundering model mistakes through deterministic
corrections. Keep autonomous writes restricted until the suite's configured
safety and quality requirements are met.

## Scope and limitations

- Native text and PDF native-text in **labelled format** are handled
  conservatively. Unstructured email body text, PDF tables, multi-column
  layouts, XLSX cell streams, scanned PDFs and images can require human review
  even if the LLM appears confident. More format-specific validators and a
  real vision evaluation set are necessary before authorizing those channels.
- A literal source line is evidence that text appeared in a document; it does
  **not** authenticate the sender, contract, customer account or correct SKU.
  Existing deterministic CRM/ERP matching, pricing, inventory and credit checks
  remain separate and authoritative.
- Suspicious content is treated as untrusted input. The heuristic injection
  guard has limited coverage; additional adversarial tests are required.
- This patch modifies neither ERP data nor container models nor configuration
  secrets. It is not a database/volume backup and was not run on your Windows
  computer. Test on your actual WSL repo before resuming a transaction.

## Next business workflow

If the live raw model output still disagrees with the document, locate the
already-saved artifact in the Operations Console, open the corrected native-text
human preview, check it **against the stored original**, and confirm it using
an authorized operations/sales identity. Continue using the existing
transaction validation → pricing/inventory/credit exception → approval → Odoo
exactly-once verification flow. Avoid uploading PO-88192 again if a transaction
or artifact already exists; use the saved artifact/transaction instead.
