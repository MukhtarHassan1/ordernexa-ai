"""Auditable document intake with resumable artifacts and AI failure classification.

The original is stored once; if Ollama cannot generate, the file remains available
for retry or an explicitly HUMAN-confirmed deterministic preview. No AI fallback
silently creates an order.
"""
import hashlib
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.digital_twin import AIDecision, SourceArtifact
from app.models.transaction import Transaction
from app.schemas.c2c import ManualOrderInput, ManualOrderLineInput
from app.schemas.intake import IntakeUploadResponse
from app.services.ai_gateway import AIProviderError
from app.services.c2c_validation_service import ResolutionNeedsReview, create_manual_order
from app.services.document_intelligence import (
    DOCUMENT_EXTRACTION_PROMPT_VERSION, SUPPORTED_EXTENSIONS,
    extract_document, extract_order_draft,
)
from app.services.object_storage import object_storage
from app.services.transaction_service import append_transaction_event


class DuplicateDocument(Exception):
    def __init__(self, existing_public_id: str):
        self.existing_public_id = existing_public_id


class ArtifactBusy(Exception):
    def __init__(self, artifact_id: UUID):
        self.artifact_id = artifact_id


class DocumentNeedsReview(Exception):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


def _safe_filename(filename: str) -> str:
    return (re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name)[:180] or "document")


def _warehouse_from_location(location: str | None) -> str | None:
    if not location:
        return None
    name = location.lower()
    return next((code for key, code in (
        ("manchester", "MAN"), ("london", "LON"),
        ("rotterdam", "RTM"), ("netherlands", "RTM"),
    ) if key in name), None)


def _check_extension(filename: str) -> None:
    if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise DocumentNeedsReview("Unsupported document type.", {"accepted_types": sorted(SUPPORTED_EXTENSIONS)})


async def _mark(session: AsyncSession, artifact: SourceArtifact, status: str, **details) -> None:
    artifact.extra_data = {**(artifact.extra_data or {}), "status": status, **details}
    await session.commit()


async def get_original_artifact(session: AsyncSession, artifact_id: UUID) -> SourceArtifact:
    artifact = await session.get(SourceArtifact, artifact_id)
    if not artifact or artifact.artifact_type != "ORIGINAL_DOCUMENT" or artifact.storage_provider != "MINIO":
        raise LookupError("Original source artifact not found.")
    return artifact


async def get_verified_original_bytes(artifact: SourceArtifact) -> bytes:
    """Retrieve saved original and verify its content-addressed integrity.

    This is shared by retry, human preview, and authenticated download so
    none can accidentally use a corrupted or replaced MinIO object.
    """
    if not artifact.object_key or not artifact.sha256:
        raise ValueError("Saved original is missing its object key or checksum.")
    data = await object_storage.get_bytes(artifact.object_key)
    if len(data) > settings.max_upload_bytes:
        raise ValueError("Saved original exceeds the configured upload limit.")
    if hashlib.sha256(data).hexdigest() != artifact.sha256:
        raise ValueError("Saved original checksum mismatch; contact an operator before review.")
    return data


async def _check_duplicate_order(session: AsyncSession, po_number: str, customer_hint: str) -> None:
    # Fail closed on the original PO number when retrying a partly committed intake.
    # The operator can inspect the existing transaction rather than silently create
    # a second potentially consequential order.
    existing = await session.scalar(
        select(Transaction.public_id).where(
            Transaction.customer_reference == po_number,
            Transaction.source.in_(["FILE_UPLOAD", "FILE_UPLOAD_HUMAN_REVIEW"]),
        ).limit(1)
    )
    if existing:
        raise DuplicateDocument(existing)


