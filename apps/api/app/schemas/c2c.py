from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.schemas.transaction import TransactionRead


class ManualOrderLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_number: int = Field(ge=1)
    product_term: str = Field(min_length=1, max_length=250)
    quantity: Decimal = Field(gt=0)
    uom: str = Field(default="EA", min_length=1, max_length=20)
    requested_unit_price: Decimal | None = Field(
        default=None,
        ge=0,
    )


class ManualOrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    po_number: str = Field(min_length=1, max_length=100)

    customer_hint: str = Field(
        min_length=2,
        max_length=200,
    )

    customer_code: str | None = Field(
        default=None,
        max_length=50,
    )

    customer_domain: str | None = Field(
        default=None,
        max_length=200,
    )

    currency: str = Field(
        default="GBP",
        min_length=3,
        max_length=3,
    )

    delivery_warehouse_code: str = Field(
        default="MAN",
        min_length=2,
        max_length=30,
    )

    requested_delivery_date: date | None = None

    # Business revision is explicit. Ordinary purchase orders are revision 1.
    # A higher revision must reference the exact prior OrderNexa transaction.
    order_revision: int = Field(default=1, ge=1, le=999)
    amendment_of_public_id: str | None = Field(
        default=None, pattern=r"^TXN-[0-9]{4}-[0-9]{6}$"
    )

    lines: list[ManualOrderLineInput] = Field(
        min_length=1,
        max_length=100,
    )

    @model_validator(mode="after")
    def validate_unique_line_numbers(self):
        numbers = [line.line_number for line in self.lines]

        if len(numbers) != len(set(numbers)):
            raise ValueError(
                "Each line_number must be unique."
            )

        return self


class CustomerResolutionResult(BaseModel):
    customer_id: UUID
    code: str
    name: str
    confidence: Decimal
    method: str


class FulfillmentAllocation(BaseModel):
    warehouse_code: str
    warehouse_name: str
    quantity: Decimal


class LineValidationResult(BaseModel):
    line_number: int

    requested_product_term: str

    resolved_product_id: UUID
    resolved_sku: str
    resolved_name: str

    resolution_confidence: Decimal
    resolution_method: str

    quantity: Decimal

    requested_unit_price: Decimal | None
    executable_unit_price: Decimal
    line_total: Decimal

    pricing_exception: bool

    fulfillment_status: str
    fulfillment_exception: bool

    allocations: list[FulfillmentAllocation]


class CreditValidationResult(BaseModel):
    credit_limit: Decimal
    current_exposure: Decimal
    order_value: Decimal
    projected_exposure: Decimal
    over_limit_by: Decimal
    requires_approval: bool


class PolicyResult(BaseModel):
    outcome: str
    reasons: list[str]
    required_approvers: list[str]


class ManualOrderValidationResponse(BaseModel):
    transaction_id: UUID
    public_id: str
    correlation_id: str

    po_number: str

    status: str
    risk: str

    value: Decimal
    currency: str

    customer: CustomerResolutionResult

    lines: list[LineValidationResult]

    credit: CreditValidationResult

    policy: PolicyResult


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    evidence_type: str
    source_type: str
    source_ref: str
    label: str
    excerpt: str | None
    confidence: Decimal | None
    effective_from: date | None
    effective_to: date | None
    details: dict
    created_at: datetime


class OrderLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    line_number: int
    requested_product_term: str
    resolved_product_id: UUID | None
    quantity: Decimal
    uom: str
    requested_unit_price: Decimal | None
    executable_unit_price: Decimal | None
    line_total: Decimal | None
    resolution_confidence: Decimal | None
    resolution_method: str | None
    status: str
    fulfillment_status: str | None
    fulfillment_plan: list[dict]


class PolicyDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_name: str
    policy_version: str
    outcome: str
    reasons: list[str]
    required_approvers: list[str]
    inputs: dict
    created_at: datetime


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reason: str
    approver_role: str
    status: str
    decided_by: str | None
    decision_at: datetime | None
    decision_payload: dict
    created_at: datetime


class CheckpointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    step: str
    status: str
    data: dict
    side_effects: list
    verified: bool
    created_at: datetime


class TransactionDetailResponse(BaseModel):
    transaction: TransactionRead
    lines: list[OrderLineRead]
    evidence: list[EvidenceRead]
    policy_decisions: list[PolicyDecisionRead]
    approvals: list[ApprovalRead]
    checkpoints: list[CheckpointRead]