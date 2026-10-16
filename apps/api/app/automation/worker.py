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
from uuid import uuid4
from sqlalchemy import and_, or_, select, update, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.automation.contracts import JobKind
from app.automation.jobs import publish_job, canonical_hash
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.integrations.graph_auth import application_token
from app.integrations.microsoft_graph import MicrosoftGraph, GraphIntegrationError
from app.integrations.hubspot import HubSpot, ContactUpsert, CompanyUpsert, HubSpotIntegrationError
from app.models.automation import AutomationJob
from app.models.digital_twin import Customer, CustomerExternalRef, IntegrationCommand, SourceArtifact, Approval
from app.models.transaction import Transaction, TransactionEvent
from app.services.ai_gateway import AIProviderError
from app.services.intake_service import (ArtifactBusy, DocumentNeedsReview, DuplicateDocument,
                                         ingest_order_file, ResolutionNeedsReview)
from app.services.object_storage import object_storage
from app.services.integration_command_service import begin_external_command, mark_external_command
from app.services.reliability import (
    CircuitOpen, FailureCategory, assert_circuit_allows,
    record_integration_failure, record_integration_success,
)
from app.automation.graph_subscription import (
    delta_sync, ensure_subscription, GraphSubscriptionConfigurationError,
)

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


def verified_teams_workflow_url(value: str) -> bool:
    """Allow only credential-free HTTPS Microsoft Teams Workflows endpoints."""
    from urllib.parse import urlparse
    parsed = urlparse(value or "")
    host = (parsed.hostname or "").lower()
    return bool(
        parsed.scheme == "https"
        and host.endswith(".logic.azure.com")
        and not parsed.username
        and not parsed.password
        and not parsed.fragment
    )


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
        job.lease_token = uuid4().hex
        job.heartbeat_at = now
        job.lease_until = now + timedelta(seconds=settings.automation_lease_seconds)
        job.error_category = None
        await session.commit()
    return job


async def expire_stalled_jobs(session: AsyncSession) -> int:
    now = datetime.now(UTC)
    # No automatic resumption even for internal steps: the state may have committed
    # before the process stopped, so an operator reconciles from the UI.
    result = await session.execute(update(AutomationJob).where(
        AutomationJob.status == 'RUNNING', AutomationJob.lease_until < now
    ).values(
        status='BLOCKED_UNCERTAIN',
        last_error='Worker lease expired. Inspect saved artifact / remote operation before retry.',
        error_category=FailureCategory.UNCERTAIN_REMOTE_STATE.value,
        lease_token=None, lease_until=None,
    ))
    await session.commit()
    return result.rowcount or 0


