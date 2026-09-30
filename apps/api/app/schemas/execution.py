from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ApprovalDecisionRequest(BaseModel):
    decision: Literal[
        "APPROVE",
        "REJECT",
    ]

    approver_role: str

    actor_id: str

    note: str | None = None


class ApprovalDecisionResponse(BaseModel):
    approval_id: UUID

    approval_status: str

    transaction_public_id: str

    transaction_status: str


class ERPExecutionResponse(BaseModel):
    public_id: str

    idempotency_key: str

    external_id: str

    external_order_name: str

    external_state: str

    replayed: bool


class DownstreamExecutionRequest(
    BaseModel
):
    simulate_failure: bool = False


class DownstreamExecutionResponse(
    BaseModel
):
    public_id: str

    status: str

    archive_object_key: str | None = None

    incident_id: UUID | None = None

    message: str


class RecoveryResponse(BaseModel):
    public_id: str

    status: str

    archive_object_key: str

    message: str