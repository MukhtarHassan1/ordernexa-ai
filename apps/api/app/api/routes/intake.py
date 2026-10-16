"""Local document intake: original artifacts survive inference failures.

These local API endpoints require an operator key. Production multi-channel
connectors need their own independently authenticated webhook ingress.
"""
from uuid import UUID

from fastapi.responses import Response
from sqlalchemy import select

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import DemoPrincipal, require_operator
from app.db.session import get_db
from app.models.transaction import Transaction
from app.schemas.c2c import ManualOrderInput, ManualOrderValidationResponse
from app.schemas.intake import IntakeUploadResponse
from app.services.ai_gateway import AIProviderError
from app.services.c2c_validation_service import ResolutionNeedsReview
from app.services.intake_service import (
    ArtifactBusy, DocumentNeedsReview, DuplicateDocument,
    confirm_human_review, get_original_artifact, get_verified_original_bytes, ingest_order_file,
)
from app.services.manual_document_preview import PreviewNotPossible, preview_purchase_order
from app.services.object_storage import object_storage

router = APIRouter(prefix="/intake", tags=["intake"])


def _translate(exc: Exception):
    if isinstance(exc, DuplicateDocument):
        return HTTPException(409, {"code": "DUPLICATE_DOCUMENT", "existing_transaction": exc.existing_public_id})
    if isinstance(exc, ArtifactBusy):
        return HTTPException(409, {"code": "ARTIFACT_BUSY", "artifact_id": str(exc.artifact_id),
                                   "message": "An earlier attempt is still running; check the artifact before retrying."})
    if isinstance(exc, DocumentNeedsReview):
        # A saved artifact requiring review is a governed workflow state,
        # not a server fault. Keep HTTP 422 to fail closed for API clients.
        # Add stable top-level routing metadata for consoles and n8n clients.
        artifact_id = exc.details.get("artifact_id")
        return HTTPException(422, {
            "code": "DOCUMENT_NEEDS_REVIEW",
            "workflow_state": "NEEDS_HUMAN_REVIEW",
            "artifact_id": artifact_id,
            "message": exc.message,
            "next_step": (
                f"GET /api/v1/intake/artifacts/{artifact_id}/preview"
                if artifact_id else "Inspect the original document"
            ),
            "details": exc.details,
        })
    if isinstance(exc, AIProviderError):
        return HTTPException(503 if exc.retryable else 422, {
            "code": exc.code, "message": exc.detail, "retryable": exc.retryable,
            "artifact_id": str(exc.artifact_id) if hasattr(exc, "artifact_id") else None,
            "next_step": "Use GET /api/v1/intake/artifacts/{id}/preview for human review, "
                         "or POST /api/v1/intake/artifacts/{id}/retry once the AI runtime is ready.",
        }, headers={"Retry-After": "75"} if exc.retryable else None)
    if isinstance(exc, ResolutionNeedsReview):
        return HTTPException(409, {"code": "RESOLUTION_NEEDS_REVIEW", "message": exc.message,
                                   "transaction_public_id": exc.public_id,
                                   "resolution_type": exc.resolution_type, "candidates": exc.candidates})
    if isinstance(exc, (ValueError, PreviewNotPossible)):
        return HTTPException(422, {"code": "INVALID_REVIEW", "message": str(exc)})
    return HTTPException(500, "Unexpected intake failure.")


