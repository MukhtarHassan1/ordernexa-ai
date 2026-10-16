"""Authenticated, durable automation APIs. No direct ERP/AI side effects in webhooks."""
import hashlib
import hmac
import re
from datetime import UTC, datetime
from urllib.parse import unquote
from uuid import UUID
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.automation.contracts import ExternalSchedule, JobKind, N8NIngress, VoiceChangeIn, VoiceDecisionIn, ReconcileRequest
from app.automation.jobs import (IdempotencyConflict, canonical_hash, graph_event_id,
                                 public_job, publish_job, verify_webhook_secret)
from app.core.config import settings
from app.integrations.microsoft_graph import is_public_https_callback
from app.core.security import DemoPrincipal, require_operator
from app.db.session import get_db
from app.models.automation import AutomationJob, VoiceChangeRequest
from app.models.digital_twin import IntegrationCommand, Approval
from app.models.transaction import Transaction, TransactionEvent
from app.services.object_storage import object_storage
from app.automation.graph_subscription import (
    accepted_subscription, configured_subscription, delta_sync, ensure_subscription,
    inspect_or_register_subscription, record_lifecycle_event,
    GraphSubscriptionConfigurationError,
)

router = APIRouter(prefix='/automation', tags=['automation'])


def _need_role(principal: DemoPrincipal, *roles: str):
    if principal.role not in roles:
        raise HTTPException(403, 'This operation requires a different operator role.')


def _voice_auth(provided: str | None):
    if not verify_webhook_secret(provided, settings.voice_server_secret):
        raise HTTPException(403, 'Voice integration is not configured or has invalid credentials.')


def _graph_notification_valid(obj: dict) -> bool:
    return (isinstance(obj, dict) and
            verify_webhook_secret(obj.get('clientState'), settings.graph_client_state) and
            isinstance(obj.get('subscriptionId'), str) and
            obj.get('changeType') == 'created' and
            isinstance((obj.get('resourceData') or {}).get('id'), str) and
            0 < len(obj['resourceData']['id']) <= 350 and
            not obj.get('encryptedContent') and
            not obj.get('validationTokens'))


@router.post('/graph/notifications')
async def graph_webhook(request: Request, validationToken: str | None = Query(default=None),
                        db: AsyncSession = Depends(get_db)):
    # Graph endpoint validation is a POST with an opaque query token, not JSON.
    if validationToken is not None:
        if len(validationToken) > 2048 or not validationToken:
            raise HTTPException(400, 'Invalid validation token.')
        return Response(content=validationToken, media_type='text/plain; charset=utf-8')
    # Basic (non-rich) notifications only. Rich/JWT notifications require a dedicated validator.
    if not (32 <= len(settings.graph_client_state) <= 128 and settings.graph_mailbox):
        raise HTTPException(503, 'Graph webhook has not been configured.')
    try:
        raw = await request.body()
        if len(raw) > 128_000:
            raise ValueError('Webhook body too large.')
        import json
        values = json.loads(raw).get('value', [])
        if not isinstance(values, list) or len(values) > 100:
            raise ValueError('Invalid notification batch.')
    except (ValueError, TypeError):
        raise HTTPException(400, 'Invalid Graph notification body.') from None
    accepted = 0
    for entry in values:
        if not _graph_notification_valid(entry):
            continue
        subscription_id = entry['subscriptionId']
        if not await accepted_subscription(db, subscription_id):
            continue
        message_id = entry['resourceData']['id']
        payload = {'subscription_id': subscription_id,
                   'message_id': message_id, 'mailbox': settings.graph_mailbox}
        await publish_job(db, key=graph_event_id(subscription_id, message_id),
                          kind=JobKind.GRAPH_MESSAGE, payload=payload, requested_by='GRAPH_WEBHOOK',
                          correlation_id=getattr(request.state, 'correlation_id', None))
        accepted += 1
    # Do not disclose clientState validation outcome to a remote sender.
    return Response(status_code=202, headers={'X-Queued-Count': str(accepted)})


