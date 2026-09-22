from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.transactions import router as transactions_router
from app.core.config import settings


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "OrderNexa AI — Agentic Customer-to-Cash Operations Platform"
    ),
)


@app.get("/")
async def root():
    return {
        "product": "OrderNexa AI",
        "status": "running",
        "version": "0.1.0",
    }


app.include_router(
    health_router,
    prefix="/api/v1",
)

app.include_router(
    transactions_router,
    prefix="/api/v1",
)