async def heartbeat(job_id, lease_token: str, stop: asyncio.Event) -> None:
    """Extend only the lease owned by this worker token (fencing)."""
    interval = max(5, min(settings.automation_heartbeat_seconds, settings.automation_lease_seconds // 3))
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            pass
        try:
            async with AsyncSessionLocal() as session:
                now = datetime.now(UTC)
                result = await session.execute(
                    update(AutomationJob).where(
                        AutomationJob.id == job_id,
                        AutomationJob.status == 'RUNNING',
                        AutomationJob.lease_token == lease_token,
                    ).values(
                        heartbeat_at=now,
                        lease_until=now + timedelta(seconds=settings.automation_lease_seconds),
                    )
                )
                await session.commit()
                if not (result.rowcount or 0):
                    logger.error('Job %s lost its lease fencing token; stopping heartbeat.', job_id)
                    return
        except Exception:
            logger.exception('Heartbeat failed for job %s; lease expiry will fail closed.', job_id)


async def wait_for_database() -> None:
    """Worker startup resilience for Docker/WSL PostgreSQL recovery windows."""
    delay = 1.0
    while True:
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text('SELECT 1'))
            logger.info('Worker database preflight: READY')
            return
        except Exception as exc:
            logger.warning('Database not ready for worker (%s); retrying in %.1fs', type(exc).__name__, delay)
            await asyncio.sleep(delay)
            delay = min(float(settings.automation_db_retry_max_seconds), delay * 1.8)


async def _persist_source_job(session: AsyncSession, *, kind: str, key: str,
                              filename: str, raw: bytes, source_digest: str,
                              correlation_id: str | None = None):
    if not raw or len(raw) > settings.max_upload_bytes:
        raise NeedsHumanReview('Incoming file exceeds the configured safe document limit or is empty.')
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
                      requested_by='GRAPH_MESSAGE', correlation_id=correlation_id)


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
                 raw=raw, source_digest=source_digest, correlation_id=job.correlation_id)
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
    if not settings.automation_live_writes:
        raise BlockedConfiguration('External notifications are disabled until explicitly authorized.')
    target = settings.teams_approval_webhook_url
    if not verified_teams_workflow_url(target):
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
        from app.services.ops_service import transaction_decision_summary
        summary = await transaction_decision_summary(session, tx.public_id) or {}
        pricing = summary.get('pricing') or {}
        credit = summary.get('credit') or {}
        price_delta = pricing.get('total_difference')
        over_limit = credit.get('over_limit_by')
        evidence_url = settings.backend_url.rstrip('/') + '/console/'
        message = (
            f'OrderNexa approval required\n'
            f'Transaction: {tx.public_id}\nPO: {tx.customer_reference}\n'
            f'Value: {tx.currency} {tx.value}\n'
            f'Pending roles: {roles}\n'
            f'Pricing difference: {tx.currency} {price_delta if price_delta is not None else "not recorded"}\n'
            f'Credit over limit: {tx.currency} {over_limit if over_limit is not None else "not recorded"}\n'
            f'Evidence / decision inspector: {evidence_url}\n'
            'Approve ONLY in the protected OrderNexa Operations Console. '
            'This Teams notification cannot execute or approve an order.'
        )
        await assert_circuit_allows(session, 'TEAMS')
        command, already_verified = await begin_external_command(
            session, transaction=tx, provider='TEAMS', action='NOTIFY_APPROVAL_REQUIRED',
            idempotency_key=f'automation:{job.idempotency_key}',
            request_summary={'job_id': str(job.id), 'pending_roles': sorted({x.approver_role for x in approvals}),
                             'pricing_difference': price_delta, 'credit_over_limit': over_limit},
        )
        if already_verified:
            return ('ACKNOWLEDGED' if command.status == 'ACKNOWLEDGED' else 'VERIFIED'), {**(command.response_payload or {}), 'message': 'Existing Teams command result reused.'}, command.external_id
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                response = await client.post(target, json={'text': message})
                response.raise_for_status()
            await record_integration_success(session, 'TEAMS')
            await mark_external_command(session, command=command, status='ACKNOWLEDGED',
                                        response_summary={'acknowledged': True, 'verified_delivery': False})
            return 'ACKNOWLEDGED', {'message': 'Teams Workflow acknowledged approval notification; channel display unverified.'}, None
        except Exception as exc:
            await record_integration_failure(session, 'TEAMS', FailureCategory.UNCERTAIN_REMOTE_STATE)
            await mark_external_command(session, command=command, status='BLOCKED_UNCERTAIN',
                                        error_category=FailureCategory.UNCERTAIN_REMOTE_STATE.value,
                                        last_error=type(exc).__name__)
            raise AmbiguousExternalEffect('Teams notification delivery uncertain; inspect the channel before any resend.') from exc


