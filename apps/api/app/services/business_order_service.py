"""Business-level identity and duplicate protection for customer purchase orders.

Technical transaction IDs and webhook keys are not sufficient to prevent two
independent transactions from representing the same customer order. This module
creates an atomic claim on (customer, normalized PO, revision) and requires an
explicit amendment link for revisions > 1.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.digital_twin import BusinessOrderIdentity, Customer
from app.models.transaction import Transaction
from app.schemas.c2c import ManualOrderInput


def normalize_po_number(value: str) -> str:
    value = value.upper().strip()
    # Keep semantic separators out of the identity so "PO 88192" and
    # "PO-88192" cannot silently become separate orders.
    normalized = re.sub(r"[^A-Z0-9]+", "", value)
    if not normalized:
        raise ValueError("Customer PO number cannot normalize to an empty value.")
    return normalized[:120]


def order_content_fingerprint(data: ManualOrderInput) -> str:
    payload = {
        "currency": data.currency.upper(),
        "delivery_warehouse_code": data.delivery_warehouse_code.upper(),
        "requested_delivery_date": data.requested_delivery_date.isoformat() if data.requested_delivery_date else None,
        "lines": [
            {
                "line_number": line.line_number,
                "product_term": re.sub(r"\s+", " ", line.product_term.strip().upper()),
                "quantity": str(line.quantity.normalize()),
                "uom": line.uom.upper(),
                "requested_unit_price": str(line.requested_unit_price) if line.requested_unit_price is not None else None,
            }
            for line in sorted(data.lines, key=lambda x: x.line_number)
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DuplicateCandidate:
    public_id: str
    status: str
    revision: int | None
    same_content: bool | None
    completed: bool

    def as_dict(self) -> dict:
        return {
            "public_id": self.public_id,
            "status": self.status,
            "revision": self.revision,
            "same_content": self.same_content,
            "completed": self.completed,
        }


class BusinessOrderConflict(RuntimeError):
    def __init__(self, *, normalized_po: str, candidates: list[DuplicateCandidate]):
        super().__init__("A transaction already claims this customer PO revision.")
        self.normalized_po = normalized_po
        self.candidates = candidates


async def _legacy_candidates(
    session: AsyncSession,
    *,
    transaction: Transaction,
    customer: Customer,
    normalized_po: str,
    fingerprint: str,
) -> list[DuplicateCandidate]:
    rows = (
        await session.execute(
            select(Transaction)
            .where(
                Transaction.customer_id == customer.id,
                Transaction.id != transaction.id,
                Transaction.customer_reference.is_not(None),
                Transaction.status != "CANCELLED",
            )
            .order_by(Transaction.created_at.desc())
            .limit(250)
        )
    ).scalars().all()
    candidates: list[DuplicateCandidate] = []
    for row in rows:
        if normalize_po_number(row.customer_reference or "") != normalized_po:
            continue
        identity = await session.scalar(
            select(BusinessOrderIdentity).where(BusinessOrderIdentity.transaction_id == row.id)
        )
        candidates.append(
            DuplicateCandidate(
                public_id=row.public_id,
                status=row.status,
                revision=identity.revision if identity else None,
                same_content=(identity.content_fingerprint == fingerprint) if identity else None,
                completed=row.status == "COMPLETED",
            )
        )
    return candidates


async def claim_business_order(
    session: AsyncSession,
    *,
    transaction: Transaction,
    customer: Customer,
    data: ManualOrderInput,
) -> BusinessOrderIdentity:
    """Atomically claim one customer PO revision.

    Revision 1 is the ordinary order. Any revision above 1 must point at a
    previous transaction for the same customer and PO, making amendments an
    explicit governed concept rather than a duplicate-bypass flag.
    """
    normalized_po = normalize_po_number(data.po_number)
    fingerprint = order_content_fingerprint(data)
    revision = data.order_revision

    current = await session.scalar(
        select(BusinessOrderIdentity).where(BusinessOrderIdentity.transaction_id == transaction.id)
    )
    if current:
        if (
            current.customer_id != customer.id
            or current.normalized_po != normalized_po
            or current.revision != revision
            or current.content_fingerprint != fingerprint
        ):
            raise ValueError("Existing business-order identity no longer matches the transaction payload.")
        return current

    amendment_of_id: UUID | None = None
    if revision > 1:
        if not data.amendment_of_public_id:
            raise ValueError("Revisions above 1 require amendment_of_public_id.")
        parent = await session.scalar(
            select(Transaction).where(Transaction.public_id == data.amendment_of_public_id)
        )
        if not parent or parent.customer_id != customer.id:
            raise ValueError("Amendment parent does not belong to the resolved customer.")
        if normalize_po_number(parent.customer_reference or "") != normalized_po:
            raise ValueError("Amendment parent has a different customer PO number.")
        parent_identity = await session.scalar(
            select(BusinessOrderIdentity).where(BusinessOrderIdentity.transaction_id == parent.id)
        )
        parent_revision = parent_identity.revision if parent_identity else 1
        if revision != parent_revision + 1:
            raise ValueError(
                f"Amendment revision must be exactly {parent_revision + 1} for the selected parent."
            )
        amendment_of_id = parent.id
    elif data.amendment_of_public_id:
        raise ValueError("amendment_of_public_id is only valid when order_revision is greater than 1.")

    # Legacy records predate this table. They still count: a new deployment must
    # not create a duplicate simply because history was created before migration.
    legacy = await _legacy_candidates(
        session,
        transaction=transaction,
        customer=customer,
        normalized_po=normalized_po,
        fingerprint=fingerprint,
    )
    if revision == 1 and legacy:
        raise BusinessOrderConflict(normalized_po=normalized_po, candidates=legacy)

    identity = BusinessOrderIdentity(
        customer_id=customer.id,
        transaction_id=transaction.id,
        normalized_po=normalized_po,
        revision=revision,
        content_fingerprint=fingerprint,
        amendment_of_transaction_id=amendment_of_id,
        status="AMENDMENT" if revision > 1 else "ACTIVE",
    )

    # Unique DB constraint is the final concurrency guard. A savepoint prevents
    # an integrity race from rolling back previously committed transaction history.
    try:
        async with session.begin_nested():
            session.add(identity)
            await session.flush()
    except IntegrityError:
        existing = await session.scalar(
            select(BusinessOrderIdentity).where(
                BusinessOrderIdentity.customer_id == customer.id,
                BusinessOrderIdentity.normalized_po == normalized_po,
                BusinessOrderIdentity.revision == revision,
            )
        )
        if not existing:
            raise
        existing_tx = await session.get(Transaction, existing.transaction_id)
        candidate = DuplicateCandidate(
            public_id=existing_tx.public_id if existing_tx else str(existing.transaction_id),
            status=existing_tx.status if existing_tx else "UNKNOWN",
            revision=existing.revision,
            same_content=existing.content_fingerprint == fingerprint,
            completed=bool(existing_tx and existing_tx.status == "COMPLETED"),
        )
        raise BusinessOrderConflict(normalized_po=normalized_po, candidates=[candidate]) from None

    return identity


async def transaction_business_identity(session: AsyncSession, transaction_id: UUID) -> BusinessOrderIdentity | None:
    return await session.scalar(
        select(BusinessOrderIdentity).where(BusinessOrderIdentity.transaction_id == transaction_id)
    )


async def duplicate_history(session: AsyncSession, *, transaction: Transaction) -> dict:
    if not transaction.customer_id or not transaction.customer_reference:
        return {"business_identity": None, "related_transactions": []}
    normalized_po = normalize_po_number(transaction.customer_reference)
    identity = await transaction_business_identity(session, transaction.id)
    rows = (
        await session.execute(
            select(Transaction)
            .where(Transaction.customer_id == transaction.customer_id)
            .order_by(Transaction.created_at.asc())
        )
    ).scalars().all()
    related = []
    for row in rows:
        if row.customer_reference and normalize_po_number(row.customer_reference) == normalized_po:
            row_identity = await transaction_business_identity(session, row.id)
            related.append({
                "public_id": row.public_id,
                "status": row.status,
                "created_at": row.created_at.isoformat(),
                "revision": row_identity.revision if row_identity else None,
                "content_fingerprint": row_identity.content_fingerprint if row_identity else None,
                "is_current": row.id == transaction.id,
            })
    return {
        "business_identity": (
            {
                "normalized_po": identity.normalized_po,
                "revision": identity.revision,
                "content_fingerprint": identity.content_fingerprint,
                "status": identity.status,
            }
            if identity else None
        ),
        "related_transactions": related,
    }
