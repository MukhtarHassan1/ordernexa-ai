from pathlib import Path
import json
import secrets

ENV_PATH = Path(".env")
if ENV_PATH.exists():
    raise SystemExit(
        ".env already exists. Refusing to overwrite it. "
        "Back it up first; never regenerate secrets over a working environment."
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
odoo_secret = secret(32)
n8n_ingest = secret(32)
voice_secret = secret(32)
role_keys = {
    "SALES_MANAGER": secret(32),
    "FINANCE_MANAGER": secret(32),
    "OPERATIONS_MANAGER": secret(32),
    "ADMIN": secret(32),
    "AUDITOR": secret(32),
}

content = f"""# OrderNexa AI - generated local development secrets
# Role keys are authoritative; the legacy single operator key is intentionally blank.
APP_NAME=OrderNexa AI
APP_ENV=development
APP_DEBUG=false
APP_SECRET={app_secret}
API_HOST=0.0.0.0
API_PORT=8000
FRONTEND_URL=http://localhost:8000
BACKEND_URL=http://localhost:8000
TRUSTED_HOSTS=localhost,127.0.0.1,testserver,api

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
ODOO_BASE_URL=http://odoo:8069
ORDERNEXA_ODOO_SHARED_SECRET={odoo_secret}

N8N_DB_NAME=n8n
N8N_DB_USER=n8n
N8N_DB_PASSWORD={n8n_password}
N8N_ENCRYPTION_KEY={n8n_encryption_key}
N8N_WEBHOOK_URL=http://localhost:5678/
N8N_INGEST_SECRET={n8n_ingest}

AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen2.5:0.5b
OLLAMA_TEXT_MODEL=qwen2.5:0.5b
OLLAMA_VISION_MODEL=
OLLAMA_PROBE_MODEL=qwen2.5:0.5b
OPENAI_API_KEY=
ANTHROPIC_API_KEY=

AUTH_MODE=auto
ORDERNEXA_OPERATOR_KEY=
ORDERNEXA_OPERATOR_ACTOR=LOCAL_OPERATOR
ORDERNEXA_OPERATOR_ROLE=OPERATIONS_MANAGER
ORDERNEXA_ROLE_KEYS_JSON={json.dumps(role_keys, separators=(',', ':'))}
OIDC_ISSUER=
OIDC_AUDIENCE=
OIDC_JWKS_URL=
OIDC_ROLE_MAP_JSON={{}}

AUTOMATION_WORKER_ENABLED=false
AUTOMATION_LIVE_WRITES=false
CUSTOMER_EMAIL_ENABLED=false
GRAPH_TENANT_ID=
GRAPH_CLIENT_ID=
GRAPH_CLIENT_SECRET=
GRAPH_MAILBOX=
GRAPH_CLIENT_STATE=
GRAPH_NOTIFICATION_URL=
GRAPH_LIFECYCLE_URL=
GRAPH_SUBSCRIPTION_RESOURCE=
GRAPH_DRIVE_ID=
HUBSPOT_ACCESS_TOKEN=
TEAMS_APPROVAL_WEBHOOK_URL=
VOICE_SERVER_SECRET={voice_secret}

STRIPE_ENABLED=false
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
ASK_OPS_ENABLED=true
"""

ENV_PATH.write_text(content, encoding="utf-8")
print("Created .env successfully.")
print("Keep this file private. It is intentionally ignored by Git.")
print("Do not paste generated role keys or secrets into chat, tickets, or screenshots.")
