import hashlib
import json

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TransactionStatus
from app.models.transaction import Transaction, TransactionEvent

from app.schemas.transaction import (
    TransactionAdvance,
    TransactionCreate,
)

from app.services.state_machine import validate_transition


# ============================================================
# PAYLOAD HASHING
# ============================================================

def _payload_hash(payload: dict) -> str:
    """
    Generate a deterministic SHA-256 hash of an event payload.

    This helps track the exact payload associated with
    each transaction event.
    """

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

    return hashlib.sha256(canonical).hexdigest()


# ============================================================
# REUSABLE TRANSACTION AUDIT EVENT HELPER
# ============================================================

async def append_transaction_event(
    session: AsyncSession,
    *,
    transaction: Transaction,
    step: str,
    event_type: str,
    payload: dict,
    actor_type: str = "SYSTEM",
    actor_id: str | None = None,
    commit: bool = True,
) -> TransactionEvent:
    """
    Append an auditable event to an existing transaction.

    Every event records:
    - Transaction ID
    - Execution step
    - Event type
    - Actor information
    - Event payload
    - SHA-256 payload hash
    - Correlation/trace ID

    When commit=True:
        Persist the event and commit the current transaction.

    When commit=False:
        Flush the event without committing. The calling
        service remains responsible for committing or
        rolling back the database transaction.
    """

    event = TransactionEvent(
        transaction_id=transaction.id,
        step=step,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        payload=payload,
        payload_hash=_payload_hash(payload),
        trace_id=transaction.correlation_id,
    )

    session.add(event)

    if commit:
        await session.commit()
    else:
        await session.flush()

    return event


# ============================================================
# GENERATE UNIQUE PUBLIC TRANSACTION ID
# ============================================================

async def _next_public_id(
    session: AsyncSession,
) -> str:
    """
    Generate a public transaction identifier using
    the PostgreSQL sequence.

    Example:
        TXN-2026-000001
    """

    sequence_number = await session.scalar(
        text(
            "SELECT nextval('transaction_public_id_seq')"
        )
    )

    year = datetime.now(UTC).year

    return f"TXN-{year}-{int(sequence_number):06d}"


# ============================================================
# CREATE TRANSACTION
# ============================================================

async def create_transaction(
    session: AsyncSession,
    data: TransactionCreate,
) -> Transaction:
    """
    Create a new transaction and record its initial
    TRANSACTION_RECEIVED audit event.
    """

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


# ============================================================
# LIST TRANSACTIONS
# ============================================================

async def list_transactions(
    session: AsyncSession,
) -> list[Transaction]:
    """
    Retrieve transactions ordered by creation time,
    newest first.
    """

    result = await session.execute(
        select(Transaction)
        .order_by(
            Transaction.created_at.desc()
        )
    )

    return list(result.scalars().all())


# ============================================================
# GET TRANSACTION
# ============================================================

async def get_transaction(
    session: AsyncSession,
    public_id: str,
) -> Transaction | None:
    """
    Retrieve a transaction by its public identifier.

    This method does not acquire a write lock.
    """

    result = await session.execute(
        select(Transaction)
        .where(
            Transaction.public_id == public_id
        )
    )

    return result.scalar_one_or_none()


# ============================================================
# GET TRANSACTION WITH ROW LOCK
# ============================================================

async def get_transaction_for_update(
    session: AsyncSession,
    public_id: str,
) -> Transaction | None:
    """
    Retrieve and lock a transaction row.

    This prevents concurrent writers using this locking
    convention from changing the same transaction
    simultaneously.

    The lock is held until the current database
    transaction commits or rolls back.
    """

    result = await session.execute(
        select(Transaction)
        .where(
            Transaction.public_id == public_id
        )
        .with_for_update()
    )

    return result.scalar_one_or_none()


# ============================================================
# GET TRANSACTION EVENT TIMELINE
# ============================================================

async def get_timeline(
    session: AsyncSession,
    transaction_id: UUID,
) -> list[TransactionEvent]:
    """
    Retrieve the chronological event history
    of a transaction.
    """

    result = await session.execute(
        select(TransactionEvent)
        .where(
            TransactionEvent.transaction_id == transaction_id
        )
        .order_by(
            TransactionEvent.created_at.asc()
        )
    )

    return list(result.scalars().all())


# ============================================================
# ADVANCE TRANSACTION STATE
# ============================================================

async def advance_transaction(
    session: AsyncSession,
    transaction: Transaction,
    data: TransactionAdvance,
) -> Transaction:
    """
    Validate and execute a transaction state transition.

    Every successful transition:
    - Validates the requested state change
    - Updates the transaction status
    - Increments its version
    - Records an audit event
    - Preserves the correlation ID
    """

    current_status = TransactionStatus(
        transaction.status
    )

    target_status = TransactionStatus(
        data.target_status
    )

    # Validate the requested state transition.

    validate_transition(
        current=current_status,
        target=target_status,
    )

    previous_status = transaction.status

    # Update transaction state and version.

    transaction.status = target_status.value

    transaction.version += 1

    # Record completion time for completed transactions.

    if target_status == TransactionStatus.COMPLETED:
        transaction.completed_at = datetime.now(UTC)

    # Create the state-transition audit payload.

    payload = {
        **data.payload,
        "from_status": previous_status,
        "to_status": target_status.value,
        "transaction_version": transaction.version,
    }

    # Record the transition.

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

    # Persist the transition and event.

    await session.commit()

    await session.refresh(transaction)

    return transaction