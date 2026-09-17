# ADR-001: Transaction Engine Owns Business State

**Status:** Accepted

## Context

OrderNexa AI coordinates long-running Customer-to-Cash transactions across AI services, n8n, ERP, CRM, Microsoft 365, voice, payments, and human approvals. The platform must preserve business state even when an integration, workflow, or AI provider fails.

## Decision

OrderNexa AI's custom FastAPI transaction engine is the authoritative owner of business-process state.

n8n is used for integration and workflow orchestration, but it is not the source of truth for transaction state.

## Reason

The platform requires:

- durable transaction state
- idempotency
- checkpoints
- safe replay
- cross-system correlation
- deterministic policies
- auditable transitions
- recovery after partial failure
- read-after-write verification
- provider-independent business logic

These guarantees must remain independent of any workflow vendor.

## Consequences

1. Every business transaction receives a canonical transaction ID.
2. External writes are represented as integration commands with idempotency keys.
3. n8n workflows call OrderNexa APIs instead of owning authoritative process state.
4. AI recommendations are persisted separately from deterministic business decisions.
5. Recovery resumes from verified checkpoints rather than rerunning an entire workflow.
