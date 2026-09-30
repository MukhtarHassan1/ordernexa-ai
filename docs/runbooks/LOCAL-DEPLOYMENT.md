# Archived earlier deployment notes

**Do not use these older commands for the September 29 release.** The project now includes a NEW automation migration and proven Windows-native Ollama connectivity. Follow `docs/runbooks/ORDERNEXA_20260929_INSTALL_AND_FINISH.md` instead. The text below is retained for historical troubleshooting context only.

---

# Applying this release without losing OrderNexa data

**Keep the original `ordernexa-ai-backup-20260928-0020.zip` as a rollback source.**
This release contains a complete sanitized source tree and a smaller overlay
patch. Neither includes your actual `.env`, PostgreSQL/Odoo databases, MinIO
files, Ollama models or n8n persistent state.

1. In Ubuntu: `cd ~/projects/ordernexa-ai` and make sure the project exists.
2. Create ANOTHER local zip or Git snapshot of source (including the private
   `.env` only in a protected, unshared location) before applying new files.
3. Copy the supplied `OrderNexa_Patch_Only.zip` into `~/Downloads` or your WSL
   project directory and apply it with **the project root** as destination:

   ```bash
   cd ~/projects/ordernexa-ai
   unzip -o /path/to/OrderNexa_Patch_Only.zip -d .
   ```

4. Never replace `.env` with `.env.example`. Keep existing private secrets.
   Add **new** local operator credentials (generate independent 32-byte tokens
   for roles, and ensure secrets never go to Git or chat):

   ```bash
   python3 - <<'PY'
   import secrets
   for role in ('SALES_MANAGER','FINANCE_MANAGER','OPERATIONS_MANAGER'):
       print(role, secrets.token_urlsafe(32))
   PY
   ```

   Add one JSON string to PRIVATE `.env` using those newly generated values:

   ```dotenv
   ORDERNEXA_ROLE_KEYS_JSON='{"SALES_MANAGER":"PUT_SALES_SECRET_HERE","FINANCE_MANAGER":"PUT_FINANCE_SECRET_HERE","OPERATIONS_MANAGER":"PUT_OPS_SECRET_HERE"}'
   # If you also have ORDERNEXA_OPERATOR_KEY set, it should be a different key.
   AI_PROVIDER=ollama
   OLLAMA_BASE_URL=http://ollama:11434
   OLLAMA_MODEL=granite3.2-vision:2b
   OLLAMA_READ_TIMEOUT_SECONDS=75
   ```

   If you have duplicate `AI_PROVIDER` or `OLLAMA_BASE_URL` lines in your old
   `.env`, reduce each variable to ONE definitive entry; do not paste the
   entire example over your existing file. CLI tests need the matching
   `X-OrderNexa-Operator-Key` request header.

5. Validate Compose without printing the expanded secrets:

   ```bash
   docker compose config --quiet
   docker compose build api
   docker compose up -d postgres redis minio minio-init api
   curl -sS --max-time 10 http://127.0.0.1:8000/api/v1/health/live
   ```

6. Open the local **Operations Console** in your browser at the API's
   `/console/` path. Click **Operator access** and paste the appropriate local
   role key; it is kept only in the current browser tab. All figures are
   queried from the real database; empty DBs show empty cards.
7. To test the operational core independently of slow AI, use the verified
   **human document review** path. For Odoo ERP demonstrations, start its
   database and Odoo explicitly and bootstrap using the existing private
   shared key; you previously observed working bootstrap and health endpoints.
8. Do **not** run database resets, `docker compose down -v`, repeat seed scripts
   blindly or delete any Ollama model directories. This release has no DB schema
   migration; existing Stage 2 schema remains the source of truth.
9. When ready, run the offline tests inside the API image using dev deps:

   ```bash
   docker compose exec -T api pip install -r requirements-dev.txt
   docker compose exec -T api pytest -q tests
   ```

10. Only after the model produces actual text in the small probe, retry AI
    extraction via the Console. If it fails, the source artifact remains
    available for review or later retry. Do not mistake an HTTP health response
    for model generation.

**Local demo security:** These demo operator keys are not production OAuth
identity. In non-development `APP_ENV`, all sensitive write routes fail closed
until real signed identity, authorization and network controls are implemented.
