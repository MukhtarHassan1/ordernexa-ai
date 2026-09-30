# OrderNexa AI

### Agentic Customer-to-Cash Operations Platform

> From messy customer requests to verified business transactions.

**OrderNexa AI** is a production-style B2B Customer-to-Cash automation platform built to demonstrate how AI can participate safely in real operational workflows.

Instead of allowing an LLM to directly create business transactions, OrderNexa separates probabilistic AI reasoning from deterministic business authority:

> **AI handles ambiguity. Software handles authority. ERP handles truth. Humans govern consequential exceptions.**

The platform converts purchase orders and other unstructured customer requests into structured transactions, validates them against authoritative business data, routes exceptions for human approval, executes approved ERP actions exactly once, verifies downstream results, preserves evidence, and maintains a recoverable transaction history.

OrderNexa is being developed as the flagship AI Automation project for the **NECTELIS Upwork agency portfolio**.

---

## Project Status

### Current verified milestone

A complete local Customer-to-Cash transaction has been successfully demonstrated:

```text
Purchase Order
      ↓
Document Intake
      ↓
Local AI Extraction
      ↓
Source Grounding
      ↓
Human Review
      ↓
Customer Resolution
      ↓
Product / SKU Resolution
      ↓
Contract Pricing
      ↓
Inventory & Fulfillment
      ↓
Credit Validation
      ↓
Policy Engine
      ↓
Sales + Finance Approval
      ↓
Verified Odoo Sales Order
      ↓
Verified MinIO Archive
      ↓
COMPLETED Transaction
```

The canonical demonstration transaction reached:

```text
Transaction: TXN-2026-000036
Customer PO: PO-88192
Customer: Northstar Engineering Ltd
Order value: GBP 13,995
Risk: HIGH
Final status: COMPLETED
```

Verified downstream operations:

```text
ODOO        CREATE_SALE_ORDER      VERIFIED
MINIO_LOCAL ARCHIVE_CONFIRMATION   VERIFIED
```

Verified checkpoints:

```text
DRAFT_VALIDATED        VERIFIED
ERP_ORDER_CREATED      VERIFIED
DOCUMENT_ARCHIVED      VERIFIED
```

The durable automation worker is also operational with external writes disabled by default.

---

# Why OrderNexa Exists

Many B2B businesses still process orders through:

- email
- PDF purchase orders
- spreadsheets
- phone calls
- manually entered ERP records
- disconnected CRM systems
- human approval chains

A conventional LLM workflow can extract text, but real business operations require much more.

For example:

- Is the customer real?
- Which account should the order belong to?
- Does a customer product alias map to an actual SKU?
- Is the requested price contractually valid?
- Is sufficient inventory available?
- Which warehouses should fulfill the order?
- Will the order exceed the customer's credit limit?
- Who is authorized to approve the exception?
- Has this exact order already been created?
- Did the ERP actually persist the sales order?
- What happens if archival fails after ERP creation?
- Can the workflow resume without creating another ERP order?

OrderNexa is designed around those operational questions.

---

# Core Design Principle

OrderNexa deliberately prevents the AI model from becoming the system of record.

## AI is allowed to

- interpret messy documents
- classify intent
- extract candidate fields
- recommend customer matches
- recommend SKU matches
- summarize evidence
- explain exceptions
- generate communication drafts
- assist with operational analysis

## AI is not allowed to independently

- determine executable pricing
- bypass credit limits
- modify contract terms
- invent inventory
- approve high-risk transactions
- perform unrestricted ERP writes
- change payment destinations
- execute arbitrary code or SQL

Business-critical authority remains in deterministic services and systems of record.

---

# Architecture

