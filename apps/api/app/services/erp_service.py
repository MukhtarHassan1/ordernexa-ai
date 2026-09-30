import json
import hashlib
from datetime import UTC, datetime
from urllib.parse import quote
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.digital_twin import (
    Checkpoint,
    Customer,
    IntegrationCommand,
    OrderLine,
    Product,
)
from app.models.enums import (
    TransactionStatus,
)
from app.models.transaction import (
    Transaction,
)
from app.schemas.execution import (
    ERPExecutionResponse,
)
from app.schemas.transaction import (
    TransactionAdvance,
)
from app.services.transaction_service import (
    advance_transaction,
)


class ERPExecutionError(Exception):
    pass


async def execute_erp_order(
    session: AsyncSession,
    *,
    public_id: str,
) -> ERPExecutionResponse:
    transaction = await session.scalar(
        select(Transaction)
        .where(
            Transaction.public_id
            == public_id
        )
        .with_for_update()
    )

    if transaction is None:
        raise LookupError(
            "Transaction not found."
        )

    idempotency_key = (
        f"odoo:create-sales-order:"
        f"{transaction.public_id}"
    )

    existing_command = await session.scalar(
        select(IntegrationCommand)
        .where(
            IntegrationCommand
            .idempotency_key
            == idempotency_key
        )
    )

    if (
        existing_command
        and existing_command.status
        == "VERIFIED"
        and existing_command.external_id
    ):
        payload = (
            existing_command
            .response_payload
            or {}
        )

        return ERPExecutionResponse(
            public_id=(
                transaction.public_id
            ),
            idempotency_key=(
                idempotency_key
            ),
            external_id=(
                existing_command
                .external_id
            ),
            external_order_name=(
                payload.get(
                    "name",
                    existing_command
                    .external_id,
                )
            ),
            external_state=(
                payload.get(
                    "state",
                    "unknown",
                )
            ),
            replayed=True,
        )

    if transaction.status not in {
        TransactionStatus.READY.value,
        TransactionStatus.ERP_PENDING.value,
    }:
        raise ValueError(
            "Transaction must be READY "
            "before ERP execution."
        )

    customer = await session.get(
        Customer,
        transaction.customer_id,
    )

    if customer is None:
        raise ERPExecutionError(
            "Resolved customer is missing."
        )

    line_result = await session.execute(
        select(
            OrderLine,
            Product,
        )
        .join(
            Product,
            Product.id
            == OrderLine
            .resolved_product_id,
        )
        .where(
            OrderLine.transaction_id
            == transaction.id
        )
        .order_by(
            OrderLine.line_number
        )
    )

    rows = list(line_result.all())

    if not rows:
        raise ERPExecutionError(
            "Transaction contains no "
            "resolved order lines."
        )

    request_payload = {
        "transaction_id": (
            transaction.public_id
        ),
        "idempotency_key": (
            idempotency_key
        ),
        "po_number": (
            transaction
            .customer_reference
        ),
        "customer_code": (
            customer.code
        ),
        "customer_name": (
            customer.name
        ),
        "currency": (
            transaction.currency
        ),
        "lines": [
            {
                "line_number": (
                    line.line_number
                ),
                "sku": product.sku,
                "quantity": str(
                    line.quantity
                ),
                "unit_price": str(
                    line
                    .executable_unit_price
                ),
            }
            for line, product in rows
        ],
    }

    # A failed/uncertain external response MUST NOT permit a different payload to
    # reuse the original idempotency key. Human edits require a new controlled action.
    if existing_command is not None and existing_command.request_payload:
        prior_hash = hashlib.sha256(json.dumps(existing_command.request_payload, sort_keys=True).encode()).hexdigest()
        new_hash = hashlib.sha256(json.dumps(request_payload, sort_keys=True).encode()).hexdigest()
        if prior_hash != new_hash:
            raise ValueError("ERP payload changed since the first attempt. Review before any replay.")

    is_uncertain_replay = existing_command is not None and existing_command.attempt_count > 0

    if existing_command is None:
        command = IntegrationCommand(
            transaction_id=(
                transaction.id
            ),
            provider="ODOO",
            action="CREATE_SALE_ORDER",
            action_id=uuid4().hex,
            idempotency_key=(
                idempotency_key
            ),
            status="PENDING",
            request_payload=(
                request_payload
            ),
            response_payload={},
            attempt_count=0,
        )

        session.add(command)

    else:
        command = existing_command
        command.status = "PENDING"
        command.request_payload = (
            request_payload
        )

    command.attempt_count += 1

    await session.flush()

    if (
        transaction.status
        == TransactionStatus.READY.value
    ):
        transaction = (
            await advance_transaction(
                session,
                transaction,
                TransactionAdvance(
                    target_status=(
                        TransactionStatus
                        .ERP_PENDING
                        .value
                    ),
                    event_type=(
                        "ERP_COMMAND_PERSISTED"
                    ),
                    payload={
                        "idempotency_key": (
                            idempotency_key
                        ),
                    },
                ),
            )
        )

    else:
        await session.commit()

    headers = {
        "X-OrderNexa-Key": (
            settings
            .ordernexa_odoo_shared_secret
        ),
        "Content-Type": (
            "application/json"
        ),
    }

    timeout = httpx.Timeout(30)

    try:
        async with httpx.AsyncClient(
            timeout=timeout
        ) as client:
            verify_url = (settings.odoo_base_url.rstrip("/")
                          + "/ordernexa/api/sales-order/"
                          + quote(idempotency_key, safe=""))

            # An earlier POST may have succeeded even when its HTTP response was
            # lost. Read-before-replay is mandatory; an existing order is never
            # re-created just because the local transaction saw a timeout.
            verified = None
            if is_uncertain_replay:
                check = await client.get(verify_url, headers=headers)
                if check.status_code == 200:
                    verified = check.json()
                elif check.status_code != 404:
                    check.raise_for_status()

            if verified is not None:
                external = {**verified, "replayed": True}
            else:
                response = await client.post(
                    settings.odoo_base_url.rstrip("/") + "/ordernexa/api/sales-order",
                    headers=headers, json=request_payload,
                )
                response.raise_for_status()
                external = response.json()
                verify = await client.get(verify_url, headers=headers)
                verify.raise_for_status()
                verified = verify.json()

            if str(verified.get("id", "")) == "" or verified.get("state") not in {"sale", "done"}:
                raise ERPExecutionError("ERP order did not pass read-after-write confirmation.")

    except Exception as exc:
        # A 401/403/422 is not transient and must not enter automatic replay.
        permanent = isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {400, 401, 403, 409, 422}
        command.status = "FAILED_MANUAL" if permanent else "FAILED_RETRYABLE"
        command.last_error = type(exc).__name__

        await session.commit()

        if (
            transaction.status
            == TransactionStatus
            .ERP_PENDING
            .value
        ):
            await advance_transaction(
                session,
                transaction,
                TransactionAdvance(
                    target_status=(
                        (TransactionStatus.FAILED_MANUAL if permanent
                         else TransactionStatus.FAILED_RETRYABLE).value
                    ),
                    event_type=(
                        "ERP_EXECUTION_FAILED"
                    ),
                    payload={
                        "error_class": type(exc).__name__,
                        "idempotency_key": (
                            idempotency_key
                        ),
                    },
                ),
            )

        raise ERPExecutionError("ERP verification or transport failed; review command status and logs.") from exc

    command.status = "VERIFIED"

    command.external_id = str(
        verified["id"]
    )

    command.response_payload = {
        **external,
        "verification": verified,
    }

    command.verified_at = (
        datetime.now(UTC)
    )

    command.last_error = None

    checkpoint = Checkpoint(
        transaction_id=transaction.id,
        step="ERP_ORDER_CREATED",
        status="VERIFIED",
        data={
            "provider": "ODOO",
            "external_id": str(
                verified["id"]
            ),
            "external_order_name": (
                verified["name"]
            ),
            "idempotency_key": (
                idempotency_key
            ),
        },
        side_effects=[
            {
                "provider": "ODOO",
                "action": (
                    "CREATE_SALE_ORDER"
                ),
                "external_id": str(
                    verified["id"]
                ),
                "verified": True,
            }
        ],
        verified=True,
    )

    session.add(checkpoint)

    await session.commit()

    transaction = (
        await advance_transaction(
            session,
            transaction,
            TransactionAdvance(
                target_status=(
                    TransactionStatus
                    .ERP_CREATED
                    .value
                ),
                event_type=(
                    "ERP_ORDER_VERIFIED"
                ),
                payload={
                    "external_id": str(
                        verified["id"]
                    ),
                    "external_order_name": (
                        verified["name"]
                    ),
                    "idempotency_key": (
                        idempotency_key
                    ),
                },
            ),
        )
    )

    return ERPExecutionResponse(
        public_id=transaction.public_id,
        idempotency_key=(
            idempotency_key
        ),
        external_id=str(
            verified["id"]
        ),
        external_order_name=(
            verified["name"]
        ),
        external_state=(
            verified["state"]
        ),
        replayed=bool(
            external.get(
                "replayed",
                False,
            )
        ),
    )

