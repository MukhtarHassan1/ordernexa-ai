from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import require_operator
from app.db.session import get_db
from app.services.knowledge_service import contract_evidence

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/contract-evidence", dependencies=[Depends(require_operator)])
async def lookup_contract_evidence(
    customer_code: str = Query(min_length=2, max_length=50),
    sku: str = Query(min_length=2, max_length=60),
    effective_on: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await contract_evidence(db, customer_code=customer_code, sku=sku,
                                   effective_on=effective_on)
