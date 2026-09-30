from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import DemoPrincipal, require_operator
from app.schemas.c2c import (
    ManualOrderInput,
    ManualOrderValidationResponse,
    TransactionDetailResponse,
)
from app.services.c2c_validation_service import (
    ResolutionNeedsReview,
    create_manual_order,
    get_transaction_detail,
)


router = APIRouter(
    prefix="/c2c",
    tags=["customer-to-cash"],
)


@router.post(
    "/manual-order",
    response_model=ManualOrderValidationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def manual_order(
    data: ManualOrderInput,
    db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    try:
        return await create_manual_order(
            db,
            data,
        )

    except ResolutionNeedsReview as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": exc.message,
                "transaction_public_id": (
                    exc.public_id
                ),
                "resolution_type": (
                    exc.resolution_type
                ),
                "candidates": exc.candidates,
            },
        ) from exc


@router.get(
    "/transactions/{public_id}",
    response_model=TransactionDetailResponse,
)
async def transaction_detail(
    public_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await get_transaction_detail(
        db,
        public_id,
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found.",
        )

    return result