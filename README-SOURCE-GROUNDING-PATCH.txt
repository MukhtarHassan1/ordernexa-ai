OrderNexa — Hybrid Source Grounding & AI Safety (updated 2026-10-09)

Purpose: make document intake fast on clear business documents, useful on messy
ones, and fail-closed whenever critical source facts remain ambiguous.

Current behavior:
 - Deterministic native-text and table parser for PDF / XLSX / CSV / labelled text
 - PyMuPDF native PDF table extraction for real business layouts
 - Source-grounded Ollama fallback only when deterministic parsing is insufficient
 - Source-backed model-copy mistakes are corrected and audited, not blindly trusted
 - Ambiguous/conflicting/unverifiable critical source data still requires human review
 - Image-only/scanned inputs remain review-gated when there is no independent text source
 - Prompt-injection-like instructions in uploaded documents still trigger review
 - Untrusted document-derived CRM domains are discarded and never used as identity authority
 - Pricing, customer identity, inventory, credit, approvals and ERP writes remain deterministic downstream controls

IMPORTANT: source grounding is not an AI-accuracy claim. A clean source can be
processed without an LLM because explicit business facts are copied directly
from the original. When AI is used, its output is still reconciled against the
source and then passed through normal business validation.

Start here: ORDERNEXA-20261009-INTAKE-HARDENING-START-HERE.md
