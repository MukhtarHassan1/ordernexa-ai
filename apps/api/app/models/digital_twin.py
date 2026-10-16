from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    code: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    normalized_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
    )

    primary_domain: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        index=True,
    )

    credit_limit: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=0,
    )

    current_exposure: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=0,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="GBP",
    )

    tier: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="STANDARD",
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="ACTIVE",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CustomerExternalRef(Base):
    __tablename__ = "customer_external_refs"

    __table_args__ = (
        UniqueConstraint(
            "system",
            "external_id",
            name="uq_customer_external_ref_system_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    system: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    external_id: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    extra_data: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    sku: Mapped[str] = mapped_column(
        String(60),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
    )

    normalized_name: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        index=True,
    )

    catalog_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="GBP",
    )

    uom: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="EA",
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ProductAlias(Base):
    __tablename__ = "product_aliases"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    customer_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    alias: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
    )

    normalized_alias: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        index=True,
    )

    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="CATALOG",
    )

    valid_from: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    valid_to: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    code: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    country: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
    )

    priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )


class Inventory(Base):
    __tablename__ = "inventory"

    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "warehouse_id",
            name="uq_inventory_product_warehouse",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    warehouse_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    on_hand: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        nullable=False,
        default=0,
    )

    reserved: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        nullable=False,
        default=0,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SourceArtifact(Base):
    __tablename__ = "source_artifacts"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    transaction_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    artifact_type: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
    )

    original_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    mime_type: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )

    storage_provider: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="INLINE",
    )

    bucket: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    object_key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )

    source_ref: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
    )

    extra_data: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    code: Mapped[str] = mapped_column(
        String(60),
        unique=True,
        nullable=False,
        index=True,
    )

    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_artifact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("source_artifacts.id", ondelete="SET NULL"),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="ACTIVE",
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="GBP",
    )

    valid_from: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    valid_to: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    payment_terms: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ContractPrice(Base):
    __tablename__ = "contract_prices"

    __table_args__ = (
        UniqueConstraint(
            "contract_id",
            "product_id",
            "min_quantity",
            name="uq_contract_price_product_qty",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    contract_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("contracts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )

    min_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        nullable=False,
        default=1,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class HistoricalOrder(Base):
    __tablename__ = "historical_orders"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    order_number: Mapped[str] = mapped_column(
        String(80),
        unique=True,
        nullable=False,
        index=True,
    )

    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    ordered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="GBP",
    )

    total: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
        default=0,
    )

    external_system: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    external_id: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )


class HistoricalOrderLine(Base):
    __tablename__ = "historical_order_lines"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    historical_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("historical_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    line_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    description: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
    )

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        nullable=False,
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        nullable=False,
    )


class OrderLine(Base):
    __tablename__ = "order_lines"

    __table_args__ = (
        UniqueConstraint(
            "transaction_id",
            "line_number",
            name="uq_order_line_transaction_line",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    line_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    requested_product_term: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
    )

    resolved_product_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 3),
        nullable=False,
    )

    uom: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="EA",
    )

    requested_unit_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )

    executable_unit_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )

    line_total: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )

    resolution_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )

    resolution_method: Mapped[str | None] = mapped_column(
        String(60),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="EXTRACTED",
    )

    fulfillment_status: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    fulfillment_plan: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    order_line_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("order_lines.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    evidence_type: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
        index=True,
    )

    source_type: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
    )

    source_ref: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
    )

    label: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
    )

    excerpt: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )

    effective_from: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    effective_to: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    details: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AIDecision(Base):
    __tablename__ = "ai_decisions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    order_line_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("order_lines.id", ondelete="CASCADE"),
        nullable=True,
    )

    decision_type: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        index=True,
    )

    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    prompt_version: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    input_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    output_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )

    validation_result: Mapped[str | None] = mapped_column(
        String(60),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="RECORDED",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class PolicyDecision(Base):
    __tablename__ = "policy_decisions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    policy_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    policy_version: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    outcome: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )

    reasons: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )

    required_approvers: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )

    inputs: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    policy_decision_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("policy_decisions.id", ondelete="SET NULL"),
        nullable=True,
    )

    reason: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    approver_role: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PENDING",
        index=True,
    )

    decided_by: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    decision_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    decision_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class IntegrationCommand(Base):
    __tablename__ = "integration_commands"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
    )

    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    action_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(200),
        unique=True,
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="PENDING",
        index=True,
    )

    request_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    response_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    external_id: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
        index=True,
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    error_category: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True,
    )

    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Checkpoint(Base):
    __tablename__ = "checkpoints"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    step: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    side_effects: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )

    verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    category: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
    )

    severity: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="OPEN",
        index=True,
    )

    error_class: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    context_data: Mapped[dict] = mapped_column(
        "context",
        JSONB,
        nullable=False,
        default=dict,
    )

    resolution: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

class BusinessOrderIdentity(Base):
    """Atomic business-level claim for one customer PO revision.

    Transaction IDs remain useful for technical idempotency, while this record
    prevents two independent transactions from representing the same business
    order revision and independently writing to the ERP.
    """
    __tablename__ = "business_order_identities"
    __table_args__ = (
        UniqueConstraint(
            "customer_id", "normalized_po", "revision",
            name="uq_business_order_customer_po_revision",
        ),
        Index("ix_business_order_lookup", "customer_id", "normalized_po"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id", ondelete="RESTRICT"),
        nullable=False, unique=True,
    )
    normalized_po: Mapped[str] = mapped_column(String(120), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    amendment_of_transaction_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id", ondelete="RESTRICT"),
        nullable=True, index=True,
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IntegrationCircuit(Base):
    """Persisted circuit-breaker state shared by worker processes."""
    __tablename__ = "integration_circuits"

    provider: Mapped[str] = mapped_column(String(60), primary_key=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="CLOSED")
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    half_open_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ExternalSubscription(Base):
    """Durable metadata for renewable external subscriptions (Graph in V1)."""
    __tablename__ = "external_subscriptions"
    __table_args__ = (UniqueConstraint("provider", "subscription_id", name="uq_external_subscription_provider_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    subscription_id: Mapped[str] = mapped_column(String(180), nullable=False)
    resource: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    client_state_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    delta_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    lifecycle_event: Mapped[str | None] = mapped_column(String(60), nullable=True)
    last_renewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_delta_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AutonomyPolicy(Base):
    """Per-action autonomy, never an agent-wide permission."""
    __tablename__ = "autonomy_policies"

    action: Mapped[str] = mapped_column(String(100), primary_key=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False, default="1.0")
    max_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    allowed_risks: Mapped[list] = mapped_column(JSONB, nullable=False, default=lambda: ["LOW"])
    require_verified_evidence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

class PaymentRecord(Base):
    """Verified sandbox payment state; never stores card or bank data."""
    __tablename__ = "payment_records"
    __table_args__ = (
        UniqueConstraint("provider", "external_session_id", name="uq_payment_provider_session"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False, default="STRIPE_SANDBOX")
    external_session_id: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING", index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    checkout_url_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_payment_intent_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

class KnowledgeDocument(Base):
    """Metadata-scoped unstructured knowledge source for retrieval only."""
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        UniqueConstraint("source_system", "source_id", name="uq_knowledge_source"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(250), nullable=False)
    document_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="ACTIVE", index=True)
    extra_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class KnowledgeChunk(Base):
    """Evidence chunk. Content is untrusted DATA and cannot authorize writes."""
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_document_chunk"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str | None] = mapped_column(String(180), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    token_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
