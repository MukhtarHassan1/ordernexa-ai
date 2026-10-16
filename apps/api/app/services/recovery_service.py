import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.digital_twin import (
    Checkpoint,
    Incident,
    IntegrationCommand,
)
from app.models.enums import (
    TransactionStatus,
)
from app.models.transaction import (
    Transaction,
)
from app.schemas.execution import (
    DownstreamExecutionResponse,
    RecoveryResponse,
)
from app.schemas.transaction import (
    TransactionAdvance,
)
from app.services.object_storage import (
    object_storage,
)
from app.services.transaction_service import (
    advance_transaction,
)


async def _get_erp_external_id(
    session: AsyncSession,
    transaction_id,
) -> tuple[str, dict]:
    command = await session.scalar(
        select(IntegrationCommand)
        .where(
            IntegrationCommand
            .transaction_id
            == transaction_id,
            IntegrationCommand.provider
            == "ODOO",
            IntegrationCommand.action
            == "CREATE_SALE_ORDER",
            IntegrationCommand.status
            == "VERIFIED",
        )
        .order_by(
            IntegrationCommand
            .created_at
            .desc()
        )
        .limit(1)
    )

    if (
        command is None
        or not command.external_id
    ):
        raise ValueError(
            "Verified ERP order "
            "does not exist."
        )

    return (
        command.external_id,
        command.response_payload,
    )


