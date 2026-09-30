"""Database-owned automation jobs. No n8n workflow owns business state."""
import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.automation import AutomationJob


class IdempotencyConflict(ValueError):
    pass


def canonical_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def verify_webhook_secret(provided: str | None, expected: str) -> bool:
    return bool(expected and len(expected) >= 32 and provided and hmac.compare_digest(provided, expected))


def graph_event_id(subscription: str, message_id: str) -> str:
    return 'graph:' + hashlib.sha256(f'{subscription}\x00{message_id}'.encode()).hexdigest()


async def publish_job(session: AsyncSession, *, key: str, kind: str,
                      payload: dict, transaction_id: UUID | None = None,
                      requested_by: str = 'SYSTEM') -> tuple[AutomationJob, bool]:
    if not key or len(key) > 200:
        raise ValueError('Invalid durable idempotency key.')
    request_hash = canonical_hash({'kind': kind, 'payload': payload, 'tx': str(transaction_id)})
    values = dict(kind=kind, idempotency_key=key, request_hash=request_hash,
                  transaction_id=transaction_id, status='PENDING', payload=payload,
                  result_data={}, attempt_count=0, next_attempt_at=datetime.now(UTC),
                  requested_by=requested_by)
    # PostgreSQL atomic insert, prevents concurrent duplicate callbacks.
    res = await session.execute(
        insert(AutomationJob).values(**values).on_conflict_do_nothing(
            index_elements=['idempotency_key']).returning(AutomationJob.id)
    )
    created_id = res.scalar_one_or_none()
    job = await session.scalar(select(AutomationJob).where(AutomationJob.idempotency_key == key))
    if job is None:
        # INSERT returning may not yet be visible to a snapshot in a concurrent transaction;
        # force caller to retry instead of claiming duplicate incorrectly.
        raise RuntimeError('Concurrent job insertion not yet visible; retry request.')
    if job.request_hash != request_hash:
        raise IdempotencyConflict('Event key was reused with different payload. Do not overwrite existing job.')
    await session.commit()
    return job, created_id is not None


def public_job(job: AutomationJob) -> dict:
    # Do not expose raw payload (verified recipient addresses and provider references) in dashboards.
    return {
        'id': str(job.id), 'transaction_id': str(job.transaction_id) if job.transaction_id else None,
        'kind': job.kind, 'status': job.status, 'attempt_count': job.attempt_count,
        'last_error': job.last_error, 'external_id': job.external_id,
        'next_attempt_at': job.next_attempt_at.isoformat() if job.next_attempt_at else None,
        'created_at': job.created_at.isoformat() if job.created_at else None,
        'verified_at': job.verified_at.isoformat() if job.verified_at else None,
        'result': {k: v for k, v in (job.result_data or {}).items() if k in
                   {'transaction_public_id', 'artifact_id', 'remote_item_id', 'draft_id', 'message'}},
    }
