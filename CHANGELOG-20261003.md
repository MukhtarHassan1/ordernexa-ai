# OrderNexa changelog — 2026-10-03

- Added multi-stage API Dockerfile (`runtime` + `test`).
- Added Compose `test` profile with `api-tests` and `console-tests`.
- Added non-destructive `test-all.sh` and `final-local-verify.sh` plus memory-friendly service helpers.
- Fixed preflight host portability and root-owned `__pycache__` behavior.
- Fixed evaluation validator JSON-output contract and added human-curation progress reporting.
- Added release-quality tests.
- Expanded n8n package from 3 to 5 inactive workflows and documented credential/acceptance setup.
- Added evidence-backed Release Readiness and Model Routing API endpoints.
- Added dedicated Decision Inspector and Release Readiness views to the Operations Console.
- Added comprehensive `.env.example` and safer local env generation.
- Added final owner/live-integration and acceptance runbooks.

No private `.env`, tokens, credentials, Docker volumes or live external systems are included or modified by the patch archive.
