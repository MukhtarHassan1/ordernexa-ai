"""Durable work and voice-review records; transaction state remains in core DB."""
from datetime import UTC, datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class AutomationJob(Base):
    __tablename__ = "automation_jobs"
    __table_args__ = (
        Index("ix_automation_claim", "status", "next_attempt_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    transaction_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(45), nullable=False, index=True)
    # Separate source-scoped delivery key. No duplicates even after process restarts.
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(35), nullable=False, default="PENDING", index=True)
    # Metadata and verified destinations only: never persist API tokens or raw message content here.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(250))
    requested_by: Mapped[str] = mapped_column(String(120), nullable=False, default="SYSTEM")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VoiceChangeRequest(Base):
    """Customer voice requests are never direct order amendments."""
    __tablename__ = "voice_change_requests"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    transaction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    request_type: Mapped[str] = mapped_column(String(40), nullable=False)
    # Never accept bank-detail changes or AI-generated executable fields.
    request_note: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING_VERIFICATION")
    external_call_id: Mapped[str] = mapped_column(String(180), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(120))
    review_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
