# OrderNexa AI

**Agentic Customer-to-Cash Operations Platform**

> From messy customer requests to verified business transactions.

## Project status

Stage 0 — Product Foundation.

The complete blueprint remains the scope. V1, V1.5, reliability, governance, AI evaluation, voice, payments, Microsoft 365, ERP/CRM integrations, observability, self-healing recovery, and planned advanced extensions are not removed.

## Core thesis

- AI handles ambiguity.
- Software handles authority.
- ERP handles truth.
- Humans govern consequential exceptions.

## Architecture rule

The custom FastAPI transaction engine owns authoritative business-process state. n8n is used for integration and workflow orchestration, but it is not the source of truth for transaction state.

## Locked stack

- Frontend: Next.js, React, TypeScript, Tailwind CSS, shadcn/ui, Recharts
- Backend: Python, FastAPI, Pydantic, SQLAlchemy, Alembic
- Database: PostgreSQL + pgvector
- Queue/cache: Redis + Celery
- Object storage: MinIO locally / S3-compatible abstraction
- Automation: n8n
- AI: OpenAI + Anthropic behind an AIProvider abstraction
- ERP: Odoo (deep V1 adapter)
- CRM: HubSpot
- Microsoft: Graph, Outlook, Teams, SharePoint
- Voice: Vapi + Twilio
- Payments: Stripe Sandbox
- Observability: OpenTelemetry + structured logging
- Runtime: Docker / Docker Compose
- CI/CD: GitHub Actions

## Development environment

Recommended workstation: Windows 11 + WSL2 + Ubuntu LTS + Docker Desktop + VS Code WSL.

Keep real secrets in `.env` only. Never commit `.env`.