async def retry_erp_order(session: AsyncSession, *, public_id: str) -> ERPExecutionResponse:
    """Explicit controlled recovery after a transient/uncertain ERP attempt.

    Uses the same unique idempotency key and GET-before-POST in execute_erp_order.
    Never retries terminal policy/business failures.
    """
    transaction = await session.scalar(
        select(Transaction).where(Transaction.public_id == public_id).with_for_update()
    )
    if transaction is None:
        raise LookupError("Transaction not found.")
    key = f"odoo:create-sales-order:{public_id}"
    command = await session.scalar(
        select(IntegrationCommand).where(IntegrationCommand.idempotency_key == key)
    )
    if not command or command.status != "FAILED_RETRYABLE" or transaction.status != TransactionStatus.FAILED_RETRYABLE.value:
        raise ValueError("Only a matching transient/uncertain ERP failure can use this replay endpoint.")
    transaction = await advance_transaction(session, transaction, TransactionAdvance(
        target_status=TransactionStatus.RECOVERY_PENDING.value,
        event_type="ERP_IDEMPOTENT_REPLAY_REQUESTED", payload={"idempotency_key": key},
    ))
    await advance_transaction(session, transaction, TransactionAdvance(
        target_status=TransactionStatus.ERP_PENDING.value,
        event_type="ERP_RECOVERY_READ_BEFORE_WRITE", payload={"idempotency_key": key},
    ))
    return await execute_erp_order(session, public_id=public_id)