```text
┌──────────────────────────────────────────────────────────┐
│                       CHANNELS                           │
│                                                          │
│ Email │ File Upload │ PDF │ Excel │ Image │ API │ Voice │
└─────────────────────────────┬────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────┐
│                 FASTAPI INTAKE GATEWAY                  │
│                                                          │
│ Validation │ Authentication │ Deduplication │ Artifacts  │
└─────────────────────────────┬────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────┐
│                  DOCUMENT INTELLIGENCE                  │
│                                                          │
│ Ollama │ Schema Validation │ Source Grounding │ Review   │
└─────────────────────────────┬────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────┐
│                 TRANSACTION DIGITAL TWIN                │
│                                                          │
│ PostgreSQL │ Events │ Evidence │ Decisions │ Checkpoints │
└─────────────────────────────┬────────────────────────────┘
                              │
              ┌───────────────┼────────────────┐
              ▼               ▼                ▼
       Customer Service   Product Service   Knowledge/RAG
              │               │                │
              └───────────────┼────────────────┘
                              ▼
┌──────────────────────────────────────────────────────────┐
│              DETERMINISTIC BUSINESS SERVICES            │
│                                                          │
│ Pricing │ Inventory │ Fulfillment │ Credit │ Policy      │
└─────────────────────────────┬────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────┐
│                    APPROVAL CENTER                      │
│                                                          │
│ Sales Manager │ Finance Manager │ Operations Manager     │
└─────────────────────────────┬────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────┐
│                INTEGRATION COMMAND LAYER                │
│                                                          │
│ Odoo │ MinIO │ Microsoft 365 │ HubSpot │ n8n │ Voice    │
└─────────────────────────────┬────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────┐
│              VERIFICATION & RECOVERY                    │
│                                                          │
│ Idempotency │ Read-after-write │ Retry │ Recovery        │
└─────────────────────────────┬────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────┐
│                 OPERATIONS CONSOLE                      │
│                                                          │
│ Transactions │ Approvals │ Recovery │ Audit │ AI Health  │
└──────────────────────────────────────────────────────────┘
```

The custom application owns authoritative transaction state.

**n8n is an orchestration/integration layer, not the source of truth.**

---

# Technology Stack

## Backend

- Python 3.12
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- AsyncPG

## Data

- PostgreSQL
- pgvector
- Redis
- MinIO / S3-compatible object storage

## AI

- Ollama
- Qwen 2.5 text model
- Granite vision model
- structured Pydantic outputs
- deterministic source grounding
- prompt/version tracking
- evaluation infrastructure

Development currently uses Windows-native Ollama while the application runs inside Docker/WSL.

## ERP

- Odoo Community
- custom `ordernexa_connector`
- authenticated integration endpoints
- idempotent command handling
- read-after-write verification

## Automation

- n8n Community
- PostgreSQL-backed durable automation queue
- dedicated background worker
- idempotent ingress
- bounded retry architecture
- recovery/reconciliation controls

## Frontend

Current implementation:

- responsive OrderNexa Operations Console
- served with the application
- transaction inbox
- decision inspector
- approval center
- recovery center
- document intake
- automation queue
- integration health
- voice review
- audit explorer

## Infrastructure

- Docker
- Docker Compose
- Ubuntu / WSL2
- Git / GitHub

---

# AI Document Safety

The document pipeline does not automatically trust model output.

The extraction process is:

```text
Original Document
      ↓
AI Structured Extraction
      ↓
Schema Validation
      ↓
Source Grounding
      ↓
Conflict Detection
      ↓
Risk Flags
      ↓
Human Review when necessary
```

Example source-grounding safeguards include:

- multiline field parsing
- PO number verification
- customer verification
- currency verification
- requested-delivery-date verification
- line-item verification
- requested-price verification
- evidence references
- suspicious customer-domain rejection
- conflicting duplicate-field detection
- ambiguous date handling
- prompt-injection indicators
- unverified image extraction review gates
- noncanonical model-confidence handling

A schema-valid model response is **not** automatically considered factually correct.

---

# Model Confidence Is Not Authority

OrderNexa treats model-reported confidence as untrusted metadata.

