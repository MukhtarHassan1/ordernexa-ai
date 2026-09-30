OrderNexa — AI confidence format & safety regression fix
2026-09-28

Observed live problem:
Qwen 1.5B returned a JSON extraction object with overall_confidence=100.
The contract requires 0 <= overall_confidence <= 1. Pydantic raised an
exception before the source-grounding stage could inspect the other fields.

What changes:
- For ExtractedOrderDraft only, confidence in the 1..100 percentage-style
  scale is converted to 0..1 for schema compatibility.
- The converted response ALWAYS gets the explicit review flag
  REVIEW_REQUIRED_NONCANONICAL_AI_CONFIDENCE.
- Source grounding lowers confidence to at most 0.5 when review is required.
- The intake service already rejects all REVIEW_REQUIRED_* flags BEFORE
  transaction creation. This patch preserves those safeguards.
- Confidence values outside acceptable fraction or percentage ranges,
  including negative numbers, >100 and booleans, remain validation errors.
- The original Ollama response stays available unmodified in raw_content.
- The read-only grounding diagnostic now prints both the original model
  confidence and the normalized value, to avoid misleading reports.

Patch files (only three):
  apps/api/app/schemas/intake.py
  apps/api/tools/check_po_grounding.py
  apps/api/tests/test_ai_confidence_scale.py

Installation (from existing ~/projects/ordernexa-ai):
  1. Back up existing files (or the project, preserving .env privately).
  2. Extract this ZIP to project root, preserving folder paths.
  3. Because the existing Compose file bind-mounts ./apps/api:/app,
     restart only the API: docker compose restart api
  4. Run offline tests:
     docker compose exec -T api python -m pytest -q tests
  5. Run diagnostic without Ollama, DB, MinIO or ERP writes:
     docker compose exec -T api python /app/tools/check_po_grounding.py --offline
  6. Run live diagnostic without DB, MinIO or ERP writes:
     docker compose exec -T api python /app/tools/check_po_grounding.py --live

The expected outcome for a model returning confidence=100 is NOT automatic
approval. The error should no longer abort the entire extraction if the
remainder of the model response is schema-valid. Instead, the source-corrected
PO is displayed with human review required. If other schema fields are wrong
in incompatible ways, the system still safely rejects the output. If the
local live model returns confidence=0..1 normally, the new quarantine flag
will not be added; existing source grounding still flags conflicting or
unverifiable fields.

Verified locally against the reconstructed source-grounding + model-routing
project snapshot: 54 offline tests passed; offline canonical PO fixture
reports 10/10 grounded fields but human review required after corrections.
Live Windows Ollama is unavailable in the test environment and must be
verified on your machine. This does not certify AI extraction accuracy.

No .env, Docker config, model weights, migrations or Docker volumes included.