async def archive_and_complete(
    session: AsyncSession,
    *,
    public_id: str,
    simulate_failure: bool = False,
) -> DownstreamExecutionResponse:
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

    if transaction.status not in {
        TransactionStatus
        .ERP_CREATED
        .value,
        TransactionStatus
        .RECOVERY_PENDING
        .value,
    }:
        raise ValueError(
            "Transaction must be "
            "ERP_CREATED or RECOVERY_PENDING."
        )

    (
        external_id,
        external_payload,
    ) = await _get_erp_external_id(
        session,
        transaction.id,
    )

    idempotency_key = (
        "document-store:"
        "archive-confirmation:"
        f"{transaction.public_id}"
    )

    command = await session.scalar(
        select(IntegrationCommand)
        .where(
            IntegrationCommand
            .idempotency_key
            == idempotency_key
        )
    )

    if command is None:
        command = IntegrationCommand(
            transaction_id=(
                transaction.id
            ),
            provider="MINIO_LOCAL",
            action=(
                "ARCHIVE_CONFIRMATION"
            ),
            action_id=uuid4().hex,
            idempotency_key=(
                idempotency_key
            ),
            status="PENDING",
            request_payload={},
            response_payload={},
            attempt_count=0,
        )

        session.add(command)

    command.attempt_count += 1
    command.status = "PENDING"

    confirmation = {
        "transaction_id": (
            transaction.public_id
        ),
        "customer_reference": (
            transaction
            .customer_reference
        ),
        "value": str(
            transaction.value
        ),
        "currency": (
            transaction.currency
        ),
        "erp": {
            "provider": "ODOO",
            "external_id": (
                external_id
            ),
            "external_order": (
                external_payload
                .get("name")
            ),
        },
        "generated_at": (
            datetime.now(UTC)
            .isoformat()
        ),
    }

    object_key = (
        f"transactions/"
        f"{transaction.public_id}/"
        f"confirmation.json"
    )

    command.request_payload = {
        "object_key": object_key,
        "confirmation": (
            confirmation
        ),
    }

    await session.commit()

    archive_error_code = None
    if not simulate_failure:
        try:
            if await object_storage.exists(object_key):
                # If the first attempt stored the document but its response was
                # lost, verify the SAME object rather than write another one.
                stored = json.loads((await object_storage.get_bytes(object_key)).decode("utf-8"))
                if stored.get("transaction_id") != transaction.public_id or str(
                    stored.get("erp", {}).get("external_id")
                ) != str(external_id):
                    raise ValueError("Existing archive conflicts with the verified ERP order.")
            else:
                await object_storage.put_json(object_key=object_key, payload=confirmation)
                stored = json.loads((await object_storage.get_bytes(object_key)).decode("utf-8"))
                if stored.get("transaction_id") != transaction.public_id or str(
                    stored.get("erp", {}).get("external_id")
                ) != str(external_id):
                    raise ValueError("Archive read-after-write verification failed.")
        except Exception as exc:
            archive_error_code = type(exc).__name__
            simulate_failure = True

    if simulate_failure:
        command.status = (
            "FAILED_RETRYABLE"
        )

        command.last_error = archive_error_code or "SIMULATED_DOCUMENT_ARCHIVE_FAILURE"

        incident = Incident(
            transaction_id=(
                transaction.id
            ),
            category=(
                "DOCUMENT_ARCHIVE"
            ),
            severity="HIGH",
            status="OPEN",
            error_class=(archive_error_code or "SIMULATED_DEPENDENCY_FAILURE"),
            message="ERP order exists, but document archival was not verified.",
            context_data={
                "erp_external_id": (
                    external_id
                ),
                "archive_object_key": (
                    object_key
                ),
                "duplicate_risk": (
                    "Do not rerun ERP "
                    "creation."
                ),
            },
            resolution={},
        )

        session.add(incident)

        await session.commit()
        await session.refresh(incident)

        transaction = (
            await advance_transaction(
                session,
                transaction,
                TransactionAdvance(
                    target_status=(
                        TransactionStatus
                        .DEGRADED
                        .value
                    ),
                    event_type=(
                        "DOWNSTREAM_ARCHIVE_FAILED"
                    ),
                    payload={
                        "incident_id": str(
                            incident.id
                        ),
                        "erp_external_id": (
                            external_id
                        ),
                        "resume_from": (
                            "DOCUMENT_ARCHIVE"
                        ),
                    },
                ),
            )
        )

        return (
            DownstreamExecutionResponse(
                public_id=(
                    transaction.public_id
                ),
                status=(
                    transaction.status
                ),
                archive_object_key=None,
                incident_id=(
                    incident.id
                ),
                message=(
                    "ERP order was preserved. "
                    "Transaction is DEGRADED "
                    "and can be safely recovered."
                ),
            )
        )

    # Archive exists AND its transaction and ERP identifiers match.
    command.status = "VERIFIED"

    command.response_payload = {
        "object_key": object_key,
        "provider": "MINIO_LOCAL",
    }

    command.verified_at = (
        datetime.now(UTC)
    )

    command.last_error = None

    checkpoint = Checkpoint(
        transaction_id=transaction.id,
        step="DOCUMENT_ARCHIVED",
        status="VERIFIED",
        data={
            "object_key": object_key,
        },
        side_effects=[
            {
                "provider": (
                    "MINIO_LOCAL"
                ),
                "action": (
                    "ARCHIVE_CONFIRMATION"
                ),
                "object_key": (
                    object_key
                ),
                "verified": True,
            }
        ],
        verified=True,
    )

    session.add(checkpoint)

    open_incidents_result = (
        await session.execute(
            select(Incident)
            .where(
                Incident.transaction_id
                == transaction.id,
                Incident.status == "OPEN",
                Incident.category
                == "DOCUMENT_ARCHIVE",
            )
        )
    )

    open_incidents = list(
        open_incidents_result
        .scalars()
        .all()
    )

    for incident in open_incidents:
        incident.status = "RESOLVED"

        incident.resolved_at = (
            datetime.now(UTC)
        )

        incident.resolution = {
            "action": (
                "RETRIED_DOCUMENT_ARCHIVE"
            ),
            "object_key": (
                object_key
            ),
            "erp_replayed": False,
        }

    await session.commit()

    transaction = (
        await advance_transaction(
            session,
            transaction,
            TransactionAdvance(
                target_status=(
                    TransactionStatus
                    .DOWNSTREAM_SYNC
                    .value
                ),
                event_type=(
                    "DOCUMENT_ARCHIVE_VERIFIED"
                ),
                payload={
                    "object_key": (
                        object_key
                    ),
                    "erp_external_id": (
                        external_id
                    ),
                },
            ),
        )
    )

    transaction = (
        await advance_transaction(
            session,
            transaction,
            TransactionAdvance(
                target_status=(
                    TransactionStatus
                    .VERIFIED
                    .value
                ),
                event_type=(
                    "TRANSACTION_VERIFIED"
                ),
                payload={
                    "erp_verified": True,
                    "archive_verified": True,
                },
            ),
        )
    )

    transaction = (
        await advance_transaction(
            session,
            transaction,
            TransactionAdvance(
                target_status=(
                    TransactionStatus
                    .COMPLETED
                    .value
                ),
                event_type=(
                    "TRANSACTION_COMPLETED"
                ),
                payload={},
            ),
        )
    )

    return DownstreamExecutionResponse(
        public_id=transaction.public_id,
        status=transaction.status,
        archive_object_key=(
            object_key
        ),
        incident_id=None,
        message=(
            "Local verification complete: verified Odoo order and "
            "MinIO archive. CRM/Microsoft/Outlook are not asserted."
        ),
    )