async def external_action(job: AutomationJob) -> tuple[str, dict, str | None]:
    if not settings.automation_live_writes:
        raise BlockedConfiguration('External writes are disabled. Explicitly enable AUTOMATION_LIVE_WRITES after permission review.')
    async with AsyncSessionLocal() as session:
        tx, key, confirmation = await _assert_external_verified(session, job)
        # Never allow AI to choose destinations or executable prices.
        kind = job.kind
        email = job.payload.get('verified_contact_email') or ''
        provider = {
            JobKind.SHAREPOINT_ARCHIVE: 'MICROSOFT_GRAPH',
            JobKind.HUBSPOT_CONTACT: 'HUBSPOT',
            JobKind.OUTLOOK_DRAFT: 'MICROSOFT_GRAPH',
            JobKind.TEAMS_NOTIFY: 'TEAMS',
        }.get(kind)
        if provider:
            await assert_circuit_allows(session, provider)
        action = {
            JobKind.SHAREPOINT_ARCHIVE: 'ARCHIVE_SHAREPOINT',
            JobKind.HUBSPOT_CONTACT: 'SYNC_CUSTOMER',
            JobKind.OUTLOOK_DRAFT: 'CREATE_OUTLOOK_DRAFT',
            JobKind.TEAMS_NOTIFY: 'NOTIFY_TRANSACTION',
        }.get(kind)
        command = None
        if provider and action:
            request_summary = {
                'job_id': str(job.id), 'kind': str(kind), 'transaction_public_id': tx.public_id,
                'verified_contact_email_hash': (hashlib.sha256(email.casefold().encode()).hexdigest() if email else None),
            }
            command, already_verified = await begin_external_command(
                session, transaction=tx, provider=provider, action=action,
                idempotency_key=f'automation:{job.idempotency_key}', request_summary=request_summary,
            )
            if already_verified:
                return ('ACKNOWLEDGED' if command.status == 'ACKNOWLEDGED' else 'VERIFIED'), {**(command.response_payload or {}), 'message': 'Existing terminal integration command reused.'}, command.external_id

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
                    await record_integration_success(session, 'MICROSOFT_GRAPH')
                    await mark_external_command(session, command=command, status='VERIFIED', external_id=previous['id'],
                                                response_summary={'remote_item_id': previous['id'], 'verified': True})
                    return 'VERIFIED', {'remote_item_id': previous['id'], 'message': 'Pre-existing archive content verified.'}, previous['id']
                created = await graph.archive_file(drive_id=settings.graph_drive_id, path=path, data=raw)
                remote = await graph.archive_content(drive_id=settings.graph_drive_id, path=path)
                if hashlib.sha256(raw).digest() != hashlib.sha256(remote).digest():
                    raise NeedsHumanReview('SharePoint content differs after upload; requires investigation.')
                await record_integration_success(session, 'MICROSOFT_GRAPH')
                await mark_external_command(session, command=command, status='VERIFIED', external_id=created['id'],
                                            response_summary={'remote_item_id': created['id'], 'verified': True})
                return 'VERIFIED', {'remote_item_id': created['id'], 'message': 'SharePoint content read back and verified.'}, created['id']
            except NeedsHumanReview:
                raise
            except Exception as exc:
                # Deterministic path supports safe future reconciliation, not uncontrolled POST replay.
                await record_integration_failure(session, 'MICROSOFT_GRAPH', FailureCategory.TRANSIENT)
                await mark_external_command(session, command=command, status='FAILED_RETRYABLE',
                                            error_category=FailureCategory.TRANSIENT.value, last_error=type(exc).__name__)
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
                company_id = None
                if customer.primary_domain:
                    company_result = await hubspot.upsert_company(
                        CompanyUpsert(domain=customer.primary_domain, name=customer.name)
                    )
                    company_ids = [item.get('id') for item in company_result.get('results', [])]
                    if len(company_ids) != 1 or not company_ids[0]:
                        raise AmbiguousExternalEffect('HubSpot company response lacks a single stable ID.')
                    company_id = str(company_ids[0])
                    remote_company = await hubspot.get_company(company_id)
                    props = remote_company.get('properties') or {}
                    if props.get('domain', '').casefold() != customer.primary_domain.casefold():
                        raise AmbiguousExternalEffect('HubSpot company failed domain read-after-write verification.')

                result = await hubspot.upsert_contact(ContactUpsert(email=email, company=customer.name))
                ids = [item.get('id') for item in result.get('results', [])]
                if len(ids) != 1 or not ids[0]:
                    raise AmbiguousExternalEffect('HubSpot response lacks a single stable contact ID.')
                contact_id = str(ids[0])
                remote = await hubspot.get_contact(contact_id)
                if (remote.get('properties') or {}).get('email', '').casefold() != email.casefold():
                    raise AmbiguousExternalEffect('HubSpot contact failed email read-after-write verification.')

                # Persist canonical remote identities so later syncs do not rely on
                # searching human-readable names. These records contain IDs only.
                refs = []
                if company_id:
                    refs.append(('HUBSPOT_COMPANY', company_id, {'domain': customer.primary_domain}))
                refs.append(('HUBSPOT_CONTACT', contact_id, {'verified_email_hash': hashlib.sha256(email.casefold().encode()).hexdigest()}))
                for system, external_id_value, metadata in refs:
                    existing_ref = await session.scalar(select(CustomerExternalRef).where(
                        CustomerExternalRef.system == system,
                        CustomerExternalRef.external_id == external_id_value,
                    ))
                    if existing_ref and existing_ref.customer_id != customer.id:
                        raise NeedsHumanReview(f'{system} identity is already linked to another customer.')
                    if not existing_ref:
                        session.add(CustomerExternalRef(
                            customer_id=customer.id, system=system,
                            external_id=external_id_value, extra_data=metadata,
                        ))
                await record_integration_success(session, 'HUBSPOT')
                await mark_external_command(session, command=command, status='VERIFIED', external_id=contact_id,
                                            response_summary={'contact_id': contact_id, 'company_id': company_id, 'verified': True})
                return 'VERIFIED', {
                    'message': 'HubSpot customer/contact identities read back and verified.',
                    'company_id': company_id, 'contact_id': contact_id,
                    'transaction_context': {
                        'transaction_public_id': tx.public_id,
                        'po_number': tx.customer_reference,
                        'status': tx.status,
                    },
                }, contact_id
            except NeedsHumanReview:
                raise
            except Exception as exc:
                await record_integration_failure(session, 'HUBSPOT', FailureCategory.UNCERTAIN_REMOTE_STATE)
                await mark_external_command(session, command=command, status='BLOCKED_UNCERTAIN',
                                            error_category=FailureCategory.UNCERTAIN_REMOTE_STATE.value, last_error=type(exc).__name__)
                raise AmbiguousExternalEffect('HubSpot write may have committed. Reconcile company/contact identities before retry.') from exc

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
                    await record_integration_success(session, 'MICROSOFT_GRAPH')
                    await mark_external_command(session, command=command, status='VERIFIED', external_id=draft['id'],
                                                response_summary={'draft_id': draft['id'], 'is_draft': True})
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
                await record_integration_success(session, 'MICROSOFT_GRAPH')
                await mark_external_command(session, command=command, status='VERIFIED', external_id=draft_id,
                                            response_summary={'draft_id': draft_id, 'is_draft': True})
                return 'VERIFIED', {'draft_id': draft_id, 'message': 'Outlook draft verified. A human must send it manually.'}, draft_id
            except Exception as exc:
                await record_integration_failure(session, 'MICROSOFT_GRAPH', FailureCategory.UNCERTAIN_REMOTE_STATE)
                await mark_external_command(session, command=command, status='BLOCKED_UNCERTAIN',
                                            error_category=FailureCategory.UNCERTAIN_REMOTE_STATE.value, last_error=type(exc).__name__)
                raise AmbiguousExternalEffect('Outlook draft creation outcome uncertain. Inspect Outlook Drafts before retry.') from exc

        if kind == JobKind.TEAMS_NOTIFY:
            import httpx
            url = settings.teams_approval_webhook_url
            if not verified_teams_workflow_url(url):
                raise BlockedConfiguration('Configure a verified HTTPS Teams Workflows webhook (logic.azure.com).')
            # Notification-only. Teams cannot approve anything in this route; use web approval center.
            message = (f'OrderNexa order {tx.customer_reference} / {tx.public_id}: '
                       f'local verified status {tx.status}. Use the protected OrderNexa console for approvals.')
            try:
                async with httpx.AsyncClient(timeout=25) as client:
                    res = await client.post(url, json={'text': message})
                    res.raise_for_status()
                # 2xx indicates webhook ACK, not verified delivery to a Teams channel.
                await record_integration_success(session, 'TEAMS')
                await mark_external_command(session, command=command, status='ACKNOWLEDGED',
                                            response_summary={'acknowledged': True, 'verified_delivery': False})
                return 'ACKNOWLEDGED', {'message': 'Teams workflow accepted notification; Teams display was not read back.'}, None
            except Exception as exc:
                await record_integration_failure(session, 'TEAMS', FailureCategory.UNCERTAIN_REMOTE_STATE)
                await mark_external_command(session, command=command, status='BLOCKED_UNCERTAIN',
                                            error_category=FailureCategory.UNCERTAIN_REMOTE_STATE.value, last_error=type(exc).__name__)
                raise AmbiguousExternalEffect('Teams webhook response uncertain. Inspect the channel before retry.') from exc
    raise NeedsHumanReview('Unsupported job kind.')