@router.post("/upload", response_model=IntakeUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_order(
    file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    filename = file.filename or "uploaded-document"
    # Bounded read prevents accidentally loading arbitrarily large uploads into RAM.
    data = await file.read(settings.max_upload_bytes + 1)
    await file.close()
    if not data:
        raise HTTPException(400, "Uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "Upload exceeds MAX_UPLOAD_BYTES.")
    try:
        return await ingest_order_file(
            db, filename=filename, content_type=file.content_type or "application/octet-stream", data=data,
        )
    except (DuplicateDocument, ArtifactBusy, DocumentNeedsReview,
            AIProviderError, ResolutionNeedsReview, ValueError) as exc:
        raise _translate(exc) from exc


@router.get("/artifacts/{artifact_id}")
async def artifact_status(
    artifact_id: UUID, db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    try:
        item = await get_original_artifact(db, artifact_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    public_id = None
    if item.transaction_id:
        public_id = await db.scalar(
            select(Transaction.public_id).where(Transaction.id == item.transaction_id)
        )
    return {
        "artifact_id": str(item.id), "filename": item.original_name,
        "transaction_public_id": public_id,
        "status": (item.extra_data or {}).get("status", "UNKNOWN"),
        "transaction_id": str(item.transaction_id) if item.transaction_id else None,
        "sha256": item.sha256, "stored": bool(item.object_key),
        "last_error_code": (item.extra_data or {}).get("last_error_code"),
        "review_flags": (item.extra_data or {}).get("review_flags", []),
        "source_corrected_fields": (item.extra_data or {}).get("source_corrected_fields", []),
        "next_action": (
            "INSPECT_TRANSACTION" if item.transaction_id else
            "CHECK_STATUS" if (item.extra_data or {}).get("status") in {"PROCESSING", "VALIDATING"} else
            "HUMAN_REVIEW_OR_RETRY"
        ),
    }


@router.post("/artifacts/{artifact_id}/retry", response_model=IntakeUploadResponse)
async def retry_original(
    artifact_id: UUID, db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    try:
        item = await get_original_artifact(db, artifact_id)
        if item.transaction_id:
            raise ValueError("The artifact already belongs to a transaction; replay is unsafe.")
        if not item.object_key:
            raise ValueError("Stored original is missing its object key.")
        data = await get_verified_original_bytes(item)
        return await ingest_order_file(
            db, filename=item.original_name or "document.txt",
            content_type=item.mime_type or "application/octet-stream",
            data=data, existing_artifact_id=artifact_id,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (DuplicateDocument, ArtifactBusy, DocumentNeedsReview,
            AIProviderError, ResolutionNeedsReview, ValueError) as exc:
        raise _translate(exc) from exc


@router.get("/artifacts/{artifact_id}/original")
async def download_saved_original(
    artifact_id: UUID, db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    """Authorized download to compare a saved document with its review fields.

    Never serve user-uploaded files inline. The local development key is not suitable
    for deployment outside localhost; production must use proper authentication.
    """
    if principal.role not in {"SALES_MANAGER", "OPERATIONS_MANAGER", "ADMIN"}:
        raise HTTPException(403, "Sales or operations review permission is required.")
    try:
        item = await get_original_artifact(db, artifact_id)
        data = await get_verified_original_bytes(item)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise _translate(exc) from exc
    # Ingest sanitizes file names. Sanitize again to avoid legacy filename issues.
    import re
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", (item.original_name or "document").split("/")[-1])[:150]
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name or "document"}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/artifacts/{artifact_id}/preview")
async def human_preview(
    artifact_id: UUID, db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    if principal.role not in {"SALES_MANAGER", "OPERATIONS_MANAGER", "ADMIN"}:
        raise HTTPException(403, "Sales or operations review permission is required.")
    try:
        item = await get_original_artifact(db, artifact_id)
        if not item.object_key:
            raise ValueError("Stored original is missing its object key.")
        data = await get_verified_original_bytes(item)
        preview = preview_purchase_order(filename=item.original_name or "document.txt", data=data)
        return {"artifact_id": str(artifact_id), **preview}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, PreviewNotPossible, DocumentNeedsReview) as exc:
        raise _translate(exc) from exc


@router.post("/artifacts/{artifact_id}/human-confirm", response_model=ManualOrderValidationResponse)
async def human_confirm(
    artifact_id: UUID, data: ManualOrderInput, db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    if principal.role not in {"SALES_MANAGER", "OPERATIONS_MANAGER", "ADMIN"}:
        raise HTTPException(403, "Sales or operations review permission is required.")
    try:
        return await confirm_human_review(
            db, artifact_id=artifact_id, data=data, actor_id=principal.actor_id,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, ResolutionNeedsReview, DuplicateDocument) as exc:
        raise _translate(exc) from exc
