from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.db.session import get_db
from app.core.security import DemoPrincipal, require_operator
from app.schemas.execution import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    DownstreamExecutionRequest,
    DownstreamExecutionResponse,
    ERPExecutionResponse,
    RecoveryResponse,
)
from app.services.approval_service import (
    decide_approval,
)
from app.services.erp_service import (
    ERPExecutionError,
    execute_erp_order,
    retry_erp_order,
)
from app.services.recovery_service import (
    archive_and_complete,
    recover_downstream,
)


router = APIRouter(
    prefix="/execution",
    tags=["execution"],
)


@router.post(
    "/approvals/{approval_id}/decision",
    response_model=(
        ApprovalDecisionResponse
    ),
)
async def approval_decision(
    approval_id: UUID,
    data: ApprovalDecisionRequest,
    db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    try:
        # Never trust role/actor claims in user-supplied JSON.
        data = data.model_copy(update={"approver_role": principal.role, "actor_id": principal.actor_id})
        return await decide_approval(
            db,
            approval_id=approval_id,
            data=data,
        )

    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.post(
    "/transactions/{public_id}/erp",
    response_model=ERPExecutionResponse,
)
async def execute_erp(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    try:
        if principal.role not in {"OPERATIONS_MANAGER", "FINANCE_MANAGER", "ADMIN"}:
            raise HTTPException(403, "Operator role cannot execute ERP orders.")
        return await execute_erp_order(
            db,
            public_id=public_id,
        )

    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    except ERPExecutionError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": (
                    "ERP execution failed."
                ),
                "error": str(exc),
            },
        ) from exc


@router.post(
    (
        "/transactions/"
        "{public_id}/downstream"
    ),
    response_model=(
        DownstreamExecutionResponse
    ),
)
async def execute_downstream(
    public_id: str,
    data: DownstreamExecutionRequest,
    db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    try:
        if principal.role not in {"OPERATIONS_MANAGER", "ADMIN"}:
            raise HTTPException(403, "Only operations can execute downstream actions.")
        return await archive_and_complete(
            db,
            public_id=public_id,
            simulate_failure=(
                data.simulate_failure
            ),
        )

    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.post(
    (
        "/transactions/"
        "{public_id}/recover"
    ),
    response_model=RecoveryResponse,
)
async def recover(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    try:
        if principal.role not in {"OPERATIONS_MANAGER", "ADMIN"}:
            raise HTTPException(403, "Only operations can run recovery.")
        return await recover_downstream(
            db,
            public_id=public_id,
        )

    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

@router.post("/transactions/{public_id}/erp/retry", response_model=ERPExecutionResponse)
async def retry_erp(
    public_id: str, db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    if principal.role not in {"OPERATIONS_MANAGER", "ADMIN"}:
        raise HTTPException(403, "Only operations may trigger an uncertain ERP replay.")
    try:
        return await retry_erp_order(db, public_id=public_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ERPExecutionError as exc:
        raise HTTPException(502, "ERP replay could not be verified; retain existing idempotency key.") from exc
