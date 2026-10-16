# OrderNexa AI — 2026-10-09 Document Intelligence Hardening

This release hardens document intake after a realistic business PO exposed a limitation in the original source-grounding parser: native PDF text was available, but the flattened layout hid key-value pairs and line-item tables from the deterministic verifier.

## What changed

- Added a **hybrid extraction pipeline**:
  - deterministic source parsing first for clean digital business documents,
  - Ollama only when the source remains ambiguous or genuinely unstructured,
  - vision/image extraction remains human-review gated when no independent text source exists.
- Added native **PyMuPDF table extraction** for digital PDFs using `Page.find_tables()`.
- Added structured-table grounding for **PDF, XLSX and CSV** order lines.
- Added common PO metadata variants and two-column business blocks:
  - PO Number / PO No / Order Number,
  - Customer / Buyer / Bill To / Sold To,
  - Ship To / Deliver To / Delivery Location,
  - Requested Delivery / Delivery Date / Required By,
  - Currency.
- Added robust handling for flattened two-column PDF text where labels and values are interleaved.
- Added document-issuer corroboration for purchase-order customer hints while preserving ambiguity review when sources disagree.
- Added deterministic line-table aliases for common headers such as SKU, Customer Ref, Qty, UOM and Unit Price.
- Changed source-backed model-copy mistakes from blanket review failures into **audited deterministic corrections** when the original source independently proves the value.
- Untrusted document-derived customer domains are now discarded as a non-authoritative security sanitation event rather than blocking an otherwise verified order.
- Noncanonical AI confidence scales such as `100` or `75%` are normalized and audited; model confidence is never used as evidence.
- Added a fast deterministic source path so clean structured documents avoid unnecessary local-model latency entirely.
- Updated Document Intake UI wording from provider-specific “Ollama extraction” to **hybrid document intelligence**.
- Added realistic tabular PDF regression fixture and XLSX/CSV grounding tests.

## Safety boundaries retained

- Ambiguous/conflicting source values still require human review.
- Prompt-injection-like document instructions still force review.
- Image/scanned extraction without independent source text still forces review.
- Customer identity, executable pricing, stock, credit and approvals remain deterministic downstream authorities.
- Duplicate/replay and stored-original protections are unchanged.

## Verification

- Python isolated suite: **139 passed** (with import-only `asyncpg` stub; no DB behavior fabricated).
- Focused document-intelligence tests: **37 passed**.
- Node console tests: **11 passed**.
- Python compilation: **PASS**.
- n8n templates: **5 JSON-valid and inactive**.
- Offline preflight: **PASS**.
- Realistic portfolio PO `PO-PORTFOLIO-001` now resolves via `PDF_NATIVE_TEXT_TABLES` and the deterministic fast path without calling Ollama.
