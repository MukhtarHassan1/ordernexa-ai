from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TransactionCreate(BaseModel):
    source: str = Field(
        min_length=2,
        max_length=50,
        examples=["EMAIL"],
    )

    intent: str | None = Field(
        default=None,
        max_length=100,
        examples=["PURCHASE_ORDER"],
    )

    currency: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
    )

    value: Decimal | None = Field(
        default=None,
        ge=0,
    )


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    public_id: str
    source: str
    intent: str | None
    customer_id: UUID | None
    value: Decimal | None
    currency: str
    status: str
    risk: str
    autonomy_level: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class TransactionAdvance(BaseModel):
    target_status: str
    event_type: str
    actor_type: str = "SYSTEM"
    actor_id: str | None = None
    payload: dict = Field(default_factory=dict)


class TransactionEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID
    step: str
    actor_type: str
    actor_id: str | None
    event_type: str
    payload: dict
    payload_hash: str | None
    trace_id: str | None
    created_at: datetime