"""Policy-bounded Stripe sandbox payment workflow.

Payments are optional V1.5 functionality. The amount/currency always originate
from the stored transaction; AI output and caller-supplied monetary values are
never accepted.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.stripe_sandbox import StripeSandbox, StripeSandboxError, amount_to_minor
from app.models.digital_twin import BusinessOrderIdentity, PaymentRecord
from app.models.transaction import Transaction
from app.services.integration_command_service import begin_external_command, mark_external_command
from app.services.transaction_service import append_transaction_event


ALLOWED_PAYMENT_TRANSACTION_STATES = {"READY", "COMPLETED"}


async def _payment_idempotency_key(session: AsyncSession, transaction: Transaction) -> str:
    identity = await session.scalar(
        select(BusinessOrderIdentity).where(BusinessOrderIdentity.transaction_id == transaction.id)
    )
    if identity:
        business = f"{identity.customer_id}:{identity.normalized_po}:r{identity.revision}"
    else:
        business = transaction.public_id
    fingerprint = hashlib.sha256(
        f"{business}|{transaction.value}|{transaction.currency}".encode("utf-8")
    ).hexdigest()[:32]
    return f"stripe:checkout:{fingerprint}"


async def create_payment_checkout(
    session: AsyncSession,
    *,
    public_id: str,
    actor_id: str,
) -> dict:
    transaction = await session.scalar(
        select(Transaction).where(Transaction.public_id == public_id).with_for_update()
    )
    if transaction is None:
        raise LookupError("Transaction not found.")
    if transaction.status not in ALLOWED_PAYMENT_TRANSACTION_STATES:
        raise ValueError("Payment link can be created only after the transaction is READY or COMPLETED.")
    if Decimal(transaction.value) <= 0:
        raise ValueError("Transaction does not have a positive authoritative value.")

    key = await _payment_idempotency_key(session, transaction)
    expected_minor = amount_to_minor(Decimal(transaction.value), transaction.currency)
    request_summary = {
        "transaction_public_id": transaction.public_id,
        "amount_minor": expected_minor,
        "currency": transaction.currency.upper(),
        "mode": "payment",
    }
    command, already_terminal = await begin_external_command(
        session,
        transaction=transaction,
        provider="STRIPE_SANDBOX",
        action="CREATE_CHECKOUT_SESSION",
        idempotency_key=key,
        request_summary=request_summary,
    )
    if already_terminal and command.external_id:
        record = await session.scalar(
            select(PaymentRecord).where(
                PaymentRecord.provider == "STRIPE_SANDBOX",
                PaymentRecord.external_session_id == command.external_id,
            )
        )
        return {
            "transaction_public_id": transaction.public_id,
            "checkout_session_id": command.external_id,
            "checkout_url": None,
            "status": record.status if record else "CREATED",
            "created": False,
            "message": "Checkout Session already exists. For safety the hosted URL is not persisted; retrieve/inspect it in Stripe test mode if needed.",
        }

    stripe = StripeSandbox()
    try:
        remote = await stripe.create_checkout_session(
            transaction_public_id=transaction.public_id,
            amount=Decimal(transaction.value),
            currency=transaction.currency,
            idempotency_key=key,
        )
    except StripeSandboxError as exc:
        await mark_external_command(
            session,
            command=command,
            status="FAILED_RETRYABLE",
            error_category="TRANSIENT",
            last_error=type(exc).__name__,
            response_summary={"verified": False},
        )
        raise

    record = await session.scalar(
        select(PaymentRecord).where(
            PaymentRecord.provider == "STRIPE_SANDBOX",
            PaymentRecord.external_session_id == remote.session_id,
        )
    )
    if record is None:
        record = PaymentRecord(
            transaction_id=transaction.id,
            provider="STRIPE_SANDBOX",
            external_session_id=remote.session_id,
            status="PENDING",
            amount=Decimal(transaction.value),
            currency=transaction.currency.upper(),
            checkout_url_hash=hashlib.sha256(remote.url.encode("utf-8")).hexdigest(),
            extra_data={"payment_status": remote.payment_status},
        )
        session.add(record)
        await session.flush()
    elif record.transaction_id != transaction.id:
        raise ValueError("Stripe Checkout Session is already linked to a different transaction.")

    await mark_external_command(
        session,
        command=command,
        status="VERIFIED",
        external_id=remote.session_id,
        response_summary={
            "amount_minor": remote.amount_total_minor,
            "currency": remote.currency,
            "payment_status": remote.payment_status,
            "checkout_url_sha256": record.checkout_url_hash,
        },
    )
    await append_transaction_event(
        session,
        transaction=transaction,
        step="PAYMENT",
        event_type="STRIPE_SANDBOX_CHECKOUT_CREATED",
        payload={
            "session_id": remote.session_id,
            "amount_minor": remote.amount_total_minor,
            "currency": remote.currency,
            "actor_id": actor_id,
        },
        actor_type="HUMAN",
        actor_id=actor_id,
    )
    return {
        "transaction_public_id": transaction.public_id,
        "checkout_session_id": remote.session_id,
        "checkout_url": remote.url,
        "status": record.status,
        "created": True,
        "notice": "Stripe test mode only. Amount and currency came from authoritative OrderNexa transaction state.",
    }


async def apply_verified_stripe_event(session: AsyncSession, event: dict) -> dict:
    """Apply a verified Stripe webhook without allowing it to change order authority."""
    event_type = event.get("type")
    if event_type not in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        return {"accepted": True, "action": "IGNORED_EVENT_TYPE"}
    obj = ((event.get("data") or {}).get("object") or {})
    if not isinstance(obj, dict):
        raise ValueError("Stripe event does not contain a Checkout Session object.")
    session_id = obj.get("id")
    public_id = ((obj.get("metadata") or {}).get("transaction_public_id") or obj.get("client_reference_id"))
    if not isinstance(session_id, str) or not session_id.startswith("cs_test_"):
        raise ValueError("Only Stripe test-mode Checkout Session events are accepted.")
    if not isinstance(public_id, str) or not public_id.startswith("TXN-"):
        raise ValueError("Stripe event is missing the OrderNexa transaction reference.")

    transaction = await session.scalar(
        select(Transaction).where(Transaction.public_id == public_id).with_for_update()
    )
    if transaction is None:
        raise LookupError("Stripe event references an unknown OrderNexa transaction.")
    expected_minor = amount_to_minor(Decimal(transaction.value), transaction.currency)
    if int(obj.get("amount_total") or 0) != expected_minor:
        raise ValueError("Stripe amount does not match the authoritative transaction value.")
    if str(obj.get("currency") or "").upper() != transaction.currency.upper():
        raise ValueError("Stripe currency does not match the authoritative transaction currency.")
    if obj.get("payment_status") != "paid":
        return {"accepted": True, "action": "PAYMENT_NOT_PAID", "transaction_public_id": public_id}

    record = await session.scalar(
        select(PaymentRecord).where(
            PaymentRecord.provider == "STRIPE_SANDBOX",
            PaymentRecord.external_session_id == session_id,
        ).with_for_update()
    )
    if record is None:
        # Webhook can arrive after local response loss. Reconstruct only after all
        # authoritative amount/currency/reference checks have passed.
        record = PaymentRecord(
            transaction_id=transaction.id,
            provider="STRIPE_SANDBOX",
            external_session_id=session_id,
            status="PAID",
            amount=Decimal(transaction.value),
            currency=transaction.currency.upper(),
            external_payment_intent_id=str(obj.get("payment_intent")) if obj.get("payment_intent") else None,
            verified_at=datetime.now(UTC),
            extra_data={"last_event_id": event.get("id")},
        )
        session.add(record)
    else:
        if record.transaction_id != transaction.id or Decimal(record.amount) != Decimal(transaction.value) or record.currency.upper() != transaction.currency.upper():
            raise ValueError("Existing payment record conflicts with authoritative transaction state.")
        if record.status == "PAID":
            return {"accepted": True, "action": "ALREADY_VERIFIED", "transaction_public_id": public_id}
        record.status = "PAID"
        record.external_payment_intent_id = str(obj.get("payment_intent")) if obj.get("payment_intent") else None
        record.verified_at = datetime.now(UTC)
        record.extra_data = {**(record.extra_data or {}), "last_event_id": event.get("id")}

    await append_transaction_event(
        session,
        transaction=transaction,
        step="PAYMENT",
        event_type="STRIPE_SANDBOX_PAYMENT_VERIFIED",
        payload={
            "session_id": session_id,
            "amount_minor": expected_minor,
            "currency": transaction.currency.upper(),
            "stripe_event_id": event.get("id"),
        },
        commit=False,
    )
    await session.commit()
    return {"accepted": True, "action": "PAYMENT_VERIFIED", "transaction_public_id": public_id, "status": "PAID"}


async def payment_status(session: AsyncSession, *, public_id: str) -> dict:
    transaction = await session.scalar(select(Transaction).where(Transaction.public_id == public_id))
    if transaction is None:
        raise LookupError("Transaction not found.")
    records = list((await session.execute(
        select(PaymentRecord).where(PaymentRecord.transaction_id == transaction.id).order_by(PaymentRecord.created_at.desc())
    )).scalars().all())
    return {
        "transaction_public_id": public_id,
        "authoritative_amount": str(transaction.value),
        "currency": transaction.currency,
        "items": [
            {
                "provider": r.provider,
                "session_id": r.external_session_id,
                "status": r.status,
                "amount": str(r.amount),
                "currency": r.currency,
                "verified_at": r.verified_at.isoformat() if r.verified_at else None,
            }
            for r in records
        ],
    }
