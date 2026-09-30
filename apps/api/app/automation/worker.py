"""Low-memory, PostgreSQL-leased automation worker.

Only consumes explicitly queued work. Non-idempotent ambiguous remote POSTs are
quarantined, not replayed. PostgreSQL is authoritative; n8n is a transport.
"""
import asyncio
import hashlib
import json
import logging
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.automation.contracts import JobKind
from app.automation.jobs import publish_job, canonical_hash
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.integrations.graph_auth import application_token
from app.integrations.microsoft_graph import MicrosoftGraph, GraphIntegrationError
from app.integrations.hubspot import HubSpot, ContactUpsert, HubSpotIntegrationError
from app.models.automation import AutomationJob
from app.models.digital_twin import Customer, IntegrationCommand, SourceArtifact, Approval
from app.models.transaction import Transaction, TransactionEvent
from app.services.ai_gateway import AIProviderError
from app.services.intake_service import (ArtifactBusy, DocumentNeedsReview, DuplicateDocument,
                                         ingest_order_file, ResolutionNeedsReview)
from app.services.object_storage import object_storage

logger = logging.getLogger('ordernexa.worker')


class BlockedConfiguration(RuntimeError):
    pass


class AmbiguousExternalEffect(RuntimeError):
    pass


class SafeTransient(RuntimeError):
    pass


class NeedsHumanReview(RuntimeError):
    def __init__(self, message: str, metadata: dict | None = None):
        super().__init__(message)
        self.metadata = metadata or {}


def retry_delay(attempts: int, jitter: float | None = None) -> timedelta:
    jitter = random.uniform(0, 2) if jitter is None else jitter
    return timedelta(seconds=min(3600, 15 * 2 ** min(attempts, 8)) + jitter)


def can_autoretry(kind: str, error: Exception) -> bool:
    if kind in {JobKind.OUTLOOK_DRAFT, JobKind.TEAMS_NOTIFY, JobKind.TEAMS_APPROVAL_NOTIFY, JobKind.HUBSPOT_CONTACT}:
        # An HTTP timeout after POST can mean the external side effect succeeded.
        return False
    return isinstance(error, SafeTransient)


async def claim(session: AsyncSession) -> AutomationJob | None:
    now = datetime.now(UTC)
    # RUNNING jobs with expired leases are deliberately *not* blindly reclaimed.
    # The operator must reconcile uncertainty before retrying a consequential side effect.
    job = await session.scalar(
        select(AutomationJob).where(
            AutomationJob.status.in_(['PENDING', 'RETRY']),
            AutomationJob.next_attempt_at <= now,
        ).order_by(AutomationJob.next_attempt_at, AutomationJob.created_at)
        .with_for_update(skip_locked=True).limit(1))
    if job:
        job.status = 'RUNNING'
        job.attempt_count += 1
        job.lease_until = now + timedelta(minutes=15)
        await session.commit()
    return job


async def expire_stalled_jobs(session: AsyncSession) -> int:
    now = datetime.now(UTC)
    # No automatic resumption even for internal steps: the state may have committed
    # before the process stopped, so an operator reconciles from the UI.
    result = await session.execute(update(AutomationJob).where(
        AutomationJob.status == 'RUNNING', AutomationJob.lease_until < now
    ).values(status='BLOCKED_UNCERTAIN', last_error='Worker lease expired. Inspect saved artifact / remote operation before retry.'))
    await session.commit()
    return result.rowcount or 0


async def _persist_source_job(session: AsyncSession, *, kind: str, key: str,
                              filename: str, raw: bytes, source_digest: str):
    if not raw or len(raw) > settings.max_upload_bytes:
        raise NeedsHumanReview('Incoming file exceeds safe demo document limit or is empty.')
    digest = hashlib.sha256(raw).hexdigest()
    if kind == JobKind.N8N_DOCUMENT:
        raise RuntimeError('Wrong job source.')
    ext = Path(filename).suffix.lower()
    if ext not in {'.txt', '.pdf', '.csv', '.xlsx', '.png', '.jpg', '.jpeg', '.webp'}:
        return
    import re
    safe = re.sub(r'[^A-Za-z0-9._-]', '_', filename.split('/')[-1])[:170] or 'incoming.txt'
    obj_key = f'automation/graph/{source_digest}/{digest}/{safe}'
    if not await object_storage.exists(obj_key):
        await object_storage.put_bytes(object_key=obj_key, data=raw)
    await publish_job(session, key=key, kind=JobKind.N8N_DOCUMENT,
                      payload={'object_key': obj_key, 'filename': safe,
                               'source_checksums': {'hash': digest, 'subject_hash': source_digest,
                                                    'sender_hash': source_digest}},
                      requested_by='GRAPH_MESSAGE')


