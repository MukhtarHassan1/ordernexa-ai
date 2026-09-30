# Release test evidence

Offline checks were performed **without** access to the user's WSL/Docker
Engine, populated Postgres, Odoo database or usable Ollama runner.

- `python -m compileall` — successful for Python modules including the custom
  Odoo addon, the API, and the eval runner.
- Compose YAML parsed with all original services still present and Ollama CPU
  AVX2 settings visible in the release.
- `node --check` — the local Console JavaScript parsed successfully.
- `bash -n` — the Ollama diagnostic script parsed successfully.
- 20 Python unit/contract tests — PASS with external I/O mocked. They cover:
  state-machine guards; exact source-text preservation and human-review
  requirement; test-schema rejection; human operator roles and production
  fail-closed guard; Ollama structured JSON, timeouts and invalid outputs;
  health-vs-inference probe; Graph and HubSpot wire contracts; original artifact
  survival and same-artifact retry; uncertain Odoo read-before-replay with no
  duplicate POST; payload drift refusal; MinIO existing-object reuse and real
  failure DEGRADED behavior; synthetic eval dataset integrity.
- API assembly and static Console smoke test using a **mock database session
  module**: `/`, `/api/v1/health/live`, `/console/`, `/console/app.js` and
  `/console/styles.css` each returned HTTP 200. This does not validate DB
  operation or external integrations.

**Not run:** actual Docker image build, actual migrations/seed, Odoo sales-order
write/verification, native Windows/WSL Ollama generation, real document AI
extraction, browser visual QA, Microsoft OAuth/Graph/Teams/SharePoint,
HubSpot live account sync and 32-case model evaluations.

Only after the operator runs the live checklist can those states be promoted
from unverified to verified. No accuracy, production uptime or percentage-of-
blueprint completion is inferred from mocked tests.
