"""Uniform write-ahead journal for consequential external integration actions."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.digital_twin import IntegrationCommand
from app.models.transaction import Transaction


async def begin_external_command(
    session: AsyncSession,
    *,
    transaction: Transaction,
    provider: str,
    action: str,
    idempotency_key: str,
    request_summary: dict,
) -> tuple[IntegrationCommand, bool]:
    command = await session.scalar(
        select(IntegrationCommand).where(IntegrationCommand.idempotency_key == idempotency_key).with_for_update()
    )
    if command:
        if command.transaction_id != transaction.id or command.provider != provider or command.action != action:
            raise ValueError("Integration idempotency key is already bound to another action.")
        if command.status == "VERIFIED" and command.external_id:
            return command, True
        if command.status == "ACKNOWLEDGED":
            # Notification transports may not expose a read-back object ID. A
            # provider ACK is still terminal for the exact same command key;
            # blindly resending would create duplicate human notifications.
            return command, True
        if command.request_payload and command.request_payload != request_summary:
            raise ValueError("Integration command payload changed after intent was persisted.")
    else:
        command = IntegrationCommand(
            transaction_id=transaction.id,
            provider=provider,
            action=action,
            action_id=uuid4().hex,
            idempotency_key=idempotency_key,
            status="PENDING",
            request_payload=request_summary,
            response_payload={},
            attempt_count=0,
        )
        session.add(command)
    command.status = "PENDING"
    command.attempt_count += 1
    command.last_error = None
    command.error_category = None
    await session.commit()  # write-ahead intent must survive process/network failure
    await session.refresh(command)
    return command, False


async def mark_external_command(
    session: AsyncSession,
    *,
    command: IntegrationCommand,
    status: str,
    external_id: str | None = None,
    response_summary: dict | None = None,
    error_category: str | None = None,
    last_error: str | None = None,
) -> None:
    command.status = status
    if external_id:
        command.external_id = str(external_id)
    if response_summary is not None:
        command.response_payload = response_summary
    command.error_category = error_category
    command.last_error = last_error
    if status in {"VERIFIED", "ACKNOWLEDGED"}:
        command.verified_at = datetime.now(UTC)
    await session.commit()