async def graph_lifecycle_action(job: AutomationJob) -> tuple[str, dict, str | None]:
    event = str(job.payload.get('event') or '')
    try:
        async with AsyncSessionLocal() as session:
            if event == 'missed':
                result = await delta_sync(session, reason='LIFECYCLE_MISSED')
                return 'VERIFIED', {**result, 'message': 'Missed Graph notifications recovered through delta synchronization.'}, None
            if event in {'subscriptionRemoved', 'reauthorizationRequired'}:
                if not settings.automation_live_writes:
                    raise BlockedConfiguration(
                        'Graph subscription requires live renewal/recreation. Enable external writes only after permission and callback review.'
                    )
                ensured = await ensure_subscription(session, allow_create=True)
                # Reconcile missed messages after renewal/recreation as a separate read path.
                synced = await delta_sync(session, reason=event.upper())
                return 'VERIFIED', {
                    'subscription': ensured, 'delta': synced,
                    'message': 'Graph lifecycle event reconciled and mailbox delta synchronized.',
                }, None
    except GraphSubscriptionConfigurationError as exc:
        raise BlockedConfiguration(str(exc)) from exc
    raise NeedsHumanReview('Unsupported Graph lifecycle event.', {'event': event})


async def process(job: AutomationJob) -> tuple[str, dict, str | None]:
    if job.kind == JobKind.GRAPH_LIFECYCLE:
        return await graph_lifecycle_action(job)
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

    lease_token = job.lease_token
    if not lease_token:
        logger.error('Claimed job %s without a fencing token.', job.id)
        return True
    stop_heartbeat = asyncio.Event()
    heartbeat_task = asyncio.create_task(heartbeat(job.id, lease_token, stop_heartbeat))
    error_category = None
    try:
        status, result, external_id = await process(job)
        err = None
    except BlockedConfiguration as exc:
        status, result, external_id, err = 'BLOCKED_CONFIG', {}, None, str(exc)
        error_category = FailureCategory.CONFIGURATION.value
    except CircuitOpen as exc:
        status, result, external_id, err = 'RETRY', {}, None, str(exc)
        error_category = FailureCategory.TRANSIENT.value
    except NeedsHumanReview as exc:
        status, result, external_id, err = 'REVIEW_REQUIRED', exc.metadata, None, str(exc)
        error_category = FailureCategory.POLICY.value
    except AmbiguousExternalEffect as exc:
        status, result, external_id, err = 'BLOCKED_UNCERTAIN', {}, None, str(exc)
        error_category = FailureCategory.UNCERTAIN_REMOTE_STATE.value
    except Exception as exc:
        logger.warning('Automation job %s failed: %s', job.id, type(exc).__name__)
        if can_autoretry(job.kind, exc) and job.attempt_count < settings.automation_max_attempts:
            status, err = 'RETRY', 'Temporary dependency failure; original payload retained.'
            error_category = FailureCategory.TRANSIENT.value
        else:
            status, err = ('BLOCKED_UNCERTAIN' if job.kind not in
                {JobKind.N8N_DOCUMENT, JobKind.GRAPH_MESSAGE, JobKind.GRAPH_LIFECYCLE} else 'FAILED_MANUAL'), \
                ('Remote effect may be uncertain; reconcile before retry.' if job.kind not in
                 {JobKind.N8N_DOCUMENT, JobKind.GRAPH_MESSAGE, JobKind.GRAPH_LIFECYCLE} else 'Repeated internal failure; inspect source artifact.')
            error_category = (FailureCategory.UNCERTAIN_REMOTE_STATE.value
                              if status == 'BLOCKED_UNCERTAIN' else FailureCategory.UNKNOWN.value)
        result, external_id = {}, None
    finally:
        stop_heartbeat.set()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

    async with AsyncSessionLocal() as session:
        current = await session.scalar(select(AutomationJob).where(
            AutomationJob.id == job.id,
            AutomationJob.lease_token == lease_token,
        ).with_for_update())
        if not current or current.status != 'RUNNING':
            # Fencing token means a stale worker can never overwrite an operator
            # decision or a later worker's result.
            logger.error('Job %s lost RUNNING lease ownership; manual reconciliation required.', job.id)
            return True
        current.status = status
        current.result_data = result
        current.last_error = err
        current.error_category = error_category
        current.lease_until = None
        current.lease_token = None
        current.heartbeat_at = datetime.now(UTC)
        if external_id:
            current.external_id = str(external_id)
        if status == 'RETRY':
            current.next_attempt_at = datetime.now(UTC) + retry_delay(current.attempt_count)
        if status in {'VERIFIED', 'ACKNOWLEDGED'}:
            current.verified_at = datetime.now(UTC)
        if current.transaction_id:
            tx = await session.get(Transaction, current.transaction_id)
            if tx:
                event_metadata = {'job_id': str(current.id), 'kind': current.kind,
                                  'status': status, 'external_id': current.external_id,
                                  'error_category': error_category}
                session.add(TransactionEvent(
                    transaction_id=tx.id, step='AUTOMATION', actor_type='WORKER',
                    actor_id='ORDERNEXA_AUTOMATION', event_type='AUTOMATION_' + status,
                    payload=event_metadata, payload_hash=canonical_hash(event_metadata),
                    trace_id=tx.correlation_id))
        await session.commit()
    logger.info('Job %s (%s) -> %s', job.id, job.kind, status)
    return True


