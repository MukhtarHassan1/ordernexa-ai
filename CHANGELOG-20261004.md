# OrderNexa AI — changelog 2026-10-04

## Product identity and UX
- Removed legacy NECTELIS / demo wording from the active Operations Console.
- Updated Odoo connector author metadata to OrderNexa.
- Strengthened console focus states, responsive behavior, selected-navigation feedback, refresh timestamp and keyboard access.

## Authentication and configuration
- Fixed local environment generation so `ORDERNEXA_OPERATOR_KEY` remains empty when per-role keys are generated.
- Restored a safe `.env.example` containing no live secret values.
- Added regression coverage for ADMIN, AUDITOR, FINANCE_MANAGER, OPERATIONS_MANAGER and SALES_MANAGER keys.

## External integration hardening
- Added public-HTTPS Graph callback validation and 32–128-character `clientState` validation.
- Made Graph SharePoint byte readback and Stripe Checkout transport contract-testable without remote writes.
- Corrected Release Readiness evidence mapping for SharePoint and Outlook, and separated Teams acknowledgement from verified display.
- Added Vapi API Request / reusable-credential metadata while preserving review-only voice actions.
- Added dedicated external-provider contract tests and verification documentation.

## Runtime and release engineering
- Runtime API container no longer uses Uvicorn `--reload` by default.
- Removed a stale local docker-compose backup from the release payload.
- Added `scripts/provider-contract-verify.sh`.
- Updated release status and reference-release review documentation.
