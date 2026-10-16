# OrderNexa AI — 2026-10-04 reference release

This release is a **non-destructive hardening and product-polish update** over the supplied `OrderNexa_Current_20261004_0109.zip` source. It keeps the existing transaction model, database migrations, Odoo flow, n8n authority boundary and private environment model intact.

## What changed

- active product branding is now **OrderNexa AI / Atlas Industrial Systems**; legacy `NECTELIS / ATLAS DEMO` branding is removed from the Operations Console;
- the legacy local operator key is no longer generated with the same secret as `OPERATIONS_MANAGER`, preventing conflicting-role authentication;
- Microsoft Graph callback validation now rejects local/private destinations and invalid clientState lengths before a live subscription attempt;
- Graph/SharePoint/Outlook/Stripe transports are easier to contract-test with injected HTTP clients;
- Release Readiness now counts the actual provider/action pairs persisted by the worker (for example Microsoft Graph `ARCHIVE_SHAREPOINT` and `CREATE_OUTLOOK_DRAFT`), and does not treat a Teams webhook acknowledgement as visible-delivery proof;
- Vapi reference contracts explicitly use the API Request tool / reusable credential boundary;
- provider mocks cover Graph subscription, SharePoint upload/readback, Outlook draft, Teams URL safety, HubSpot, Vapi/Twilio boundaries and Stripe Checkout safety;
- runtime API image no longer defaults to Uvicorn `--reload`;
- console polish adds stronger focus states, selected navigation, responsive feedback, last-refresh visibility and keyboard shortcuts while preserving the existing same-origin architecture;
- safe `.env.example` is restored and release-quality tests protect the five-role configuration.

## Fast verification

```bash
cd ~/projects/ordernexa-ai
bash scripts/core-up.sh
bash scripts/final-local-verify.sh
```

Offline provider contracts (no remote writes):

```bash
bash scripts/provider-contract-verify.sh
```

## Safety / upgrade rules

- Do **not** overwrite a working private `.env` with `.env.example`.
- Do **not** run `docker compose down -v` as part of an upgrade.
- Do **not** rotate `N8N_ENCRYPTION_KEY` or database passwords merely to apply this source update.
- Keep `ORDERNEXA_OPERATOR_KEY=` empty when `ORDERNEXA_ROLE_KEYS_JSON` is configured.
- Keep `AUTOMATION_LIVE_WRITES=false` until the target provider account and destination have been reviewed.

## Evidence boundary

Passing mocks prove source contracts and safety behavior, not third-party account provisioning. Microsoft 365, Vapi/Twilio, HubSpot, Teams and Stripe still require owner credentials for a live-provider claim. The generated 500-case evaluation dataset remains ineligible for accuracy claims until human curation is complete.

See:

- `RELEASE-STATUS.md`
- `docs/testing/20261004_REFERENCE_RELEASE_REVIEW.md`
- `docs/testing/EXTERNAL_PROVIDER_CONTRACT_MATRIX.md`
