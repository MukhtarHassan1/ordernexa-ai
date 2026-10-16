from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import require_operator
from app.db.session import get_db
from app.services.knowledge_service import contract_evidence
from app.schemas.knowledge import KnowledgeDocumentIn, KnowledgeQuery
from app.services.knowledge_retrieval import ingest_knowledge_document, retrieve_knowledge

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


@router.post("/documents")
async def add_knowledge_document(
    data: KnowledgeDocumentIn,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_operator),
):
    from fastapi import HTTPException
    if principal.role not in {"OPERATIONS_MANAGER", "ADMIN"}:
        raise HTTPException(403, "Operations/Admin role required to ingest knowledge.")
    try:
        return await ingest_knowledge_document(db, **data.model_dump())
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/retrieve")
async def retrieve_scoped_knowledge(
    data: KnowledgeQuery,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_operator),
):
    try:
        return await retrieve_knowledge(db, **data.model_dump())
    except LookupError as exc:
        from fastapi import HTTPException
        raise HTTPException(404, str(exc)) from exc