For example, a model may return:

```json
{
  "overall_confidence": 100
}
```

while the schema expects:

```text
0.0 → 1.0
```

OrderNexa normalizes the format while preserving the original response and can still force human review.

Likewise, high model confidence cannot override contradictory source evidence.

---

# Canonical Demonstration Scenario

The fictional demonstration company is:

```text
Atlas Industrial Systems
```

The customer is:

```text
Northstar Engineering Ltd
```

Example purchase order:

```text
PO Number: PO-88192

40 × XTR-42
Requested price: GBP 260.00

15 × BRK-90
Requested price: GBP 165.00

Delivery:
Manchester, United Kingdom

Requested date:
30 September 2026
```

Customer aliases are resolved to authoritative SKUs:

```text
XTR-42 → XTR-420
BRK-90 → BRK-090
```

Authoritative pricing determines:

```text
XTR-420 = GBP 288.00
BRK-090 = GBP 165.00
```

Resulting authoritative order value:

```text
GBP 13,995
```

The system detects:

```text
REQUESTED_PRICE_DIFFERS_FROM_EXECUTABLE_PRICE
CREDIT_LIMIT_EXCEEDED
MULTI_WAREHOUSE_FULFILLMENT
```

The transaction therefore requires authorized Sales and Finance approval before ERP execution.

---

# Inventory & Fulfillment

The canonical transaction demonstrates distributed inventory.

Example XTR-420 allocation:

```text
Manchester Warehouse   20
London Warehouse       11
Rotterdam Warehouse     9
                       --
                       40
```

Example BRK-090 allocation:

```text
Manchester Warehouse   10
London Warehouse        5
                       --
                       15
```

Inventory availability and fulfillment allocation are deterministic business calculations rather than LLM decisions.

---

# Credit & Policy Engine

The demonstration customer has:

```text
Current exposure:       GBP 88,000
New order:              GBP 13,995
Projected exposure:     GBP 101,995
Credit limit:           GBP 100,000
```

This triggers a Finance Manager approval.

The pricing discrepancy separately triggers a Sales Manager approval.

Only after all required approvals are recorded can the transaction reach:

```text
READY
```

---

# Role-Based Approval

OrderNexa currently supports local role-specific operator authorization.

Example roles:

```text
SALES_MANAGER
FINANCE_MANAGER
OPERATIONS_MANAGER
```

Approval decisions are persisted in the transaction audit history.

A user cannot substitute an Operations Manager credential for a Sales or Finance approval when policy requires those roles.

---

# Exactly-Once ERP Execution

ERP writes are treated as integration commands rather than direct controller actions.

Before execution OrderNexa persists:

- transaction ID
- command action
- request information
- idempotency key
- command status

After the external call, the platform performs read-after-write verification.

The canonical transaction produced:

```text
Provider: ODOO
Action: CREATE_SALE_ORDER
Status: VERIFIED
External ID: 1
Attempts: 1
```

Repeated execution of the same committed command is prevented.

Additional cross-transaction customer-PO duplicate hardening remains part of the reliability roadmap before unattended execution is enabled.

---

# Object Storage & Archival

Original documents and generated transaction artifacts are stored in MinIO.

The completed demonstration produced:

```text
transactions/TXN-2026-000036/confirmation.json
```

The archive was written and subsequently verified.

Recorded integration result:

```text
Provider: MINIO_LOCAL
Action: ARCHIVE_CONFIRMATION
Status: VERIFIED
```

---

# Transaction Digital Twin

Every request becomes a durable business transaction.

The transaction stores and links information such as:

- source channel
- customer reference
- normalized intent
- customer resolution
- order lines
- evidence
- AI decisions
- policy decisions
- approvals
- integration commands
- checkpoints
- incidents
- external IDs
- timestamps
- correlation identifiers

Example lifecycle:

