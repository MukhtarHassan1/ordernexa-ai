# START HERE — OrderNexa 2026-10-02 Development Completion

You asked to finish development first and postpone n8n/live testing. This release follows that instruction.

## Use these files

1. Read `docs/runbooks/ORDERNEXA_20261002_FINAL_UPGRADE.md`.
2. Apply the patch ZIP over your current repository **without replacing `.env`**.
3. Rebuild API/worker images.
4. Run `alembic upgrade head`.
5. Run backend + JS tests in your Docker/WSL environment.
6. Verify worker startup and the local console.
7. Verify a NEW duplicate-PO scenario.
8. Keep n8n testing postponed.
9. Only after the codebase is clean, follow `docs/runbooks/ORDERNEXA_EXTERNAL_LIVE_SETUP.md` integration by integration.

Never run `docker compose down -v` for this upgrade.

The patch deliberately does not contain your `.env`, `.env.before-qwen15-test`, secrets or Docker volumes.