@router.post('/graph/lifecycle')
async def graph_lifecycle(request: Request, validationToken: str | None = Query(default=None),
                          db: AsyncSession = Depends(get_db)):
    if validationToken is not None:
        if not validationToken or len(validationToken) > 2048:
            raise HTTPException(400, 'Invalid validation token.')
        return Response(content=validationToken, media_type='text/plain; charset=utf-8')
    if not 32 <= len(settings.graph_client_state) <= 128:
        raise HTTPException(503, 'Graph lifecycle callback not configured.')
    try:
        import json
        raw = await request.body()
        if len(raw) > 128_000:
            raise ValueError('Body too large.')
        values = json.loads(raw)['value']
        if not isinstance(values, list) or len(values) > 100:
            raise ValueError('Invalid batch.')
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, 'Invalid lifecycle payload.') from None
    accepted = 0
    for item in values:
        if not isinstance(item, dict) or not verify_webhook_secret(item.get('clientState'), settings.graph_client_state):
            continue
        subscription_id = item.get('subscriptionId')
        if not isinstance(subscription_id, str) or not await accepted_subscription(db, subscription_id):
            continue
        event = item.get('lifecycleEvent')
        if event not in {'missed', 'subscriptionRemoved', 'reauthorizationRequired'}:
            continue
        fingerprint = canonical_hash({'subscription': subscription_id,
                                      'event': event, 'expiration': item.get('subscriptionExpirationDateTime')})
        await record_lifecycle_event(db, subscription_id=subscription_id, event=event)
        await publish_job(db, key=f'graph-lifecycle:{fingerprint}', kind=JobKind.GRAPH_LIFECYCLE,
                          payload={'event': event, 'subscription': subscription_id},
                          requested_by='GRAPH_LIFECYCLE', correlation_id=getattr(request.state, 'correlation_id', None))
        accepted += 1
    return Response(status_code=202, headers={'X-Queued-Count': str(accepted)})


