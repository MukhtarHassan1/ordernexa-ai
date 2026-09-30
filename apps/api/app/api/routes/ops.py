from fastapi import (
    APIRouter,
    Depends,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.db.session import get_db
from app.core.security import require_operator
from app.schemas.ops import (
    IntegrationHealthResponse,
    OperationsOverview,
)
from app.services.ops_service import (
    get_integration_health,
    get_operations_overview,
)


router = APIRouter(
    prefix="/ops",
    tags=["operations"],
)


@router.get(
    "/overview",
    response_model=OperationsOverview,
)
async def overview(
    db: AsyncSession = Depends(get_db),
):
    return await get_operations_overview(
        db
    )


@router.get(
    "/integration-health",
    response_model=(
        IntegrationHealthResponse
    ),
)
async def integration_health(
    db: AsyncSession = Depends(get_db),
):
    return await get_integration_health(
        db
    )

@router.get("/pending-approvals")
async def pending_approvals(db: AsyncSession = Depends(get_db)):
    from app.services.ops_service import list_pending_approvals
    return await list_pending_approvals(db)


@router.get("/open-incidents")
async def open_incidents(db: AsyncSession = Depends(get_db)):
    from app.services.ops_service import list_open_incidents
    return await list_open_incidents(db)


@router.get("/ai-quality")
async def ai_quality(db: AsyncSession = Depends(get_db)):
    from app.services.ops_service import ai_quality_snapshot
    return await ai_quality_snapshot(db)


@router.post("/ai-inference-probe")
async def ai_inference_probe(principal=Depends(require_operator)):
    """Explicit probe: /api/tags alone cannot verify actual model execution."""
    from fastapi import HTTPException
    from app.services.ai_gateway import AIProviderError, OllamaProvider
    try:
        return await OllamaProvider().probe_inference()
    except AIProviderError as exc:
        raise HTTPException(503, {"status": "MODEL_NOT_READY", "code": exc.code,
                                  "message": exc.detail}) from exc


@router.get('/evaluation-reports')
async def evaluation_reports(principal=Depends(require_operator)):
    """List actual local benchmark reports; never infer performance from an empty directory."""
    import json
    from pathlib import Path
    base = Path('/evals/reports')
    if not base.exists():
        return {'items': [], 'message': 'No measured benchmark reports found.'}
    reports = []
    for path in sorted(base.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:25]:
        if path.is_symlink() or path.stat().st_size > 5_000_000:
            continue
        try:
            value = json.loads(path.read_text())
            if not isinstance(value, dict) or not isinstance(value.get('cases'), int):
                continue
            reports.append({
                'file': path.name,
                'run_at': value.get('run_at'),
                'provider': value.get('provider'),
                'cases': value['cases'],
                'dataset': Path(str(value.get('dataset', 'unknown'))).name,
                'raw_model_field_accuracy': value.get('raw_model_field_accuracy'),
                'source_grounded_accuracy': value.get('field_accuracy'),
                'safety_pass_rate': value.get('safety_pass_rate'),
                'raw_model_safety_pass_rate': value.get('raw_model_safety_pass_rate'),
                'critical_gate_pass': bool(value.get('critical_gate_pass', False)),
                'latency_p50_s': value.get('latency_p50_s'),
            })
        except (ValueError, OSError, TypeError):
            continue
    return {'items': reports, 'message': 'Results originate from saved evaluation reports; not generated dashboard scores.'}
