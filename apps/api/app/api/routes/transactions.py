from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security import DemoPrincipal, require_operator
from app.schemas.transaction import (
    TransactionAdvance,
    TransactionCreate,
    TransactionEventRead,
    TransactionRead,
)
from app.services.transaction_service import (
    advance_transaction,
    create_transaction,
    get_timeline,
    get_transaction,
    get_transaction_for_update,
    list_transactions,
)


router = APIRouter(
    prefix="/transactions",
    tags=["transactions"],
)


@router.post(
    "",
    response_model=TransactionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create(
    data: TransactionCreate,
    db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    return await create_transaction(
        db,
        data,
    )


@router.get(
    "",
    response_model=list[TransactionRead],
)
async def list_all(
    db: AsyncSession = Depends(get_db),
):
    return await list_transactions(db)


@router.get(
    "/{public_id}",
    response_model=TransactionRead,
)
async def get_one(
    public_id: str,
    db: AsyncSession = Depends(get_db),
):
    transaction = await get_transaction(
        db,
        public_id,
    )

    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    return transaction


@router.get(
    "/{public_id}/timeline",
    response_model=list[TransactionEventRead],
)
async def timeline(
    public_id: str,
    db: AsyncSession = Depends(get_db),
):
    transaction = await get_transaction(
        db,
        public_id,
    )

    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    return await get_timeline(
        db,
        transaction.id,
    )


@router.post(
    "/{public_id}/advance",
    response_model=TransactionRead,
)
async def advance(
    public_id: str,
    data: TransactionAdvance,
    db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    if principal.role != "ADMIN":
        raise HTTPException(403, "Direct state advances are restricted to local demo administrators.")
    transaction = await get_transaction_for_update(
        db,
        public_id,
    )

    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    try:
        return await advance_transaction(
            db,
            transaction,
            data,
        )

    except ValueError as exc:
        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc