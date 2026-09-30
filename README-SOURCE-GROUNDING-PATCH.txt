OrderNexa — Source Grounding & AI Safety Patch (2026-09-28)

Purpose: Correct the cause of misleading schema-valid PO extraction on the
supplied 2026-09-28 OrderNexa source and Ollama model-routing patch.

Contents:
 - New strict labelled-source parser + literal line evidence
 - Source-grounded, conflict-flagged AI extraction
 - Fail-closed intake; artifact status reports non-sensitive review reasons
 - Multi-line PO/customer/date human preview
 - Raw-vs-grounded evaluation reporting
 - 14 focused offline regression tests and a read-only diagnostic
 - Deployment/limitations runbook

IMPORTANT: Source-grounded field accuracy is NOT raw LLM accuracy. If the LLM
omits or contradicts source fields, the corrected draft is for a HUMAN to review;
no new transaction or ERP execution is authorized by that draft.

Start here: docs/runbooks/SOURCE-GROUNDING-SAFETY.md

Apply from the EXISTING ~/projects/ordernexa-ai root after backing up its
changed files. NO .env, Compose, secrets, migrations or model weights are
included. All Docker volumes remain untouched.