async def graph_message(job: AutomationJob) -> dict:
    payload = job.payload
    if not (settings.graph_mailbox and settings.graph_client_id and settings.graph_client_secret):
        raise BlockedConfiguration('Graph app-only Mail.Read, tenant and mailbox configuration is missing.')
    if payload['mailbox'].casefold() != settings.graph_mailbox.casefold():
        raise NeedsHumanReview('Mailbox mismatch; rejected Graph notification.')
    graph = MicrosoftGraph(token_provider=application_token)
    mail = await graph.get_message_with_attachments(settings.graph_mailbox, payload['message_id'])
    source_digest = hashlib.sha256((payload['subscription_id'] + '\x00' + payload['message_id']).encode()).hexdigest()
    files = [(name, raw) for name, raw, _ in mail.attachments
             if Path(name).suffix.lower() in {'.txt', '.pdf', '.csv', '.xlsx', '.png', '.jpg', '.jpeg', '.webp'}]
    if not files and mail.body_text.strip():
        files = [('message-body.txt', mail.body_text.encode('utf-8'))]
    if not files:
        raise NeedsHumanReview('Graph message contained no supported purchase-order attachments or readable text.')
    async with AsyncSessionLocal() as session:
        for i, (filename, raw) in enumerate(files[:8]):
            await _persist_source_job(session, kind=JobKind.GRAPH_MESSAGE,
                 key=f'graph-file:{source_digest}:{i}', filename=filename,
                 raw=raw, source_digest=source_digest)
    if len(files) > 8:
        raise NeedsHumanReview('Only the first eight attachments were queued; manually inspect the email.')
    return {'message': f'Queued {len(files)} saved source document(s) for extraction/review.'}


async def process_document(job: AutomationJob) -> tuple[str, dict]:
    payload = job.payload
    raw = await object_storage.get_bytes(payload['object_key'])
    digest = hashlib.sha256(raw).hexdigest()
    if digest != payload['source_checksums']['hash']:
        raise NeedsHumanReview('Source checksum mismatch; saved artifact must be investigated.')
    async with AsyncSessionLocal() as session:
        try:
            result = await ingest_order_file(session, filename=payload['filename'],
                                             content_type='application/octet-stream', data=raw)
            return 'VERIFIED', {'transaction_public_id': result.transaction.public_id,
                                'artifact_id': str(result.artifact_id),
                                'message': 'Structured extraction and business validation completed.'}
        except DocumentNeedsReview as exc:
            return 'REVIEW_REQUIRED', {
                'artifact_id': exc.details.get('artifact_id'),
                'message': 'Saved original requires a human review; no ERP write occurred.'}
        except DuplicateDocument as exc:
            return 'VERIFIED', {'transaction_public_id': exc.existing_public_id,
                                'message': 'Existing transaction reused; no duplicate created.'}
        except ArtifactBusy as exc:
            raise SafeTransient('Another worker still holds this saved artifact; retry later.') from exc
        except AIProviderError as exc:
            if exc.retryable:
                # The source remains in MinIO and existing artifact status is AI_UNAVAILABLE.
                raise SafeTransient('Local Ollama temporarily unavailable; original source retained.') from exc
            return 'REVIEW_REQUIRED', {'artifact_id': str(getattr(exc, 'artifact_id', '')),
                                       'message': 'AI output invalid; source saved for authorized human review.'}
        except ResolutionNeedsReview as exc:
            return 'REVIEW_REQUIRED', {'transaction_public_id': exc.public_id,
                                       'message': 'Deterministic business resolution requires human review.'}


