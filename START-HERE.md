# Start Here

This ZIP creates the OrderNexa AI project foundation. It intentionally does not install FastAPI, Next.js, Odoo, n8n, or other dependencies yet.

## Recommended active location

You can keep this ZIP on `E:\` as a backup. For best WSL/Docker performance, use the active working copy inside the Ubuntu filesystem, for example:

`~/projects/ordernexa-ai`

## Verify Windows / WSL

From PowerShell:

```powershell
wsl --version
wsl --status
wsl -l -v
```

## Verify the Ubuntu development environment

From WSL, inside the project:

```bash
bash infra/scripts/verify-wsl-env.sh
```

## Open in VS Code WSL

```bash
cd ~/projects/ordernexa-ai
code .
```

## Initialize local Git only

```bash
git init
git branch -M main
```

No remote is configured, so nothing is uploaded to GitHub.

## Next stage

Stage 1 configures the real Docker Compose infrastructure:

- PostgreSQL + pgvector
- Redis
- MinIO
- Odoo + Odoo database
- n8n
