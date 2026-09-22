from pathlib import Path
import secrets


ENV_PATH = Path(".env")

if ENV_PATH.exists():
    raise SystemExit(
        ".env already exists. Refusing to overwrite it. "
        "Delete it manually only if you intentionally want new local secrets."
    )


def secret(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


postgres_password = secret()
redis_password = secret()
minio_password = secret()
odoo_password = secret()
n8n_password = secret()
n8n_encryption_key = secret(48)
app_secret = secret(48)

content = f"""# OrderNexa AI - generated local development secrets

APP_NAME=OrderNexa AI
APP_ENV=development
APP_DEBUG=true
APP_SECRET={app_secret}
API_HOST=0.0.0.0
API_PORT=8000
FRONTEND_URL=http://localhost:3000
BACKEND_URL=http://localhost:8000

POSTGRES_DB=ordernexa
POSTGRES_USER=ordernexa
POSTGRES_PASSWORD={postgres_password}
DATABASE_URL=postgresql+asyncpg://ordernexa:{postgres_password}@postgres:5432/ordernexa

REDIS_PASSWORD={redis_password}
REDIS_URL=redis://:{redis_password}@redis:6379/0

MINIO_ROOT_USER=ordernexa
MINIO_ROOT_PASSWORD={minio_password}
MINIO_ENDPOINT=http://minio:9000
MINIO_PUBLIC_ENDPOINT=http://localhost:9000
MINIO_BUCKET=ordernexa-artifacts

ODOO_DB_USER=odoo
ODOO_DB_PASSWORD={odoo_password}
ODOO_DB_NAME=postgres
ODOO_URL=http://odoo:8069
ODOO_PUBLIC_URL=http://localhost:8069

N8N_DB_NAME=n8n
N8N_DB_USER=n8n
N8N_DB_PASSWORD={n8n_password}
N8N_ENCRYPTION_KEY={n8n_encryption_key}
N8N_BASE_URL=http://localhost:5678
N8N_WEBHOOK_URL=http://localhost:5678/

AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434

OPENAI_API_KEY=
ANTHROPIC_API_KEY=

HUBSPOT_ACCESS_TOKEN=

AZURE_TENANT_ID=
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=

VAPI_API_KEY=

TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=

STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

OTEL_SERVICE_NAME=ordernexa-api
OTEL_EXPORTER_OTLP_ENDPOINT=
"""

ENV_PATH.write_text(content, encoding="utf-8")

print("Created .env successfully.")
print("Keep this file private. It is intentionally ignored by Git.")