async def ingest_order_file(
    session: AsyncSession, *, filename: str, content_type: str, data: bytes,
    existing_artifact_id: UUID | None = None,
) -> IntakeUploadResponse:
    safe_name = _safe_filename(filename)
    _check_extension(safe_name)
    if len(data) > settings.max_upload_bytes:
        raise DocumentNeedsReview("File exceeds the configured upload limit.")
    sha = hashlib.sha256(data).hexdigest()
    original = None
    if existing_artifact_id:
        original = await get_original_artifact(session, existing_artifact_id)
        if original.sha256 != sha:
            raise ValueError("Saved artifact checksum mismatch; refusing to process modified bytes.")
    else:
        # Reuse orphaned copies left by an interrupted/failed attempt.
        existing = await session.scalar(
            select(SourceArtifact).where(
                SourceArtifact.sha256 == sha,
                SourceArtifact.artifact_type == "ORIGINAL_DOCUMENT",
            ).order_by(SourceArtifact.created_at.desc()).limit(1).with_for_update()
        )
        if existing:
            if existing.transaction_id:
                public_id = await session.scalar(
                    select(Transaction.public_id).where(Transaction.id == existing.transaction_id)
                )
                raise DuplicateDocument(public_id or str(existing.transaction_id))
            original = existing
    if original is not None:
        meta = original.extra_data or {}
        if meta.get("status") == "PROCESSING":
            try:
                last = datetime.fromisoformat(meta.get("last_attempt_at", ""))
                if datetime.now(UTC) - last < timedelta(minutes=10):
                    raise ArtifactBusy(original.id)
            except (ValueError, TypeError):
                # Legacy original artifacts without a timestamp can be recovered.
                pass
        if not original.object_key or not await object_storage.exists(original.object_key):
            raise DocumentNeedsReview("Stored source document is missing; inspect MinIO.")
    else:
        object_key = f"intake/{datetime.now(UTC):%Y/%m/%d}/{uuid4().hex}/{safe_name}"
        await object_storage.put_bytes(object_key=object_key, data=data, content_type=content_type)
        original = SourceArtifact(
            transaction_id=None, artifact_type="ORIGINAL_DOCUMENT", original_name=safe_name,
            mime_type=content_type, storage_provider="MINIO", bucket=settings.minio_bucket,
            object_key=object_key, sha256=sha, source_ref=safe_name, extra_data={"status": "STORED"},
        )
        session.add(original)
        await session.commit()
        await session.refresh(original)

    await _mark(session, original, "PROCESSING", last_attempt_at=datetime.now(UTC).isoformat())
    try:
        document = extract_document(filename=safe_name, data=data)
        ai_result = await extract_order_draft(document)
        draft = ai_result.data
        if draft.document_type != "PURCHASE_ORDER":
            raise DocumentNeedsReview("This document is not confidently classified as a PO.",
                                      {"document_type": draft.document_type})
        # Schema-valid and self-reported confidence are not evidence.
        # Block corrected/unverified critical source fields *before* any
        # deterministic business validation or transaction creation.
        review_flags = [
            flag for flag in draft.risk_flags
            if flag.upper().startswith("REVIEW_REQUIRED_")
        ]
        if review_flags:
            raise DocumentNeedsReview(
                "Source grounding found missing, unverifiable or conflicting "
                "critical fields. Confirm the saved document in human review.",
                {
                    "review_flags": review_flags,
                    "corrected_fields": ai_result.usage.get(
                        "source_grounding", {}
                    ).get("corrected_fields", []),
                },
            )
        if draft.overall_confidence < 0.80:
            raise DocumentNeedsReview("AI confidence is below the automatic threshold.",
                                      {"confidence": draft.overall_confidence, "missing_fields": draft.missing_fields})
        if any("PROMPT" in x.upper() or "INJECTION" in x.upper() for x in draft.risk_flags):
            raise DocumentNeedsReview("Possible prompt injection detected; requires review.")
        if not draft.po_number or not draft.customer_hint or not draft.lines:
            raise DocumentNeedsReview("PO number, customer or complete line items are missing.")
        warehouse = draft.delivery_warehouse_code or _warehouse_from_location(draft.delivery_location)
        if not warehouse:
            raise DocumentNeedsReview("Warehouse cannot be confirmed from the source.")

        manual = ManualOrderInput(
            po_number=draft.po_number, customer_hint=draft.customer_hint,
            customer_domain=draft.customer_domain, currency=draft.currency.upper(),
            delivery_warehouse_code=warehouse, requested_delivery_date=draft.requested_delivery_date,
            lines=[ManualOrderLineInput(
                line_number=line.line_number, product_term=line.product_term,
                quantity=Decimal(str(line.quantity)), uom=line.uom,
                requested_unit_price=(Decimal(str(line.requested_unit_price))
                                      if line.requested_unit_price is not None else None),
            ) for line in draft.lines],
        )
        await _check_duplicate_order(session, manual.po_number, manual.customer_hint)
        # Track the PO before handing off to the existing deterministic validator.
        await _mark(session, original, "VALIDATING", extracted_po=manual.po_number)
        transaction_result = await create_manual_order(session, manual, source="FILE_UPLOAD")
        original.transaction_id = transaction_result.transaction_id
        original.extra_data = {
            **(original.extra_data or {}), "status": "PROCESSED",
            "extraction_method": document.extraction_method, "page_count": document.page_count,
        }
        session.add(AIDecision(
            transaction_id=transaction_result.transaction_id,
            decision_type="DOCUMENT_EXTRACTION", provider=ai_result.provider,
            model_name=ai_result.model, prompt_version=DOCUMENT_EXTRACTION_PROMPT_VERSION,
            input_hash=sha, output_payload=draft.model_dump(mode="json"),
            confidence=Decimal(str(draft.overall_confidence)),
            validation_result="SCHEMA_VALID_AND_ACCEPTED", status="RECORDED",
        ))
        await session.commit()
        return IntakeUploadResponse(
            artifact_id=original.id, object_key=original.object_key,
            provider=ai_result.provider, model=ai_result.model,
            prompt_version=DOCUMENT_EXTRACTION_PROMPT_VERSION,
            extraction=draft, transaction=transaction_result,
        )
    except Exception as exc:
        # create_manual_order uses several commits; do not assume a transaction can
        # always be rolled back. Explicitly retain the source and mark it for review.
        await session.rollback()
        artifact = await session.get(SourceArtifact, original.id)
        if artifact is not None:
            if isinstance(exc, AIProviderError):
                status = "AI_UNAVAILABLE" if exc.retryable else "AI_NEEDS_REVIEW"
            elif isinstance(exc, (DocumentNeedsReview, ResolutionNeedsReview)):
                status = "NEEDS_REVIEW"
            elif isinstance(exc, DuplicateDocument):
                status = "DUPLICATE_REVIEW"
            else:
                status = "FAILED_MANUAL"
            review_metadata = {}
            if isinstance(exc, DocumentNeedsReview):
                # Persist only field names and review flags; never write raw
                # customer documents or LLM output into operational logs.
                review_metadata = {
                    "review_flags": exc.details.get("review_flags", []),
                    "source_corrected_fields": exc.details.get("corrected_fields", []),
                }
            await _mark(session, artifact, status,
                        last_error_code=type(exc).__name__, **review_metadata)
        if isinstance(exc, AIProviderError):
            exc.artifact_id = original.id
        if isinstance(exc, DocumentNeedsReview):
            exc.details = {**exc.details, "artifact_id": str(original.id),
                           "manual_review_available": True}
        raise


