from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.digital_twin import Approval
from app.models.enums import TransactionStatus
from app.models.transaction import Transaction
from app.schemas.execution import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
)
from app.schemas.transaction import (
    TransactionAdvance,
)
from app.services.transaction_service import (
    advance_transaction,
    append_transaction_event,
)


async def decide_approval(
    session: AsyncSession,
    *,
    approval_id: UUID,
    data: ApprovalDecisionRequest,
) -> ApprovalDecisionResponse:
    approval = await session.scalar(
        select(Approval)
        .where(
            Approval.id == approval_id
        )
        .with_for_update()
    )

    if approval is None:
        raise LookupError(
            "Approval not found."
        )

    transaction = await session.scalar(
        select(Transaction)
        .where(
            Transaction.id
            == approval.transaction_id
        )
        .with_for_update()
    )

    if transaction is None:
        raise LookupError(
            "Transaction not found."
        )

    if (
        data.approver_role
        != approval.approver_role
    ):
        raise PermissionError(
            "Approver role does not match "
            "the required approval role."
        )

    requested_status = (
        "APPROVED"
        if data.decision == "APPROVE"
        else "REJECTED"
    )

    # Idempotent same decision.
    if approval.status == requested_status:
        return ApprovalDecisionResponse(
            approval_id=approval.id,
            approval_status=(
                approval.status
            ),
            transaction_public_id=(
                transaction.public_id
            ),
            transaction_status=(
                transaction.status
            ),
        )

    if approval.status != "PENDING":
        raise ValueError(
            "Approval has already been "
            "decided differently."
        )

    approval.status = requested_status
    approval.decided_by = data.actor_id
    approval.decision_at = (
        datetime.now(UTC)
    )

    approval.decision_payload = {
        "decision": data.decision,
        "role": data.approver_role,
        "note": data.note,
    }

    await append_transaction_event(
        session,
        transaction=transaction,
        step="APPROVAL",
        event_type=(
            f"APPROVAL_{requested_status}"
        ),
        actor_type="HUMAN",
        actor_id=data.actor_id,
        payload={
            "approval_id": str(
                approval.id
            ),
            "approver_role": (
                approval.approver_role
            ),
            "decision": (
                data.decision
            ),
            "note": data.note,
        },
        commit=False,
    )

    if requested_status == "REJECTED":
        transaction = (
            await advance_transaction(
                session,
                transaction,
                TransactionAdvance(
                    target_status=(
                        TransactionStatus
                        .CANCELLED
                        .value
                    ),
                    event_type=(
                        "TRANSACTION_REJECTED"
                    ),
                    actor_type="HUMAN",
                    actor_id=data.actor_id,
                    payload={
                        "approval_id": str(
                            approval.id
                        )
                    },
                ),
            )
        )

        return ApprovalDecisionResponse(
            approval_id=approval.id,
            approval_status=(
                approval.status
            ),
            transaction_public_id=(
                transaction.public_id
            ),
            transaction_status=(
                transaction.status
            ),
        )

    result = await session.execute(
        select(Approval)
        .where(
            Approval.transaction_id
            == transaction.id
        )
    )

    approvals = list(
        result.scalars().all()
    )

    all_approved = (
        approvals
        and all(
            item.status == "APPROVED"
            for item in approvals
        )
    )

    if (
        all_approved
        and transaction.status
        == TransactionStatus
        .APPROVAL_REQUIRED
        .value
    ):
        transaction = (
            await advance_transaction(
                session,
                transaction,
                TransactionAdvance(
                    target_status=(
                        TransactionStatus
                        .READY
                        .value
                    ),
                    event_type=(
                        "ALL_APPROVALS_GRANTED"
                    ),
                    actor_type="SYSTEM",
                    payload={
                        "approval_count": len(
                            approvals
                        ),
                    },
                ),
            )
        )

    else:
        await session.commit()

    return ApprovalDecisionResponse(
        approval_id=approval.id,
        approval_status=approval.status,
        transaction_public_id=(
            transaction.public_id
        ),
        transaction_status=(
            transaction.status
        ),
    )