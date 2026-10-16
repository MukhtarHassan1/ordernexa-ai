# OrderNexa AI — 2026-10-09 Intake Hardening

## Purpose

Apply this patch over the current 2026-10-09 working project. It does not contain `.env` and does not change database migrations, ERP execution, n8n workflows or external-provider contracts.

## Main behavior change

Document Intake is now hybrid:

1. Parse native text and structured tables deterministically.
2. If all critical PO fields and line items are independently grounded, continue immediately without an LLM call.
3. If source data is ambiguous/unstructured, use Ollama structured extraction and reconcile its proposal against the original source.
4. If critical source facts remain unverifiable, preserve the original and require human review.

This keeps AI useful for ambiguity while making ordinary digital purchase orders faster and more reliable.

## After overlay

Rebuild/recreate the API because Python and console assets changed:

```bash
docker compose build api
docker compose up -d --force-recreate api
docker compose --profile automation up -d --force-recreate automation-worker
```

Then run:

```bash
bash scripts/final-local-verify.sh
```

For the realistic portfolio PO, upload it once through Document Intake. A clean digital/table-based source should now use the deterministic source-grounded path instead of waiting on Ollama.
