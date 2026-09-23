import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TransactionStatus
from app.models.transaction import Transaction, TransactionEvent
from app.schemas.transaction import TransactionAdvance, TransactionCreate
from app.services.state_machine import validate_transition


def _payload_hash(payload: dict) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

    return hashlib.sha256(canonical).hexdigest()


async def _next_public_id(
    session: AsyncSession,
) -> str:
    sequence_number = await session.scalar(
        text("SELECT nextval('transaction_public_id_seq')")
    )

    year = datetime.now(UTC).year

    return f"TXN-{year}-{int(sequence_number):06d}"


async def create_transaction(
    session: AsyncSession,
    data: TransactionCreate,
) -> Transaction:
    public_id = await _next_public_id(session)
    correlation_id = uuid4().hex

    transaction = Transaction(
        public_id=public_id,
        correlation_id=correlation_id,
        customer_reference=data.customer_reference,
        source=data.source.upper(),
        intent=data.intent,
        currency=data.currency.upper(),
        value=data.value,
        status=TransactionStatus.RECEIVED.value,
        version=1,
    )

    session.add(transaction)
    await session.flush()

    payload = {
        "source": transaction.source,
        "intent": transaction.intent,
        "customer_reference": transaction.customer_reference,
    }

    event = TransactionEvent(
        transaction_id=transaction.id,
        step="INTAKE",
        actor_type="SYSTEM",
        event_type="TRANSACTION_RECEIVED",
        payload=payload,
        payload_hash=_payload_hash(payload),
        trace_id=transaction.correlation_id,
    )

    session.add(event)

    await session.commit()
    await session.refresh(transaction)

    return transaction


async def list_transactions(
    session: AsyncSession,
) -> list[Transaction]:
    result = await session.execute(
        select(Transaction)
        .order_by(Transaction.created_at.desc())
    )

    return list(result.scalars().all())


async def get_transaction(
    session: AsyncSession,
    public_id: str,
) -> Transaction | None:
    result = await session.execute(
        select(Transaction)
        .where(Transaction.public_id == public_id)
    )

    return result.scalar_one_or_none()


async def get_transaction_for_update(
    session: AsyncSession,
    public_id: str,
) -> Transaction | None:
    result = await session.execute(
        select(Transaction)
        .where(Transaction.public_id == public_id)
        .with_for_update()
    )

    return result.scalar_one_or_none()


async def get_timeline(
    session: AsyncSession,
    transaction_id,
) -> list[TransactionEvent]:
    result = await session.execute(
        select(TransactionEvent)
        .where(
            TransactionEvent.transaction_id == transaction_id
        )
        .order_by(TransactionEvent.created_at.asc())
    )

    return list(result.scalars().all())


async def advance_transaction(
    session: AsyncSession,
    transaction: Transaction,
    data: TransactionAdvance,
) -> Transaction:
    current_status = TransactionStatus(transaction.status)
    target_status = TransactionStatus(data.target_status)

    validate_transition(
        current=current_status,
        target=target_status,
    )

    previous_status = transaction.status

    transaction.status = target_status.value
    transaction.version += 1

    if target_status == TransactionStatus.COMPLETED:
        transaction.completed_at = datetime.now(UTC)

    payload = {
        "from_status": previous_status,
        "to_status": target_status.value,
        "transaction_version": transaction.version,
        **data.payload,
    }

    event = TransactionEvent(
        transaction_id=transaction.id,
        step=target_status.value,
        actor_type=data.actor_type,
        actor_id=data.actor_id,
        event_type=data.event_type,
        payload=payload,
        payload_hash=_payload_hash(payload),
        trace_id=transaction.correlation_id,
    )

    session.add(event)

    await session.commit()
    await session.refresh(transaction)

    return transaction