```text
RECEIVED
   ↓
TRIAGED
   ↓
EXTRACTED
   ↓
CUSTOMER_RESOLUTION
   ↓
PRODUCT_RESOLUTION
   ↓
PRICING_CHECK
   ↓
INVENTORY_CHECK
   ↓
CREDIT_CHECK
   ↓
APPROVAL_REQUIRED
   ↓
READY
   ↓
ERP_CREATED
   ↓
COMPLETED
```

Exception states are also supported for recoverable and manual failure scenarios.

---

# Audit & Evidence

OrderNexa records business events rather than relying only on application logs.

Example timeline events include:

```text
TRANSACTION_RECEIVED
INTENT_CLASSIFIED
ORDER_SCHEMA_VALIDATED
CUSTOMER_RESOLUTION_STARTED
CUSTOMER_RESOLVED
PRODUCTS_RESOLVED
PRICING_VALIDATED
INVENTORY_VALIDATED
POLICY_APPROVAL_REQUIRED
ORIGINAL_DOCUMENT_HUMAN_CONFIRMED
APPROVAL_APPROVED
ALL_APPROVALS_GRANTED
ERP_COMMAND_PERSISTED
ERP_ORDER_VERIFIED
DOCUMENT_ARCHIVED
```

This makes it possible to reconstruct why a transaction reached its final state.

---

# Recovery Architecture

OrderNexa is designed so a partial integration failure does not restart the entire transaction.

Example:

```text
Odoo order created successfully
        ↓
SharePoint archival fails
        ↓
DO NOT recreate Odoo order
        ↓
Mark transaction degraded
        ↓
Retry/recover only SharePoint
        ↓
Continue downstream workflow
```

The reliability layer includes concepts for:

- checkpoints
- idempotency
- bounded retries
- failure classification
- reconciliation
- incident tracking
- safe replay
- external-state verification

Full scripted failure-injection coverage is still being expanded.

---

# Durable Automation Worker

A dedicated optional worker processes persistent automation jobs.

Current verified worker startup:

```text
Worker started; external writes: False
```

External integrations remain disabled by default:

```dotenv
AUTOMATION_LIVE_WRITES=false
```

This prevents development/test events from automatically modifying remote systems.

---

# n8n Integration

OrderNexa includes importable n8n workflow templates under:

```text
workflows/n8n/
```

Current templates include:

```text
OrderNexa_01_Manual_Synthetic_Intake.json
OrderNexa_02_Authenticated_Intake_Bridge.json
OrderNexa_03_Readonly_KPI_Digest.json
```

The intended relationship is:

```text
External Trigger
      ↓
n8n
      ↓
Authenticated OrderNexa Intake
      ↓
Persistent Automation Job
      ↓
OrderNexa Worker
      ↓
Authoritative Transaction Engine
```

n8n does not bypass business policy or directly control authoritative transaction state.

Live n8n integration verification is the current development milestone.

---

# Microsoft 365 Integration

The architecture includes Microsoft Graph support for:

- Outlook mailbox intake
- purchase-order attachment retrieval
- Graph webhook notifications
- subscription lifecycle
- SharePoint archival
- Outlook customer communication
- Teams notifications / approval context

Environment placeholders include:

```dotenv
GRAPH_TENANT_ID=
GRAPH_CLIENT_ID=
GRAPH_CLIENT_SECRET=
GRAPH_MAILBOX=
GRAPH_DRIVE_ID=
GRAPH_CLIENT_STATE=
GRAPH_SUBSCRIPTION_ID=
TEAMS_APPROVAL_WEBHOOK_URL=
```

These integrations require an authorized Microsoft 365 tenant and remain disabled until real permissions and external behavior are verified.

---

# CRM Integration

HubSpot is the planned CRM implementation behind the CRM adapter.

Target behavior includes:

```text
Resolve / synchronize customer
        ↓
Record transaction activity
        ↓
Attach resulting order context
```

Live HubSpot credentials and synchronization are not yet asserted as completed.

