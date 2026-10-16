"""Durable Microsoft Graph subscription lifecycle and missed-event recovery.

Webhook delivery is an optimization, not the sole source of truth. A persisted
subscription record plus delta synchronization allows OrderNexa to recover
messages that were missed while the callback or worker was unavailable.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.contracts import JobKind
from app.automation.jobs import graph_event_id, publish_job
from app.core.config import settings
from app.integrations.graph_auth import application_token
from app.integrations.microsoft_graph import MicrosoftGraph, GraphIntegrationError, is_public_https_callback
from app.models.digital_twin import ExternalSubscription


class GraphSubscriptionConfigurationError(RuntimeError):
    pass


def _parse_graph_datetime(value: str) -> datetime:
    if not value:
        raise ValueError("Graph subscription response omitted expirationDateTime.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _client_state_hash() -> str | None:
    if not settings.graph_client_state:
        return None
    return hashlib.sha256(settings.graph_client_state.encode()).hexdigest()


def graph_resource() -> str:
    if settings.graph_subscription_resource:
        return settings.graph_subscription_resource
    if not settings.graph_mailbox:
        return ""
    return f"/users/{settings.graph_mailbox}/mailFolders('Inbox')/messages"


def validate_configuration(*, require_callbacks: bool = True) -> None:
    missing = []
    for name, value in {
        "GRAPH_TENANT_ID": settings.graph_tenant_id,
        "GRAPH_CLIENT_ID": settings.graph_client_id,
        "GRAPH_CLIENT_SECRET": settings.graph_client_secret,
        "GRAPH_MAILBOX": settings.graph_mailbox,
        "GRAPH_CLIENT_STATE": settings.graph_client_state,
    }.items():
        if not value:
            missing.append(name)
    if not 32 <= len(settings.graph_client_state) <= 128:
        missing.append("GRAPH_CLIENT_STATE(32-128 chars)")
    if require_callbacks:
        if not is_public_https_callback(settings.graph_notification_url):
            missing.append("GRAPH_NOTIFICATION_URL(public https)")
        if not is_public_https_callback(settings.graph_lifecycle_url):
            missing.append("GRAPH_LIFECYCLE_URL(public https)")
    if missing:
        raise GraphSubscriptionConfigurationError("Missing Graph configuration: " + ", ".join(sorted(set(missing))))


async def _persist_remote(session: AsyncSession, remote: dict) -> ExternalSubscription:
    subscription_id = str(remote.get("id") or "")
    if not subscription_id:
        raise GraphIntegrationError("Graph subscription response did not include an ID.")
    row = await session.scalar(
        select(ExternalSubscription).where(
            ExternalSubscription.provider == "MICROSOFT_GRAPH",
            ExternalSubscription.subscription_id == subscription_id,
        )
    )
    if row is None:
        row = ExternalSubscription(
            provider="MICROSOFT_GRAPH",
            subscription_id=subscription_id,
            resource=str(remote.get("resource") or graph_resource()),
            expires_at=_parse_graph_datetime(str(remote.get("expirationDateTime") or "")),
            client_state_hash=_client_state_hash(),
            status="ACTIVE",
            extra_data={},
        )
        session.add(row)
    else:
        row.resource = str(remote.get("resource") or row.resource)
        row.expires_at = _parse_graph_datetime(str(remote.get("expirationDateTime") or ""))
        row.client_state_hash = _client_state_hash()
        row.status = "ACTIVE"
    await session.commit()
    await session.refresh(row)
    return row


async def configured_subscription(session: AsyncSession) -> ExternalSubscription | None:
    # Prefer the explicit configured ID, then newest durable active record.
    if settings.graph_subscription_id:
        row = await session.scalar(
            select(ExternalSubscription).where(
                ExternalSubscription.provider == "MICROSOFT_GRAPH",
                ExternalSubscription.subscription_id == settings.graph_subscription_id,
            )
        )
        if row:
            return row
    return await session.scalar(
        select(ExternalSubscription)
        .where(ExternalSubscription.provider == "MICROSOFT_GRAPH", ExternalSubscription.status == "ACTIVE")
        .order_by(ExternalSubscription.expires_at.desc())
        .limit(1)
    )


async def accepted_subscription(session: AsyncSession, subscription_id: str) -> bool:
    if settings.graph_subscription_id and subscription_id == settings.graph_subscription_id:
        return True
    row = await session.scalar(
        select(ExternalSubscription.id).where(
            ExternalSubscription.provider == "MICROSOFT_GRAPH",
            ExternalSubscription.subscription_id == subscription_id,
            ExternalSubscription.status == "ACTIVE",
        )
    )
    return row is not None


async def inspect_or_register_subscription(session: AsyncSession) -> ExternalSubscription:
    validate_configuration(require_callbacks=False)
    graph = MicrosoftGraph(token_provider=application_token)
    row = await configured_subscription(session)
    subscription_id = settings.graph_subscription_id or (row.subscription_id if row else "")
    if not subscription_id:
        raise GraphSubscriptionConfigurationError(
            "No Graph subscription ID exists yet. Use the explicit ensure/create action after configuring public HTTPS callbacks."
        )
    remote = await graph.get_subscription(subscription_id)
    return await _persist_remote(session, remote)


async def ensure_subscription(session: AsyncSession, *, allow_create: bool) -> dict:
    """Inspect, renew, or explicitly create the mailbox subscription.

    Creation/renewal is a live external write and is never performed unless the
    caller explicitly authorizes it and AUTOMATION_LIVE_WRITES is enabled.
    """
    validate_configuration(require_callbacks=True)
    graph = MicrosoftGraph(token_provider=application_token)
    row = await configured_subscription(session)
    now = datetime.now(UTC)

    if row:
        try:
            remote = await graph.get_subscription(row.subscription_id)
            row = await _persist_remote(session, remote)
        except GraphIntegrationError as exc:
            if "HTTP 404" not in str(exc):
                raise
            row.status = "REMOVED"
            row.lifecycle_event = "subscriptionRemoved"
            await session.commit()
            row = None

    if row is None and settings.graph_subscription_id:
        try:
            remote = await graph.get_subscription(settings.graph_subscription_id)
            row = await _persist_remote(session, remote)
        except GraphIntegrationError as exc:
            if "HTTP 404" not in str(exc):
                raise

    if row is None:
        if not allow_create or not settings.automation_live_writes:
            raise GraphSubscriptionConfigurationError(
                "Graph subscription is absent. Enable live writes only after callback/permission review, then run ensure with allow_create=true."
            )
        expiration = now + timedelta(days=2)
        remote = await graph.create_subscription(
            resource=graph_resource(),
            notification_url=settings.graph_notification_url,
            lifecycle_url=settings.graph_lifecycle_url,
            expiration=expiration,
            client_state=settings.graph_client_state,
        )
        row = await _persist_remote(session, remote)
        row.last_renewed_at = now
        await session.commit()
        return {"action": "CREATED", "subscription_id": row.subscription_id, "expires_at": row.expires_at.isoformat()}

    renewal_due = row.expires_at <= now + timedelta(minutes=settings.graph_renewal_margin_minutes)
    if renewal_due:
        if not settings.automation_live_writes:
            return {
                "action": "RENEWAL_REQUIRED",
                "subscription_id": row.subscription_id,
                "expires_at": row.expires_at.isoformat(),
            }
        expiration = now + timedelta(days=2)
        remote = await graph.renew_subscription(subscription_id=row.subscription_id, expiration=expiration)
        row = await _persist_remote(session, remote)
        row.last_renewed_at = now
        await session.commit()
        return {"action": "RENEWED", "subscription_id": row.subscription_id, "expires_at": row.expires_at.isoformat()}

    return {"action": "HEALTHY", "subscription_id": row.subscription_id, "expires_at": row.expires_at.isoformat()}


async def delta_sync(session: AsyncSession, *, reason: str = "MANUAL") -> dict:
    validate_configuration(require_callbacks=False)
    row = await configured_subscription(session)
    if row is None:
        row = await inspect_or_register_subscription(session)
    graph = MicrosoftGraph(token_provider=application_token)
    changes, new_delta = await graph.message_delta(
        mailbox=settings.graph_mailbox,
        delta_link=row.delta_link,
        max_pages=settings.graph_delta_max_pages,
    )
    queued = 0
    ignored = 0
    for item in changes:
        if "@removed" in item:
            ignored += 1
            continue
        message_id = item.get("id")
        if not isinstance(message_id, str) or not message_id:
            ignored += 1
            continue
        payload = {
            "subscription_id": row.subscription_id,
            "message_id": message_id,
            "mailbox": settings.graph_mailbox,
            "recovered_by": "DELTA_SYNC",
        }
        _, created = await publish_job(
            session,
            key=graph_event_id(row.subscription_id, message_id),
            kind=JobKind.GRAPH_MESSAGE,
            payload=payload,
            requested_by=f"GRAPH_DELTA_{reason}",
            correlation_id=f"graph-delta:{reason.lower()}:{row.subscription_id}"[:128],
        )
        queued += int(created)
    # Advance the delta token only after every accepted change has been durably
    # inserted/deduplicated in PostgreSQL.
    if new_delta:
        row.delta_link = new_delta
    row.last_delta_sync_at = datetime.now(UTC)
    row.lifecycle_event = None
    row.status = "ACTIVE"
    await session.commit()
    return {
        "subscription_id": row.subscription_id,
        "changes_seen": len(changes),
        "jobs_created": queued,
        "ignored": ignored,
        "delta_link_advanced": bool(new_delta),
        "synced_at": row.last_delta_sync_at.isoformat(),
    }


async def record_lifecycle_event(session: AsyncSession, *, subscription_id: str, event: str) -> None:
    row = await session.scalar(
        select(ExternalSubscription).where(
            ExternalSubscription.provider == "MICROSOFT_GRAPH",
            ExternalSubscription.subscription_id == subscription_id,
        )
    )
    if row:
        row.lifecycle_event = event
        if event == "subscriptionRemoved":
            row.status = "REMOVED"
        elif event in {"missed", "reauthorizationRequired"}:
            row.status = "ATTENTION"
        await session.commit()
