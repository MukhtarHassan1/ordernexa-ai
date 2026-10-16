# OrderNexa — 2026-10-03 final development patch

This patch is designed to be overlaid on the user's current OrderNexa checkout **without replacing `.env` and without deleting Docker volumes**.

## What is new in this final patch

- robust test tooling so Python/Node checks do not keep failing because of host-vs-container assumptions;
- multi-stage API Dockerfile with an opt-in pytest image;
- `api-tests` and `console-tests` Compose services under the `test` profile;
- `scripts/test-all.sh`, `scripts/final-local-verify.sh`, memory-friendly `core-up.sh`, plus n8n/Odoo/status helpers;
- fixed evaluation validator CLI (`--json-out`) and explicit curation-progress tooling;
- five inactive n8n workflow templates with clear authority boundaries;
- explicit Decision Inspector, Model Routing and evidence-backed Release Readiness views in the Operations Console;
- evidence-backed `/ops/release-readiness` and `/ops/model-routing` endpoints;
- complete safe `.env.example` and an updated non-destructive local env generator;
- new release-quality tests and final owner/live-integration runbooks.

## Fast local verification after overlay

```bash
cd ~/projects/ordernexa-ai
bash scripts/core-up.sh
bash scripts/final-local-verify.sh
```

`final-local-verify.sh` is non-destructive: it does not use `docker compose down -v`, does not turn on external writes and does not rotate secrets.

If your machine is short on RAM, keep Odoo and n8n stopped while testing the core, then start them only when that phase is reached:

```bash
bash scripts/odoo-up.sh
bash scripts/n8n-up.sh
```

## Truth boundary

Source code can be completed and tested offline/local, but no package can honestly pre-verify your Microsoft tenant, SharePoint site grant, HubSpot account, Teams/Outlook delivery, Vapi/Twilio phone path, Stripe account, production OIDC identity provider or human curation of the 500-case evaluation set. Those remaining owner-only steps are documented exactly in `docs/runbooks/ORDERNEXA_20261003_FINAL_OWNER_ACTIONS.md`.