---

# Voice Transaction Assistant

OrderNexa includes guarded backend capabilities for future Vapi/Twilio integration.

The voice channel is intended to:

- retrieve a transaction
- report permitted order status
- collect customer requests
- create a controlled change request
- route changes for human/business-policy review

The voice assistant is **not** permitted to directly alter an ERP order or approve consequential changes.

---

# Evaluation & AI Quality

OrderNexa contains:

- extraction regression tests
- source-grounding tests
- adversarial cases
- policy safety tests
- structured-output validation
- local Ollama evaluation utilities
- evaluation result infrastructure
- generated synthetic evaluation data

A generated dataset of approximately 500 examples is included as:

```text
UNCURATED / REQUIRES HUMAN REVIEW
```

It must not be represented as a completed benchmark until examples are independently reviewed and labeled.

Current architecture distinguishes:

```text
RAW MODEL ACCURACY
        vs
SOURCE-GROUNDED PIPELINE ACCURACY
```

This prevents deterministic corrections from being incorrectly counted as model intelligence.

---

# Security Principles

OrderNexa is designed around several safety rules:

- secrets remain outside source control
- `.env` is excluded from Git
- role-based authorization
- restricted integration commands
- server-side business-policy enforcement
- AI outputs are validated before use
- external documents are treated as untrusted input
- prompt-injection defenses
- no arbitrary LLM-generated API calls
- no arbitrary LLM-generated SQL execution
- no AI-authoritative pricing
- no automatic credit override
- human approval for consequential exceptions
- explicit external-write switch
- audit logging
- idempotency keys
- read-after-write verification

---

# Operations Console

Local console:

```text
http://localhost:8000/console/
```

Current screens include:

### Operations Overview

Business-level metrics including:

- transaction volume
- order value
- approvals
- blocked revenue
- verified ERP orders
- completed transactions
- incidents
- recorded AI decisions

### Transaction Inbox

Search and filter transactions by:

- transaction ID
- purchase-order reference
- state

### Decision Inspector

Displays:

- policy outcome
- source-derived evidence
- customer resolution
- product resolution
- contract pricing
- fulfillment evidence
- credit position
- audit timeline
- checkpoints
- permitted next operation

### Approval Center

Role-aware:

- approve
- reject
- inspect evidence
- future Teams notification

### Recovery Center

For failed or degraded operations requiring safe recovery.

### Document Intake

Supports:

- upload
- extraction
- artifact status
- human review
- transaction creation

### Integrations & AI

Displays integration and model health.

### Automation Queue

Displays:

- integration readiness
- persistent jobs
- external-sync controls

### Voice Review

Human review for voice-originated change requests.

### Audit Explorer

Searchable operational history.

---

# Repository Structure

The repository broadly follows this structure:

```text
ordernexa-ai/
│
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── api/
│   │   │   ├── automation/
│   │   │   ├── core/
│   │   │   ├── db/
│   │   │   ├── models/
│   │   │   ├── schemas/
│   │   │   └── services/
│   │   ├── alembic/
│   │   ├── tests/
│   │   └── tools/
│   │
│   └── ...
│
├── evals/
│   ├── datasets/
│   └── runners/
│
├── infra/
│   ├── docker/
│   └── scripts/
│
├── integrations/
│
├── sample-data/
│   └── purchase-orders/
│
├── workflows/
│   └── n8n/
│
├── docs/
│   ├── architecture/
│   ├── adr/
│   ├── demo/
│   ├── runbooks/
│   └── security/
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

# Local Development Requirements

Recommended environment:

```text
Windows 10/11
WSL2
Ubuntu 24.04
Docker Desktop
Docker Compose
Python 3.12
Git
Windows-native Ollama
```

The current development machine uses an 8 GB system, so services are intentionally started selectively to reduce memory pressure.

---

# Quick Start

Clone the repository:

```bash
git clone https://github.com/YOUR_USERNAME/ordernexa-ai.git
cd ordernexa-ai
```

Create your local environment configuration:

```bash
cp .env.example .env
```

Populate local secrets and configuration values.

Never commit `.env`.

Validate Compose:

```bash
export COMPOSE_FILE=docker-compose.yml
docker compose config --quiet
```

Start the core services:

```bash
docker compose up -d \
  postgres \
  redis \
  minio \
  minio-init \
  api
