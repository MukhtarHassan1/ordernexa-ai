"""Proof-based recovery for expired leases and uncertain remote effects.

This module never trusts a browser's 'success' assertion for an external write.
Where no read-after-write is supported, status remains manually acknowledged,
NOT verified or safe for automatic retry.
"""
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.automation.contracts import JobKind, ReconcileRequest
from app.automation.jobs import canonical_hash
from app.core.config import settings
from app.integrations.graph_auth import application_token
from app.integrations.microsoft_graph import MicrosoftGraph
from app.integrations.hubspot import HubSpot
from app.models.automation import AutomationJob
from app.models.digital_twin import SourceArtifact
from app.models.transaction import Transaction, TransactionEvent
from app.services.object_storage import object_storage


class ReconciliationRejected(ValueError):
    pass


async def reconcile(session: AsyncSession, *, job: AutomationJob,
                    request: ReconcileRequest, actor_id: str) -> str:
    if job.status != 'BLOCKED_UNCERTAIN':
        raise ReconciliationRejected('Only BLOCKED_UNCERTAIN jobs require this proof-based recovery operation.')
    kind = job.kind
    status: str
    external_id = job.external_id
    result: dict = {}
    if kind == JobKind.N8N_DOCUMENT:
        raw = await object_storage.get_bytes(job.payload['object_key'])
        digest = hashlib.sha256(raw).hexdigest()
        if digest != job.payload['source_checksums']['hash']:
            raise ReconciliationRejected('Saved original checksum mismatch; no retry permitted.')
        existing = await session.scalar(select(SourceArtifact).where(
            SourceArtifact.sha256 == digest, SourceArtifact.artifact_type == 'ORIGINAL_DOCUMENT')
            .order_by(SourceArtifact.created_at.desc()).limit(1))
        if existing and existing.transaction_id:
            transaction = await session.get(Transaction, existing.transaction_id)
            if not transaction:
                raise ReconciliationRejected('Original is linked to a missing transaction.')
            status = 'VERIFIED'
            result = {'transaction_public_id': transaction.public_id,
                      'artifact_id': str(existing.id),
                      'message': 'Matched previously committed source artifact and transaction.'}
        elif existing and existing.extra_data.get('status') in {
            'NEEDS_REVIEW', 'AI_NEEDS_REVIEW', 'AI_UNAVAILABLE', 'FAILED_MANUAL', 'DUPLICATE_REVIEW'
        }:
            status = 'REVIEW_REQUIRED'
            result = {'artifact_id': str(existing.id),
                      'message': 'Found previously saved original. Human review required; no new AI attempt authorized.'}
        elif existing and existing.extra_data.get('status') == 'PROCESSING':
            from datetime import timedelta
            stamp = existing.extra_data.get('last_attempt_at')
            try:
                still_recent = datetime.now(UTC) - datetime.fromisoformat(stamp) < timedelta(minutes=10)
            except (TypeError, ValueError):
                still_recent = False
            if still_recent:
                raise ReconciliationRejected('Source is still processing; wait for lease and original-artifact timeout.')
            status = 'PENDING'
        else:
            status = 'PENDING'
    elif kind == JobKind.GRAPH_MESSAGE:
        # Read-only callback processing and child jobs have unique delivery keys.
        # Re-running the parent cannot create two child jobs with the same key.
        status = 'PENDING'
    elif kind == JobKind.SHAREPOINT_ARCHIVE:
        if not settings.graph_drive_id:
            raise ReconciliationRejected('SharePoint drive must be configured for remote verification.')
        if not job.transaction_id:
            raise ReconciliationRejected('SharePoint job is missing its transaction.')
        tx = await session.get(Transaction, job.transaction_id)
        if not tx:
            raise ReconciliationRejected('Transaction missing.')
        local_key = f'transactions/{tx.public_id}/confirmation.json'
        raw = await object_storage.get_bytes(local_key)
        remote = MicrosoftGraph(token_provider=application_token)
        remote_path = f'OrderNexa/{tx.public_id}/confirmation.json'
        existing = await remote.inspect_archive(drive_id=settings.graph_drive_id, path=remote_path)
        if existing:
            remote_bytes = await remote.archive_content(drive_id=settings.graph_drive_id, path=remote_path)
            if hashlib.sha256(raw).digest() != hashlib.sha256(remote_bytes).digest():
                raise ReconciliationRejected('SharePoint remote archive differs from local verified source.')
            external_id = existing['id']
            status = 'VERIFIED'
            result = {'remote_item_id': external_id, 'message': 'Existing SharePoint content verified byte-for-byte.'}
        else:
            # PUT to deterministic immutable source path, safe after absence check.
            status = 'PENDING'
    elif kind == JobKind.HUBSPOT_CONTACT:
        if not settings.hubspot_access_token or not request.remote_id:
            raise ReconciliationRejected('Supply an existing HubSpot numeric contact ID for authenticated readback.')
        remote = await HubSpot(access_token=settings.hubspot_access_token).get_contact(request.remote_id)
        expected_email = job.payload.get('verified_contact_email', '').casefold()
        if not expected_email or (remote.get('properties') or {}).get('email', '').casefold() != expected_email:
            raise ReconciliationRejected('Remote HubSpot email mismatch. Job cannot be marked verified.')
        external_id = request.remote_id
        status = 'VERIFIED'
        result = {'message': 'Existing HubSpot contact read back by ID and verified.'}
    elif kind == JobKind.OUTLOOK_DRAFT:
        if not request.remote_id or not settings.graph_mailbox:
            raise ReconciliationRejected('Supply an existing Outlook draft ID from the configured mailbox.')
        graph = MicrosoftGraph(token_provider=application_token)
        existing = await graph.get_draft(sender_id=settings.graph_mailbox, draft_id=request.remote_id)
        tx = await session.get(Transaction, job.transaction_id)
        expected = f'Order confirmation draft: {tx.customer_reference} [{tx.public_id}]' if tx else ''
        if not expected or existing.get('subject') != expected or not existing.get('isDraft'):
            raise ReconciliationRejected('Outlook draft does not match the intended unsent confirmation.')
        external_id = request.remote_id
        status = 'VERIFIED'
        result = {'draft_id': external_id, 'message': 'Existing unsent Outlook draft verified. Human sending remains required.'}
    elif kind in {JobKind.TEAMS_NOTIFY, JobKind.TEAMS_APPROVAL_NOTIFY}:
        # No reliable read-after-write API for Workflows webhook delivery.
        # Do not misrepresent operator testimony as a verified remote side effect.
        status = 'MANUALLY_ACKNOWLEDGED'
        result = {'message': 'Operator recorded investigation; Teams delivery is not independently verified.'}
    elif kind == JobKind.GRAPH_LIFECYCLE:
        raise ReconciliationRejected('Graph lifecycle requires subscription renewal and a delta resync. See integration runbook.')
    else:
        raise ReconciliationRejected('Unsupported recovery operation.')
    job.status = status
    job.external_id = external_id
    job.result_data = result
    job.last_error = None if status != 'PENDING' else 'Operator verified safe retry prerequisites; queued for worker.'
    job.lease_until = None
    if status == 'PENDING':
        job.next_attempt_at = datetime.now(UTC)
    if status == 'VERIFIED':
        job.verified_at = datetime.now(UTC)
    if job.transaction_id:
        tx = await session.get(Transaction, job.transaction_id)
        if tx:
            event = {'job_id': str(job.id), 'outcome': status, 'operator': actor_id,
                     'note_hash': hashlib.sha256(request.operator_note.encode()).hexdigest()}
            session.add(TransactionEvent(transaction_id=tx.id, step='AUTOMATION_RECOVERY',
                actor_type='HUMAN', actor_id=actor_id, event_type='AUTOMATION_RECONCILED',
                payload=event, payload_hash=canonical_hash(event), trace_id=tx.correlation_id))
    await session.commit()
    return status
