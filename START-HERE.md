# OrderNexa: current installation and development instructions

**September 29 source integration release:** Start with `INSTALL-NEW-RELEASE.md`, then follow `docs/runbooks/ORDERNEXA_20260929_INSTALL_AND_FINISH.md` in order. Do not replay older README-... fixes on top of the current release. Keep the private `.env` and existing Docker volumes; this release **adds a database migration** (`20260929_auto`) and an opt-in worker, unlike the archived older release instructions.

The local Console is at `http://127.0.0.1:8000/console/` after FastAPI starts. Its automation and external sync tabs require your local role-appropriate operator key. Windows-native Ollama remains the configured AI provider, and conflict-triggered human review remains mandatory until independently curated evaluation proves otherwise.

`RELEASE-STATUS.md` separates code actually present from genuinely live-verified integrations. `docs/architecture/20260929_BLUEPRINT_GAP_AND_EVIDENCE.md` maps the 38-page NECTELIS scope. The current source files alone cannot activate your external Microsoft, HubSpot, Vapi or Stripe accounts.
