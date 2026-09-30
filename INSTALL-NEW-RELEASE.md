# September 29 OrderNexa upgrade: start here

**Use the *Upgrade Patch* ZIP inside your existing `~/projects/ordernexa-ai` project. The full ZIP is a sanitized reference source tree, NOT a copy of your live databases, passwords, MinIO files or downloaded Ollama models.** Your previously issued patches are already represented in the new source ZIP; do not replay them over this release.

1. Read **`docs/runbooks/ORDERNEXA_20260929_INSTALL_AND_FINISH.md`** before applying anything. Create a private source backup AND a real PostgreSQL database dump (Odoo/n8n/MinIO separately if preserving disaster-recovery coverage). Never share your backup `.env`.
2. Locate `OrderNexa_20260929_Upgrade_Patch.zip` in Windows Downloads, and in Ubuntu run `unzip -t /mnt/c/Users/Hammad/Downloads/OrderNexa_20260929_Upgrade_Patch.zip`.
3. From your **existing project root** `cd ~/projects/ordernexa-ai`, run `unzip -o /mnt/c/Users/Hammad/Downloads/OrderNexa_20260929_Upgrade_Patch.zip -d .`.
4. Set `export COMPOSE_FILE=docker-compose.yml`. Keep existing `.env`; add the *new* keys described in the guide without pasting it into chat. `docker compose config --quiet`.
5. Start basic services and **apply new DB migration before using new endpoints**: `docker compose up -d postgres redis minio minio-init api && docker compose exec -T api alembic upgrade head`.
6. Run offline tests and the local Operations Console. Leave external writes off and Windows Ollama at your already verified private host endpoint. Resume your existing PO artifact if it exists; do not reupload blindly.
7. Only after the local ERP/recovery slice passes, opt in to the worker, import n8n workflow templates, and request real external account permissions as documented. Teams messages are **notification-only**, Outlook confirmation is initially an **unsent draft**, and Vapi change requests never execute business changes.

If any migration, health or test command fails, **stop at that step** and record the error without running seed/reset/delete commands. The long guide contains recovery and acceptance criteria.
