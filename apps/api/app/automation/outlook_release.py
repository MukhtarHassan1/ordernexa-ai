"""Explicit manual release of a verified Outlook draft. Never automatic."""
import hashlib
import json
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.integrations.graph_auth import application_token
from app.integrations.microsoft_graph import MicrosoftGraph
from app.models.automation import AutomationJob
from app.models.digital_twin import IntegrationCommand
from app.models.transaction import Transaction, TransactionEvent
from app.automation.jobs import canonical_hash


class DraftReleaseRejected(ValueError):
    pass


def validate_draft(draft: dict, *, draft_id: str, subject: str, recipient: str) -> dict:
    if not draft.get('isDraft') or draft.get('id') != draft_id or draft.get('subject') != subject:
        raise DraftReleaseRejected('Draft state, identity or subject changed; do not send.')
    targets = [((x or {}).get('emailAddress') or {}).get('address', '').casefold()
               for x in (draft.get('toRecipients') or [])]
    if targets != [recipient.casefold()] or draft.get('ccRecipients') or draft.get('bccRecipients'):
        raise DraftReleaseRejected('Recipient differs from human-verified job address or unexpected CC/BCC present.')
    body = draft.get('body') or {}
    if body.get('contentType', '').lower() != 'text':
        raise DraftReleaseRejected('Only the approved plain-text confirmation template can be released.')
    content = body.get('content') or ''
    if not content or len(content) > 10_000:
        raise DraftReleaseRejected('Missing or oversized confirmation body.')
    canonical = {'draft_id':draft_id, 'subject':subject, 'recipient':recipient.casefold(), 'body':content}
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'draft_id': draft_id, 'subject': subject, 'recipient': recipient,
            'body': content, 'preview_sha256': digest}


async def live_preview(session: AsyncSession, job: AutomationJob) -> dict:
    if not settings.customer_email_enabled or not settings.automation_live_writes or not settings.graph_mailbox:
        raise DraftReleaseRejected('Email release remains disabled or the verified mailbox is unconfigured.')
    if job.kind != 'OUTLOOK_DRAFT' or job.status != 'VERIFIED' or not job.external_id:
        raise DraftReleaseRejected('A verified unsent Outlook draft is required.')
    tx = await session.get(Transaction, job.transaction_id)
    if not tx or tx.status != 'COMPLETED':
        raise DraftReleaseRejected('Underlying transaction must remain COMPLETED.')
    subject = f'Order confirmation draft: {tx.customer_reference} [{tx.public_id}]'
    email = job.payload.get('verified_contact_email', '')
    if not email:
        raise DraftReleaseRejected('Human-verified recipient missing.')
    graph = MicrosoftGraph(token_provider=application_token)
    draft = await graph.get_draft(sender_id=settings.graph_mailbox, draft_id=job.external_id)
    return validate_draft(draft, draft_id=job.external_id, subject=subject, recipient=email)


async def release_draft(session: AsyncSession, job: AutomationJob, *, preview_sha256: str, actor_id: str) -> dict:
    # Caller obtains row lock on job. Uncertain commands are deliberately not replayed.
    command_key = f'outlook:release-once:{job.id}'
    command = await session.scalar(select(IntegrationCommand).where(IntegrationCommand.idempotency_key == command_key))
    if command:
        if command.status == 'ACKNOWLEDGED':
            return {'status':'ACKNOWLEDGED', 'replayed':True,
                    'notice':'Graph previously acknowledged send; check Sent Items for actual delivery.'}
        raise DraftReleaseRejected('Existing send command is pending or uncertain; inspect Outlook Sent Items, do NOT resend.')
    current = await live_preview(session, job)
    if current['preview_sha256'] != preview_sha256:
        raise DraftReleaseRejected('Draft changed since preview; refresh and review the complete content again.')
    tx = await session.get(Transaction, job.transaction_id)
    command = IntegrationCommand(transaction_id=job.transaction_id, provider='MICROSOFT_GRAPH',
        action='SEND_EXISTING_DRAFT', action_id=uuid4().hex, idempotency_key=command_key,
        status='PENDING', external_id=job.external_id,
        request_payload={'draft_id':job.external_id, 'content_hash':preview_sha256, 'approved_by':actor_id},
        response_payload={}, attempt_count=1)
    session.add(command)
    await session.commit()  # Write intent BEFORE remote effect; crashed calls require reconciliation.
    try:
        graph = MicrosoftGraph(token_provider=application_token)
        await graph.send_existing_draft_once(sender_id=settings.graph_mailbox, draft_id=job.external_id)
    except Exception as exc:
        command.status='BLOCKED_UNCERTAIN'
        command.last_error='Uncertain send; verify by searching Outlook Sent Items before any further action.'
        job.status='BLOCKED_UNCERTAIN'
        job.last_error='Outlook send response uncertain. Do not resend automatically.'
        await session.commit()
        raise DraftReleaseRejected('Send outcome uncertain; inspect Outlook Sent Items. Automatic replay is forbidden.') from exc
    command.status='ACKNOWLEDGED'
    command.response_payload={'message':'Graph accepted draft send request (not delivery proof).'}
    job.status='SENT_ACKNOWLEDGED'
    job.result_data={'message':'Graph accepted send request. Confirm actual delivery in Outlook Sent Items.'}
    event={'action':'OUTLOOK_SEND_ACKNOWLEDGED', 'job_id':str(job.id), 'operator':actor_id,
           'approved_content_hash':preview_sha256}
    session.add(TransactionEvent(transaction_id=tx.id, step='CUSTOMER_COMMUNICATION',
        actor_type='HUMAN', actor_id=actor_id, event_type='EMAIL_SEND_ACKNOWLEDGED',
        payload=event,payload_hash=canonical_hash(event),trace_id=tx.correlation_id))
    await session.commit()
    return {'status':'ACKNOWLEDGED', 'replayed':False,
            'notice':'Graph accepted the draft-send request; check Outlook Sent Items for confirmation.'}