async def graph_subscription_maintenance() -> None:
    """Periodically inspect/renew the durable Graph subscription.

    This never creates a subscription while live writes are disabled. It makes
    expiry visible instead of relying on a human to remember the renewal date.
    """
    if not (settings.graph_tenant_id and settings.graph_client_id and settings.graph_client_secret
            and settings.graph_mailbox and settings.graph_client_state):
        return
    try:
        async with AsyncSessionLocal() as session:
            result = await ensure_subscription(session, allow_create=settings.automation_live_writes)
            logger.info('Graph subscription maintenance: %s', result.get('action'))
    except GraphSubscriptionConfigurationError as exc:
        logger.warning('Graph subscription maintenance blocked by configuration: %s', exc)
    except Exception as exc:
        logger.warning('Graph subscription maintenance failed safely: %s', type(exc).__name__)



async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    if not settings.automation_worker_enabled:
        logger.error('AUTOMATION_WORKER_ENABLED is false. Worker will not run until explicitly enabled.')
        return
    logger.info('Worker started; external writes: %s', settings.automation_live_writes)
    await wait_for_database()
    last_graph_maintenance = 0.0
    while True:
        try:
            now = asyncio.get_running_loop().time()
            if now - last_graph_maintenance >= max(60, settings.graph_maintenance_interval_seconds):
                await graph_subscription_maintenance()
                last_graph_maintenance = now
            processed = await process_once()
            if not processed:
                await asyncio.sleep(5)
        except Exception:
            logger.exception('Worker polling error; retrying after delay.')
            await asyncio.sleep(15)


if __name__ == '__main__':
    asyncio.run(main())