```

Apply migrations:

```bash
docker compose exec -T api alembic upgrade head
```

Verify API readiness:

```bash
curl -sS \
  http://127.0.0.1:8000/api/v1/health/ready
```

Open:

```text
http://localhost:8000/console/
```

---

# Local Ollama

OrderNexa currently uses Windows-native Ollama from the Docker API container:

```dotenv
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434

OLLAMA_TEXT_MODEL=qwen2.5:1.5b
OLLAMA_VISION_MODEL=granite3.2-vision:2b
```

The provider layer keeps model access separate from business logic so additional AI providers can be integrated later.

---

# Start Automation Worker

Enable:

```dotenv
AUTOMATION_WORKER_ENABLED=true
AUTOMATION_LIVE_WRITES=false
```

Build:

```bash
docker compose \
  --profile automation \
  build automation-worker
```

Start:

```bash
docker compose \
  --profile automation \
  up -d automation-worker
```

Check:

```bash
docker compose \
  --profile automation \
  logs --tail=50 automation-worker
```

---

# Start n8n

```bash
docker compose up -d n8n-db n8n
```

Open:

```text
http://localhost:5678
```

Import the supplied workflow templates from:

```text
workflows/n8n/
```

---

# Start Odoo

Odoo can be started only when ERP functionality is required:

```bash
docker compose up -d odoo-db odoo
```

Open:

```text
http://localhost:8069
```

The current demonstration database is:

```text
atlas_industrial
```

The custom OrderNexa connector provides authenticated ERP integration endpoints.

---

# Tests

Install development requirements if necessary:

```bash
docker compose exec -T api \
  python -m pip install -r requirements-dev.txt
```

Run the backend test suite:

```bash
docker compose exec -T api \
  python -m pytest -q tests
