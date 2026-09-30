from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.routes.c2c import (
    router as c2c_router,
)
from app.api.routes.execution import (
    router as execution_router,
)
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.health import (
    router as health_router,
)
from app.api.routes.intake import (
    router as intake_router,
)
from app.api.routes.ops import (
    router as ops_router,
)
from app.api.routes.transactions import (
    router as transactions_router,
)
from app.api.routes.automation import router as automation_router
from app.core.config import settings


app = FastAPI(
    title=settings.app_name,
    version="0.4.0",
    description=(
        "OrderNexa AI — Agentic "
        "Customer-to-Cash "
        "Operations Platform"
    ),
)


@app.get("/")
async def root():
    return {
        "product": "OrderNexa AI",
        "status": "running",
        "version": "0.4.0",
    }


app.include_router(
    health_router,
    prefix="/api/v1",
)

app.include_router(
    transactions_router,
    prefix="/api/v1",
)

app.include_router(
    c2c_router,
    prefix="/api/v1",
)

app.include_router(
    intake_router,
    prefix="/api/v1",
)

app.include_router(
    execution_router,
    prefix="/api/v1",
)

app.include_router(
    ops_router,
    prefix="/api/v1",
)

# Local portfolio console. Serve on the existing 127.0.0.1:8000 host binding;
# production exposure requires OAuth, CSRF strategy and a reverse proxy.
app.mount(
    "/console", StaticFiles(directory=Path(__file__).parent / "console", html=True),
    name="local-console",
)

app.include_router(knowledge_router, prefix="/api/v1")

app.include_router(automation_router, prefix="/api/v1")