async def _assert_external_verified(session: AsyncSession, job: AutomationJob) -> tuple[Transaction, str, dict]:
    tx = await session.get(Transaction, job.transaction_id)
    if not tx or tx.status != 'COMPLETED':
        raise NeedsHumanReview('Local transaction is no longer verified and complete.')
    commands = (await session.execute(select(IntegrationCommand).where(
        IntegrationCommand.transaction_id == tx.id, IntegrationCommand.status == 'VERIFIED'))).scalars().all()
    erp = next((c for c in commands if c.provider == 'ODOO' and c.action == 'CREATE_SALE_ORDER' and c.external_id), None)
    archive = next((c for c in commands if c.provider == 'MINIO_LOCAL' and c.action == 'ARCHIVE_CONFIRMATION'), None)
    if not erp or not archive:
        raise NeedsHumanReview('Cannot export unverified ERP order or missing local archive.')
    key = (archive.response_payload or {}).get('object_key') or \
          (archive.request_payload or {}).get('object_key')
    if not key:
        raise NeedsHumanReview('Verified local archive key is missing.')
    raw = await object_storage.get_bytes(key)
    try:
        confirmation = json.loads(raw)
        if confirmation.get('transaction_id') != tx.public_id or str(confirmation.get('erp', {}).get('external_id')) != str(erp.external_id):
            raise ValueError('Archive transaction and ERP identity mismatch.')
    except (ValueError, TypeError) as exc:
        raise NeedsHumanReview('Saved confirmation failed authoritative readback validation.') from exc
    return tx, key, confirmation


async def teams_approval_notification(job: AutomationJob) -> tuple[str, dict, str | None]:
    import httpx
    from urllib.parse import urlparse
    if not settings.automation_live_writes:
        raise BlockedConfiguration('External notifications are disabled until explicitly authorized.')
    target = settings.teams_approval_webhook_url
    parsed = urlparse(target)
    if parsed.scheme != 'https' or not (parsed.hostname or '').endswith('.logic.azure.com'):
        raise BlockedConfiguration('Verified Teams Workflows HTTPS endpoint required.')
    async with AsyncSessionLocal() as session:
        tx = await session.get(Transaction, job.transaction_id)
        if not tx or tx.status != 'APPROVAL_REQUIRED':
            raise NeedsHumanReview('Transaction is no longer awaiting approval; do not send stale notification.')
        approvals = (await session.execute(select(Approval).where(
            Approval.transaction_id == tx.id, Approval.status == 'PENDING'))).scalars().all()
        if not approvals:
            raise NeedsHumanReview('No remaining approvals; a stale Teams notification would mislead the team.')
        roles = ', '.join(sorted({x.approver_role for x in approvals}))
        message = (f'OrderNexa {tx.public_id} / PO {tx.customer_reference}: '
                   f'{len(approvals)} pending human decision(s): {roles}. '
                   'Review evidence and approve ONLY in the protected OrderNexa Operations Console. '
                   'This Teams notification cannot execute or approve an order.')
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(target, json={'text': message})
            response.raise_for_status()
        return 'ACKNOWLEDGED', {'message': 'Teams Workflow acknowledged approval notification; channel display unverified.'}, None
    except Exception as exc:
        raise AmbiguousExternalEffect('Teams notification delivery uncertain; inspect the channel before any resend.') from exc