async def recover_downstream(
    session: AsyncSession,
    *,
    public_id: str,
) -> RecoveryResponse:
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

    if (
        transaction.status
        != TransactionStatus
        .DEGRADED
        .value
    ):
        raise ValueError(
            "Only DEGRADED transactions "
            "can enter this recovery path."
        )

    transaction = (
        await advance_transaction(
            session,
            transaction,
            TransactionAdvance(
                target_status=(
                    TransactionStatus
                    .RECOVERY_PENDING
                    .value
                ),
                event_type=(
                    "RECOVERY_STARTED"
                ),
                payload={
                    "resume_from": (
                        "DOCUMENT_ARCHIVE"
                    ),
                    "erp_reexecution": (
                        False
                    ),
                },
            ),
        )
    )

    result = await archive_and_complete(
        session,
        public_id=public_id,
        simulate_failure=False,
    )

    return RecoveryResponse(
        public_id=result.public_id,
        status=result.status,
        archive_object_key=(
            result.archive_object_key
            or ""
        ),
        message=(
            "Recovery completed from "
            "the downstream checkpoint "
            "without recreating the ERP order."
        ),
    )
async def recovery_plan(
    session: AsyncSession,
    *,
    public_id: str,
) -> dict:
    """Explain a recovery before any repair write is attempted.

    The plan is derived only from durable transaction/checkpoint/command state.
    It never assumes a failed remote POST did or did not commit.
    """
    transaction = await session.scalar(
        select(Transaction).where(Transaction.public_id == public_id)
    )
    if transaction is None:
        raise LookupError("Transaction not found.")

    commands = list((await session.execute(
        select(IntegrationCommand)
        .where(IntegrationCommand.transaction_id == transaction.id)
        .order_by(IntegrationCommand.created_at)
    )).scalars().all())
    checkpoints = list((await session.execute(
        select(Checkpoint)
        .where(Checkpoint.transaction_id == transaction.id)
        .order_by(Checkpoint.created_at)
    )).scalars().all())
    incidents = list((await session.execute(
        select(Incident)
        .where(Incident.transaction_id == transaction.id)
        .order_by(Incident.created_at)
    )).scalars().all())

    protected: list[dict] = []
    uncertain: list[dict] = []
    failed: list[dict] = []
    for command in commands:
        item = {
            "provider": command.provider,
            "action": command.action,
            "status": command.status,
            "external_id": command.external_id,
            "idempotency_key": command.idempotency_key,
            "error_category": command.error_category,
        }
        if command.status == "VERIFIED" and command.external_id:
            protected.append(item)
        elif command.status == "BLOCKED_UNCERTAIN" or command.error_category == "UNCERTAIN_REMOTE_STATE":
            uncertain.append(item)
        elif command.status in {"FAILED_RETRYABLE", "FAILED_MANUAL", "BLOCKED_CONFIG"}:
            failed.append(item)

    erp_verified = any(
        item["provider"] == "ODOO" and item["action"] == "CREATE_SALE_ORDER"
        for item in protected
    )
    archive_verified = any(
        item["action"] in {"ARCHIVE_CONFIRMATION", "ARCHIVE_SHAREPOINT"}
        for item in protected
    )

    if uncertain:
        recommendation = "RECONCILE_REMOTE_STATE_FIRST"
        safe_to_execute = False
        repeatable_steps: list[str] = []
    elif transaction.status == TransactionStatus.DEGRADED.value and erp_verified and not archive_verified:
        recommendation = "RESUME_DOWNSTREAM_ONLY"
        safe_to_execute = True
        repeatable_steps = ["DOCUMENT_ARCHIVE", "DOWNSTREAM_SYNC", "FINAL_VERIFICATION"]
    elif transaction.status == TransactionStatus.BLOCKED_UNCERTAIN.value:
        recommendation = "RECONCILE_REMOTE_STATE_FIRST"
        safe_to_execute = False
        repeatable_steps = []
    else:
        recommendation = "NO_AUTOMATIC_RECOVERY_PATH"
        safe_to_execute = False
        repeatable_steps = []

    import hashlib
    plan_core = {
        "public_id": transaction.public_id,
        "current_status": transaction.status,
        "recommendation": recommendation,
        "safe_to_execute": safe_to_execute,
        "repeatable_steps": repeatable_steps,
        "protected_committed_side_effects": protected,
        "uncertain_remote_effects": uncertain,
        "failed_or_blocked_commands": failed,
        "verified_checkpoints": [
            {"step": c.step, "status": c.status, "verified": c.verified}
            for c in checkpoints if c.verified
        ],
        "open_incidents": [
            {
                "id": str(i.id),
                "category": i.category,
                "severity": i.severity,
                "error_class": i.error_class,
                "message": i.message,
            }
            for i in incidents if i.status == "OPEN"
        ],
        "duplicate_safety": {
            "erp_reexecution_allowed": False if erp_verified else None,
            "reason": (
                "A verified ERP order is protected and must never be recreated during downstream recovery."
                if erp_verified else
                "No verified ERP order is recorded; ERP-specific retry must use its original idempotency key and reconciliation path."
            ),
        },
    }
    canonical = json.dumps(plan_core, sort_keys=True, separators=(",", ":"), default=str).encode()
    plan_core["plan_sha256"] = hashlib.sha256(canonical).hexdigest()
    return plan_core