@router.get('/graph/subscription')
async def graph_subscription_status(
    db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    _need_role(principal, 'OPERATIONS_MANAGER', 'ADMIN', 'AUDITOR')
    row = await configured_subscription(db)
    if row is None:
        return {'configured': False, 'message': 'No durable Graph subscription record exists yet.'}
    return {
        'configured': True, 'subscription_id': row.subscription_id,
        'resource': row.resource, 'status': row.status,
        'expires_at': row.expires_at.isoformat(),
        'last_renewed_at': row.last_renewed_at.isoformat() if row.last_renewed_at else None,
        'last_delta_sync_at': row.last_delta_sync_at.isoformat() if row.last_delta_sync_at else None,
        'lifecycle_event': row.lifecycle_event,
        'delta_initialized': bool(row.delta_link),
    }


@router.post('/graph/subscription/ensure')
async def graph_subscription_ensure(
    allow_create: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    _need_role(principal, 'OPERATIONS_MANAGER', 'ADMIN')
    try:
        return await ensure_subscription(db, allow_create=allow_create)
    except GraphSubscriptionConfigurationError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post('/graph/delta-sync')
async def graph_delta_recovery(
    db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    _need_role(principal, 'OPERATIONS_MANAGER', 'ADMIN')
    try:
        return await delta_sync(db, reason='OPERATOR')
    except GraphSubscriptionConfigurationError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post('/n8n/intake', status_code=202)
async def n8n_ingress(request: Request, data: N8NIngress,
                      x_ordernexa_ingest_secret: str | None = Header(default=None),
                      db: AsyncSession = Depends(get_db)):
    if not verify_webhook_secret(x_ordernexa_ingest_secret, settings.n8n_ingest_secret):
        raise HTTPException(403, 'Invalid automation ingress credentials.')
    try:
        raw = data.document_bytes(settings.max_upload_bytes)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    # The document itself is stored in MinIO, never in the job table or logs.
    digest = hashlib.sha256(raw).hexdigest()
    key = 'n8n:' + hashlib.sha256(data.event_id.encode()).hexdigest()
    prior = await db.scalar(select(AutomationJob).where(AutomationJob.idempotency_key == key))
    base = {'hash': digest, 'subject_hash': hashlib.sha256(data.subject.encode()).hexdigest(),
            'sender_hash': hashlib.sha256(data.sender.lower().encode()).hexdigest()}
    if prior and (prior.payload or {}).get('source_checksums') != base:
        raise HTTPException(409, 'Event ID reused with different content; original event was retained.')
    if not prior:
        safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', data.filename.split('/')[-1])[:180]
        if not data.content_base64:
            safe_filename = 'email-body.txt'
        if not safe_filename.lower().endswith(('.pdf', '.xlsx', '.txt', '.csv', '.png', '.jpg', '.jpeg', '.webp')):
            raise HTTPException(422, 'Unsupported document extension.')
        obj_key = f'automation/n8n/{digest}/{safe_filename}'
        if not await object_storage.exists(obj_key):
            await object_storage.put_bytes(object_key=obj_key, data=raw)
        payload = {'source_checksums': base, 'object_key': obj_key, 'filename': safe_filename}
    else:
        payload = prior.payload
    try:
        job, created = await publish_job(db, key=key, kind=JobKind.N8N_DOCUMENT,
                                          payload=payload, requested_by='N8N_INGRESS',
                                          correlation_id=getattr(request.state, 'correlation_id', None))
    except IdempotencyConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return {'job_id': str(job.id), 'status': job.status, 'created': created,
            'message': 'Document saved; processing is asynchronous and review-gated.'}


@router.post('/transactions/{public_id}/schedule', status_code=202)
async def schedule_verified_transaction(request: Request, public_id: str, data: ExternalSchedule,
                                         db: AsyncSession = Depends(get_db),
                                         principal: DemoPrincipal = Depends(require_operator)):
    _need_role(principal, 'OPERATIONS_MANAGER', 'ADMIN')
    tx = await db.scalar(select(Transaction).where(Transaction.public_id == public_id).with_for_update())
    if not tx:
        raise HTTPException(404, 'Transaction not found.')
    if tx.status != 'COMPLETED':
        raise HTTPException(409, 'Only verified and completed local transactions can be externally synchronized.')
    local = (await db.execute(select(IntegrationCommand).where(
        IntegrationCommand.transaction_id == tx.id,
        IntegrationCommand.status == 'VERIFIED'))).scalars().all()
    if not (any(c.provider == 'ODOO' and c.action == 'CREATE_SALE_ORDER' and c.external_id for c in local) and
            any(c.action == 'ARCHIVE_CONFIRMATION' and c.provider == 'MINIO_LOCAL' for c in local)):
        raise HTTPException(409, 'Odoo and MinIO verification records are both required before external synchronization.')
    # Read-only dry queueing is useful during local setup; worker will block writes unless explicitly enabled.
    kinds = [kind for flag, kind in (
        (data.sharepoint, JobKind.SHAREPOINT_ARCHIVE),
        (data.hubspot, JobKind.HUBSPOT_CONTACT),
        (data.outlook_draft, JobKind.OUTLOOK_DRAFT),
        (data.teams_notify, JobKind.TEAMS_NOTIFY)) if flag]
    result = []
    for kind in kinds:
        payload = {'transaction_public_id': tx.public_id,
                   'verified_contact_email': data.verified_contact_email or ''}
        job, created = await publish_job(db, key=f'external:{tx.public_id}:{kind}:v1',
                                          kind=kind, payload=payload, transaction_id=tx.id,
                                          requested_by=principal.actor_id, correlation_id=getattr(request.state, 'correlation_id', None))
        result.append({'kind': kind, 'job_id': str(job.id), 'created': created, 'status': job.status})
    return {'public_id': public_id, 'jobs': result,
            'live_writes_enabled': settings.automation_live_writes,
            'message': 'Jobs queued; each operation verifies its own prerequisite and policy.'}


@router.post('/transactions/{public_id}/notify-approvals', status_code=202)
async def schedule_teams_approval(request: Request, public_id: str,
                                   db: AsyncSession = Depends(get_db),
                                   principal: DemoPrincipal = Depends(require_operator)):
    _need_role(principal, 'OPERATIONS_MANAGER', 'ADMIN')
    tx = await db.scalar(select(Transaction).where(Transaction.public_id == public_id))
    if not tx or tx.status != 'APPROVAL_REQUIRED':
        raise HTTPException(409, 'Only currently approval-required transactions qualify.')
    pending = (await db.execute(select(Approval).where(
        Approval.transaction_id == tx.id, Approval.status == 'PENDING'))).scalars().all()
    if not pending:
        raise HTTPException(409, 'No pending approvals remain.')
    job, created = await publish_job(db, key=f'approval-notify:{tx.public_id}:v1',
        kind=JobKind.TEAMS_APPROVAL_NOTIFY,
        payload={'transaction_public_id': public_id, 'approval_count': len(pending)},
        transaction_id=tx.id, requested_by=principal.actor_id,
        correlation_id=getattr(request.state, 'correlation_id', None))
    return {'job_id': str(job.id), 'status': job.status, 'created': created,
            'message': 'Teams notification only. A real operator must approve in the protected web console.'}


@router.get('/jobs')
async def list_jobs(limit: int = Query(default=50, ge=1, le=200), db: AsyncSession = Depends(get_db),
                    principal: DemoPrincipal = Depends(require_operator)):
    _need_role(principal, 'OPERATIONS_MANAGER', 'ADMIN', 'AUDITOR')
    jobs = (await db.execute(select(AutomationJob).order_by(AutomationJob.created_at.desc()).limit(limit))).scalars().all()
    return {'items': [public_job(job) for job in jobs]}


@router.post('/jobs/{job_id}/retry')
async def retry_safe_job(job_id: UUID, db: AsyncSession = Depends(get_db),
                         principal: DemoPrincipal = Depends(require_operator)):
    _need_role(principal, 'OPERATIONS_MANAGER', 'ADMIN')
    job = await db.scalar(select(AutomationJob).where(AutomationJob.id == job_id).with_for_update())
    if not job:
        raise HTTPException(404, 'Job not found.')
    if job.status not in {'BLOCKED_CONFIG', 'FAILED_MANUAL'}:
        raise HTTPException(409, 'Only resolved configuration failures or explicitly safe failures can be retried. Ambiguous external writes require remote reconciliation.')
    # All non-idempotent remote POSTs remain excluded from automatic retry.
    if job.kind in {'TEAMS_NOTIFY', 'OUTLOOK_DRAFT'} and job.attempt_count:
        raise HTTPException(409, 'A remote POST may have succeeded. Inspect the remote service before any new action.')
    job.status = 'PENDING'
    job.next_attempt_at = datetime.now(UTC)
    job.last_error = None
    await db.commit()
    return public_job(job)


@router.post('/jobs/{job_id}/reconcile')
async def reconcile_uncertain_job(job_id: UUID, data: ReconcileRequest,
                                   db: AsyncSession = Depends(get_db),
                                   principal: DemoPrincipal = Depends(require_operator)):
    _need_role(principal, 'OPERATIONS_MANAGER', 'ADMIN')
    job = await db.scalar(select(AutomationJob).where(AutomationJob.id == job_id).with_for_update())
    if not job:
        raise HTTPException(404, 'Job not found.')
    from app.automation.reconcile import reconcile, ReconciliationRejected
    try:
        status = await reconcile(db, job=job, request=data, actor_id=principal.actor_id)
    except ReconciliationRejected as exc:
        raise HTTPException(409, str(exc)) from exc
    return {'status': status, 'job': public_job(job)}


@router.get('/jobs/{job_id}/outlook-preview')
async def outlook_draft_preview(job_id: UUID, db: AsyncSession = Depends(get_db),
                                principal: DemoPrincipal = Depends(require_operator)):
    _need_role(principal, 'OPERATIONS_MANAGER', 'ADMIN', 'FINANCE_MANAGER')
    job = await db.get(AutomationJob, job_id)
    if not job:
        raise HTTPException(404, 'Outlook draft job not found.')
    from app.automation.outlook_release import live_preview, DraftReleaseRejected
    try:
        return await live_preview(db, job)
    except DraftReleaseRejected as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post('/jobs/{job_id}/send-outlook')
async def send_approved_outlook_draft(job_id: UUID, data: dict = Body(...),
                                       db: AsyncSession = Depends(get_db),
                                       principal: DemoPrincipal = Depends(require_operator)):
    _need_role(principal, 'OPERATIONS_MANAGER', 'ADMIN', 'FINANCE_MANAGER')
    if not data.get('confirm_send_once') or not isinstance(data.get('preview_sha256'), str) or len(data['preview_sha256']) != 64:
        raise HTTPException(422, 'Explicit approval and exact preview checksum required.')
    job = await db.scalar(select(AutomationJob).where(AutomationJob.id == job_id).with_for_update())
    if not job:
        raise HTTPException(404, 'Outlook draft job not found.')
    from app.automation.outlook_release import release_draft, DraftReleaseRejected
    try:
        return await release_draft(db, job, preview_sha256=data['preview_sha256'], actor_id=principal.actor_id)
    except DraftReleaseRejected as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get('/configuration')
async def configuration(
    db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    # Reflect configured vs missing, never reveal secret values. A durable Graph
    # subscription is authoritative; GRAPH_SUBSCRIPTION_ID remains a backwards
    # compatible bootstrap hint rather than a completion signal.
    subscription = await configured_subscription(db)
    oidc_ready = bool(
        settings.oidc_issuer.strip() and settings.oidc_audience.strip()
        and settings.oidc_jwks_url.strip().startswith('https://')
    )
    return {
        'worker_enabled': settings.automation_worker_enabled,
        'external_writes_enabled': settings.automation_live_writes,
        'customer_email_enabled': settings.customer_email_enabled,
        'auth_mode': settings.auth_mode,
        'production_oidc_configured': oidc_ready,
        'graph_credentials_configured': bool(
            settings.graph_client_state and settings.graph_mailbox
            and settings.graph_client_id and settings.graph_client_secret
            and settings.graph_tenant_id
        ),
        'graph_callback_urls_configured': bool(
            is_public_https_callback(settings.graph_notification_url)
            and is_public_https_callback(settings.graph_lifecycle_url)
        ),
        'graph_subscription_registered': bool(subscription),
        'graph_subscription_status': subscription.status if subscription else None,
        'graph_subscription_expires_at': subscription.expires_at.isoformat() if subscription else None,
        'sharepoint_configured': bool(settings.graph_drive_id),
        'hubspot_configured': bool(settings.hubspot_access_token),
        'teams_configured': bool(settings.teams_approval_webhook_url),
        'n8n_configured': len(settings.n8n_ingest_secret) >= 32,
        'voice_configured': len(settings.voice_server_secret) >= 32,
        'stripe_sandbox_configured': bool(settings.stripe_enabled and settings.stripe_secret_key and settings.stripe_webhook_secret),
        'notice': 'Configured does not mean live-verified. Integration Health records only observed/runtime evidence.',
    }


@router.get('/audit/{public_id}')
async def transaction_audit(public_id: str, db: AsyncSession = Depends(get_db),
                            principal: DemoPrincipal = Depends(require_operator)):
    _need_role(principal, 'OPERATIONS_MANAGER', 'ADMIN', 'AUDITOR', 'FINANCE_MANAGER')
    tx = await db.scalar(select(Transaction).where(Transaction.public_id == public_id))
    if not tx:
        raise HTTPException(404, 'Transaction not found.')
    events = (await db.execute(select(TransactionEvent).where(TransactionEvent.transaction_id == tx.id)
                               .order_by(TransactionEvent.created_at))).scalars().all()
    # Hashes permit evidence correlation without disclosing raw payloads or AI source documents.
    return {'public_id': public_id, 'events': [
        {'step': e.step, 'event_type': e.event_type, 'actor_type': e.actor_type,
         'actor_id': e.actor_id, 'timestamp': e.created_at.isoformat(),
         'payload_hash': e.payload_hash, 'trace_id': e.trace_id}
        for e in events]}


@router.get('/voice/status/{public_id}')
async def voice_status(public_id: str, x_ordernexa_voice_secret: str | None = Header(default=None),
                       db: AsyncSession = Depends(get_db)):
    _voice_auth(x_ordernexa_voice_secret)
    # No private order value, customer identity or delivery data without end-caller verification.
    tx = await db.scalar(select(Transaction).where(Transaction.public_id == public_id))
    return {'found': bool(tx), 'safe_status': (
        'IN_REVIEW' if tx and tx.status in {'APPROVAL_REQUIRED', 'WAITING_CUSTOMER'} else
        'PROCESSING' if tx and tx.status not in {'COMPLETED', 'CANCELLED'} else
        'PROCESSED' if tx and tx.status == 'COMPLETED' else
        'CLOSED' if tx else 'UNKNOWN'),
        'notice': 'Customer identity is not verified by this endpoint; never disclose prices or make order changes.'}


@router.post('/voice/change-request', status_code=202)
async def voice_change(data: VoiceChangeIn,
                       x_ordernexa_voice_secret: str | None = Header(default=None),
                       db: AsyncSession = Depends(get_db)):
    _voice_auth(x_ordernexa_voice_secret)
    tx = await db.scalar(select(Transaction).where(Transaction.public_id == data.transaction_public_id))
    if not tx:
        raise HTTPException(404, 'No matching reference; caller verification and human follow-up required.')
    key = 'voice:' + hashlib.sha256((data.event_id + '\x00' + data.call_id).encode()).hexdigest()
    stmt = insert(VoiceChangeRequest).values(
        transaction_id=tx.id, idempotency_key=key, request_type=data.request_type,
        request_note=data.request_note, status='PENDING_VERIFICATION', external_call_id=data.call_id,
    ).on_conflict_do_nothing(index_elements=['idempotency_key']).returning(VoiceChangeRequest.id)
    row_id = (await db.execute(stmt)).scalar_one_or_none()
    existing = await db.scalar(select(VoiceChangeRequest).where(VoiceChangeRequest.idempotency_key == key))
    if existing and (existing.request_type != data.request_type or existing.request_note != data.request_note or existing.transaction_id != tx.id):
        raise HTTPException(409, 'Voice event ID reused with different content.')
    await db.commit()
    return {'request_id': str(row_id or existing.id), 'created': row_id is not None,
            'status': 'PENDING_VERIFICATION', 'message': 'A human must verify caller identity and decide next steps.'}


@router.get('/voice/requests')
async def voice_requests(principal: DemoPrincipal = Depends(require_operator),
                         db: AsyncSession = Depends(get_db)):
    _need_role(principal, 'OPERATIONS_MANAGER', 'ADMIN', 'SALES_MANAGER')
    rows = (await db.execute(select(VoiceChangeRequest).order_by(VoiceChangeRequest.created_at.desc()).limit(100))).scalars().all()
    return {'items': [{'id': str(row.id), 'transaction_id': str(row.transaction_id),
                       'request_type': row.request_type, 'request_note': row.request_note,
                       'status': row.status, 'created_at': row.created_at.isoformat()}
                      for row in rows]}


@router.post('/voice/requests/{request_id}/decision')
async def voice_review(request_id: UUID, data: VoiceDecisionIn,
                       principal: DemoPrincipal = Depends(require_operator),
                       db: AsyncSession = Depends(get_db)):
    _need_role(principal, 'OPERATIONS_MANAGER', 'ADMIN', 'SALES_MANAGER')
    row = await db.scalar(select(VoiceChangeRequest).where(VoiceChangeRequest.id == request_id).with_for_update())
    if not row:
        raise HTTPException(404, 'Voice request not found.')
    if row.status != 'PENDING_VERIFICATION':
        raise HTTPException(409, 'Request already reviewed. No automated order amendments are supported.')
    row.status = data.decision
    row.review_note = data.note
    row.reviewed_by = principal.actor_id
    row.reviewed_at = datetime.now(UTC)
    await db.commit()
    return {'request_id': str(row.id), 'status': row.status,
            'message': 'This decision does not modify the original order.'}