async def external_action(job: AutomationJob) -> tuple[str, dict, str | None]:
    if not settings.automation_live_writes:
        raise BlockedConfiguration('External writes are disabled. Explicitly enable AUTOMATION_LIVE_WRITES after permission review.')
    async with AsyncSessionLocal() as session:
        tx, key, confirmation = await _assert_external_verified(session, job)
        # Never allow AI to choose destinations or executable prices.
        kind = job.kind
        email = job.payload.get('verified_contact_email') or ''
        if kind == JobKind.SHAREPOINT_ARCHIVE:
            if not settings.graph_drive_id:
                raise BlockedConfiguration('SharePoint drive ID / Sites.Selected site grant not configured.')
            graph = MicrosoftGraph(token_provider=application_token)
            path = f'OrderNexa/{tx.public_id}/confirmation.json'
            raw = await object_storage.get_bytes(key)
            try:
                previous = await graph.inspect_archive(drive_id=settings.graph_drive_id, path=path)
                if previous:
                    # Compare actual content. Never silently overwrite an existing unrelated file.
                    remote = await graph.archive_content(drive_id=settings.graph_drive_id, path=path)
                    if hashlib.sha256(raw).digest() != hashlib.sha256(remote).digest():
                        raise NeedsHumanReview('Existing SharePoint file differs from local verified confirmation.')
                    return 'VERIFIED', {'remote_item_id': previous['id'], 'message': 'Pre-existing archive content verified.'}, previous['id']
                created = await graph.archive_file(drive_id=settings.graph_drive_id, path=path, data=raw)
                remote = await graph.archive_content(drive_id=settings.graph_drive_id, path=path)
                if hashlib.sha256(raw).digest() != hashlib.sha256(remote).digest():
                    raise NeedsHumanReview('SharePoint content differs after upload; requires investigation.')
                return 'VERIFIED', {'remote_item_id': created['id'], 'message': 'SharePoint content read back and verified.'}, created['id']
            except NeedsHumanReview:
                raise
            except Exception as exc:
                # Deterministic path supports safe future reconciliation, not uncontrolled POST replay.
                raise SafeTransient('SharePoint operation failed; remote path must be verified before retry.') from exc

        if kind == JobKind.HUBSPOT_CONTACT:
            if not settings.hubspot_access_token:
                raise BlockedConfiguration('HubSpot access token is missing.')
            if '@' not in email:
                raise BlockedConfiguration('A human-verified email is required for HubSpot upsert.')
            customer = await session.get(Customer, tx.customer_id)
            if not customer:
                raise NeedsHumanReview('Authoritative customer record missing.')
            hubspot = HubSpot(access_token=settings.hubspot_access_token)
            try:
                result = await hubspot.upsert_contact(ContactUpsert(email=email, company=customer.name))
                ids = [item.get('id') for item in result.get('results', [])]
                if len(ids) != 1 or not ids[0]:
                    raise AmbiguousExternalEffect('HubSpot response lacks a single stable contact ID.')
                remote = await hubspot.get_contact(str(ids[0]))
                if (remote.get('properties') or {}).get('email', '').casefold() != email.casefold():
                    raise AmbiguousExternalEffect('HubSpot contact failed email read-after-write verification.')
                return 'VERIFIED', {'message': 'HubSpot contact read back and verified.'}, str(ids[0])
            except (HubSpotIntegrationError, Exception) as exc:
                raise AmbiguousExternalEffect('HubSpot call may have committed. Reconcile the contact by email before retry.') from exc

        if kind == JobKind.OUTLOOK_DRAFT:
            if not settings.graph_mailbox or not settings.customer_email_enabled:
                raise BlockedConfiguration('Outlook draft is disabled or mailbox missing; customer email sending is NEVER automatic.')
            if '@' not in email:
                raise BlockedConfiguration('A human-verified recipient email is mandatory.')
            graph = MicrosoftGraph(token_provider=application_token)
            subject = f'Order confirmation draft: {tx.customer_reference} [{tx.public_id}]'
            text = (f'Hello,\n\nPlease review the order summary for {tx.customer_reference}.\n'
                    f'Validated amount: {tx.currency} {tx.value}\n'
                    f'Internal reference: {tx.public_id}\n\n'
                    'This is an UNRELEASED DRAFT. A human must check delivery, approval and recipient before sending.\n')
            if job.external_id:
                draft = await graph.get_draft(sender_id=settings.graph_mailbox, draft_id=job.external_id)
                if draft.get('id') == job.external_id and draft.get('isDraft'):
                    return 'VERIFIED', {'draft_id': draft['id'], 'message': 'Existing draft verified; customer email not sent.'}, draft['id']
            try:
                created = await graph.create_confirmation_draft(sender_id=settings.graph_mailbox,
                    recipient=email, subject=subject, plain_text=text)
                draft_id = created.get('id')
                if not draft_id:
                    raise AmbiguousExternalEffect('Draft response lacks ID; reconcile Outlook Drafts.')
                draft = await graph.get_draft(sender_id=settings.graph_mailbox, draft_id=draft_id)
                if not draft.get('isDraft') or draft.get('subject') != subject:
                    raise AmbiguousExternalEffect('Outlook draft verification failed; inspect Outlook.')
                return 'VERIFIED', {'draft_id': draft_id, 'message': 'Outlook draft verified. A human must send it manually.'}, draft_id
            except Exception as exc:
                raise AmbiguousExternalEffect('Outlook draft creation outcome uncertain. Inspect Outlook Drafts before retry.') from exc

        if kind == JobKind.TEAMS_NOTIFY:
            import httpx
            from urllib.parse import urlparse
            url = settings.teams_approval_webhook_url
            parsed = urlparse(url)
            if parsed.scheme != 'https' or not (parsed.hostname or '').endswith('.logic.azure.com'):
                raise BlockedConfiguration('Configure a verified HTTPS Teams Workflows webhook (logic.azure.com).')
            # Notification-only. Teams cannot approve anything in this route; use web approval center.
            message = (f'OrderNexa order {tx.customer_reference} / {tx.public_id}: '
                       f'local verified status {tx.status}. Use the protected OrderNexa console for approvals.')
            try:
                async with httpx.AsyncClient(timeout=25) as client:
                    res = await client.post(url, json={'text': message})
                    res.raise_for_status()
                # 2xx indicates webhook ACK, not verified delivery to a Teams channel.
                return 'ACKNOWLEDGED', {'message': 'Teams workflow accepted notification; Teams display was not read back.'}, None
            except Exception as exc:
                raise AmbiguousExternalEffect('Teams webhook response uncertain. Inspect the channel before retry.') from exc
    raise NeedsHumanReview('Unsupported job kind.')