```

At the current milestone the project has passed:

```text
89 backend tests
```

plus frontend/JavaScript contract checks during the release build.

External Microsoft, HubSpot, n8n, Vapi and other live-provider behavior must be independently tested after their credentials are configured.

---

# Environment Safety

The following must never be committed:

```text
.env
API keys
client secrets
operator keys
database passwords
OAuth secrets
Twilio auth tokens
Vapi credentials
Stripe secrets
private access tokens
```

`.env.example` should contain variable names and safe placeholders only.

---

# Current Completion Matrix

| Capability | Status |
|---|---|
| Transaction Digital Twin | ✅ Implemented |
| PostgreSQL state and audit | ✅ Implemented |
| Multi-format local document intake | ✅ Implemented |
| Ollama extraction | ✅ Implemented |
| Source grounding | ✅ Implemented |
| Human document review | ✅ Implemented |
| Customer resolution | ✅ Implemented |
| SKU alias resolution | ✅ Implemented |
| Contract pricing authority | ✅ Implemented |
| Inventory allocation | ✅ Implemented |
| Credit validation | ✅ Implemented |
| Policy engine | ✅ Implemented |
| Role-based approvals | ✅ Implemented |
| Odoo connector | ✅ Implemented |
| Verified Odoo execution | ✅ Live local verification completed |
| MinIO document storage | ✅ Implemented |
| Verified confirmation archive | ✅ Live local verification completed |
| Operations dashboard | ✅ Implemented |
| Approval Center | ✅ Implemented |
| Decision Inspector | ✅ Implemented |
| Automation worker | ✅ Running |
| Persistent automation jobs | ✅ Implemented |
| n8n workflow templates | ✅ Included |
| n8n live intake test | 🚧 Current milestone |
| Failure/recovery hardening | 🚧 In progress |
| Cross-transaction duplicate protection | 🚧 Hardening required |
| Microsoft Graph email intake | 🚧 Integration pending |
| SharePoint live archive | 🚧 Integration pending |
| HubSpot live sync | 🚧 Integration pending |
| Teams live integration | 🚧 Integration pending |
| Outlook live customer messaging | 🚧 Integration pending |
| Vapi/Twilio live voice assistant | 🚧 Integration pending |
| AI Quality Lab full benchmark | 🚧 Dataset/evaluation work remaining |
| Progressive autonomy | 🚧 Planned V1.5 |
| Ask Ops AI | 🚧 Planned V1.5 |
| Stripe sandbox | 🚧 Planned V1.5 |
| Production deployment | 🚧 Final release stage |

---

# Roadmap

## Phase 1 — Product Foundation

- architecture
- environment
- Docker infrastructure
- data model
- security principles

**Status: completed**

## Phase 2 — Transaction Core

- transaction lifecycle
- digital twin
- events
- evidence
- checkpoints

**Status: completed**

## Phase 3 — Document Intelligence

- document ingestion
- Ollama extraction
- schema validation
- source grounding
- human review

**Status: completed for local demonstration**

## Phase 4 — Business Validation

- customer resolution
- SKU resolution
- pricing
- inventory
- credit
- policy

**Status: completed**

## Phase 5 — Approvals & ERP

- role-specific approvals
- Odoo commands
- idempotency
- verification

**Status: completed for verified local transaction**

## Phase 6 — Automation & Integrations

- durable worker
- n8n
- Microsoft Graph
- SharePoint
- HubSpot
- Teams
- Outlook

**Status: in progress**

## Phase 7 — Reliability & Recovery

- failure injection
- retry classification
- safe replay
- duplicate protection
- reconciliation

**Status: in progress**

## Phase 8 — AI Quality & Security

- curated evaluation dataset
- regression gates
- adversarial tests
- shadow mode
- security hardening

**Status: in progress**

## Phase 9 — Voice & Advanced Operations

- Vapi
- Twilio
- change requests
- Ask Ops AI
- progressive autonomy
- Stripe sandbox

**Status: planned after core V1 integrations**

## Phase 10 — Portfolio Release

- final UI polish
- architecture diagrams
- screenshots
- benchmark report
- deployment documentation
- 4–6 minute demonstration
- Upwork case study

**Status: pending final integration completion**

---

# Important Scope Statement

OrderNexa is intentionally being developed as a **production-style portfolio system**, not represented as a production-certified commercial platform.

The current repository demonstrates substantial working local functionality, including a successfully completed Customer-to-Cash transaction.

The following are **not yet claimed as live-complete**:

- Microsoft 365 production integration
- HubSpot production integration
- Vapi/Twilio production voice calls
- Stripe payments
- autonomous L4 ERP execution
- fully curated 500-case model benchmark
- production OAuth/OIDC
- multi-tenant production deployment
- production SLA or compliance certification

These capabilities will only be marked completed after actual integration and verification.

---

# Portfolio Goal

OrderNexa is intended to demonstrate capabilities relevant to higher-value AI Automation and Systems Integration projects:

- AI + backend engineering
- document intelligence
- deterministic business rules
- ERP integration
- CRM integration
- Microsoft 365 integration
- workflow automation
- human-in-the-loop governance
- API development
- database architecture
- AI safety
- idempotency
- failure recovery
- observability
- testing
- containerized deployment

The goal is not to demonstrate the largest number of AI agents.

The goal is to demonstrate that AI can be engineered responsibly into a real transactional business workflow.

---

## OrderNexa AI

**From messy customer requests to verified business transactions.**

Built as the NECTELIS flagship Customer-to-Cash AI Automation project.