async def confirm_human_review(
    session: AsyncSession, *, artifact_id: UUID, data: ManualOrderInput,
    actor_id: str,
):
    """A human must check the original; this path deliberately records NO AI decision."""
    original = await get_original_artifact(session, artifact_id)
    if original.transaction_id is not None:
        raise ValueError("Artifact is already attached to a transaction.")
    if original.sha256 is None or not original.object_key:
        raise ValueError("Source artifact has no verifiable stored original.")
    await _check_duplicate_order(session, data.po_number, data.customer_hint)
    result = await create_manual_order(session, data, source="FILE_UPLOAD_HUMAN_REVIEW")
    original.transaction_id = result.transaction_id
    original.extra_data = {
        **(original.extra_data or {}), "status": "HUMAN_REVIEWED",
        "reviewed_by": actor_id, "reviewed_at": datetime.now(UTC).isoformat(),
    }
    transaction = await session.get(Transaction, result.transaction_id)
    await append_transaction_event(
        session, transaction=transaction, step="DOCUMENT_REVIEW",
        event_type="ORIGINAL_DOCUMENT_HUMAN_CONFIRMED", actor_type="HUMAN",
        actor_id=actor_id, payload={"artifact_id": str(artifact_id),
                                    "source_checksum": original.sha256}, commit=False,
    )
    await session.commit()
    return result