async def process(job: AutomationJob) -> tuple[str, dict, str | None]:
    if job.kind == JobKind.GRAPH_LIFECYCLE:
        raise NeedsHumanReview('Graph subscription lifecycle action required: inspect subscription and reconcile missed notifications.', {'message': job.payload.get('event', 'unknown')})
    if job.kind == JobKind.TEAMS_APPROVAL_NOTIFY:
        return await teams_approval_notification(job)
    if job.kind == JobKind.GRAPH_MESSAGE:
        return 'VERIFIED', await graph_message(job), None
    if job.kind == JobKind.N8N_DOCUMENT:
        status, result = await process_document(job)
        return status, result, None
    return await external_action(job)


async def process_once() -> bool:
    async with AsyncSessionLocal() as session:
        await expire_stalled_jobs(session)
        job = await claim(session)
    if not job:
        return False
    try:
        status, result, external_id = await process(job)
        err = None
    except BlockedConfiguration as exc:
        status, result, external_id, err = 'BLOCKED_CONFIG', {}, None, str(exc)
    except NeedsHumanReview as exc:
        status, result, external_id, err = 'REVIEW_REQUIRED', exc.metadata, None, str(exc)
    except AmbiguousExternalEffect as exc:
        status, result, external_id, err = 'BLOCKED_UNCERTAIN', {}, None, str(exc)
    except Exception as exc:
        logger.warning('Automation job %s failed: %s', job.id, type(exc).__name__)
        if can_autoretry(job.kind, exc) and job.attempt_count < settings.automation_max_attempts:
            status, err = 'RETRY', 'Temporary dependency failure; original payload retained.'
        else:
            status, err = ('BLOCKED_UNCERTAIN' if job.kind not in
                {JobKind.N8N_DOCUMENT, JobKind.GRAPH_MESSAGE, JobKind.GRAPH_LIFECYCLE} else 'FAILED_MANUAL'), \
                ('Remote effect may be uncertain; reconcile before retry.' if job.kind not in
                 {JobKind.N8N_DOCUMENT, JobKind.GRAPH_MESSAGE, JobKind.GRAPH_LIFECYCLE} else 'Repeated internal failure; inspect source artifact.')
        result, external_id = {}, None
    async with AsyncSessionLocal() as session:
        current = await session.scalar(select(AutomationJob).where(AutomationJob.id == job.id).with_for_update())
        if not current or current.status != 'RUNNING':
            # Never overwrite an operator decision made during an in-flight external request.
            logger.error('Job %s lost RUNNING state; manual reconciliation required.', job.id)
            return True
        current.status = status
        current.result_data = result
        current.last_error = err
        current.lease_until = None
        if external_id:
            current.external_id = str(external_id)
        if status == 'RETRY':
            current.next_attempt_at = datetime.now(UTC) + retry_delay(current.attempt_count)
        if status == 'VERIFIED':
            current.verified_at = datetime.now(UTC)
        if current.transaction_id:
            tx = await session.get(Transaction, current.transaction_id)
            if tx:
                event_metadata = {'job_id': str(current.id), 'kind': current.kind,
                                  'status': status, 'external_id': current.external_id}
                session.add(TransactionEvent(
                    transaction_id=tx.id, step='AUTOMATION', actor_type='WORKER',
                    actor_id='ORDERNEXA_AUTOMATION', event_type='AUTOMATION_' + status,
                    payload=event_metadata, payload_hash=canonical_hash(event_metadata),
                    trace_id=tx.correlation_id))
        await session.commit()
    logger.info('Job %s (%s) -> %s', job.id, job.kind, status)
    return True


async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if not settings.automation_worker_enabled:
        logger.error('AUTOMATION_WORKER_ENABLED is false. Worker will not run until explicitly enabled.')
        return
    logger.info('Worker started; external writes: %s', settings.automation_live_writes)
    while True:
        try:
            processed = await process_once()
            if not processed:
                await asyncio.sleep(5)
        except Exception:
            logger.exception('Worker polling error; retrying after delay.')
            await asyncio.sleep(15)


if __name__ == '__main__':
    asyncio.run(main())
