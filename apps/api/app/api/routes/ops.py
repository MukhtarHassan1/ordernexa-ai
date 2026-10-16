from fastapi import (
    APIRouter,
    Depends,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.db.session import get_db
from app.core.security import require_operator
from app.schemas.governance import AutonomyPolicyUpdate, AskOpsRequest
from app.schemas.ops import (
    IntegrationHealthResponse,
    OperationsOverview,
)
from app.services.ops_service import (
    business_kpis,
    get_integration_health,
    get_operations_overview,
    transaction_decision_summary,
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

@router.get("/business-kpis")
async def business_kpi_report(
    db: AsyncSession = Depends(get_db),
):
    """Database-backed business metrics; unavailable metrics are explicitly null."""
    return await business_kpis(db)


@router.get("/transactions/{public_id}/decision-summary")
async def decision_summary(
    public_id: str,
    db: AsyncSession = Depends(get_db),
):
    from fastapi import HTTPException
    result = await transaction_decision_summary(db, public_id)
    if result is None:
        raise HTTPException(404, "Transaction not found.")
    return result


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


@router.get("/autonomy-policies")
async def autonomy_policies(
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_operator),
):
    from app.services.autonomy_service import list_autonomy_policies, seed_default_autonomy_policies
    if principal.role not in {"OPERATIONS_MANAGER", "ADMIN", "AUDITOR"}:
        from fastapi import HTTPException
        raise HTTPException(403, "Operations/Admin/Auditor role required.")
    await seed_default_autonomy_policies(db, actor_id=principal.actor_id)
    return {"items": await list_autonomy_policies(db),
            "notice": "Policies are per action. External writes remain separately gated and disabled by default."}


@router.put("/autonomy-policies/{action}")
async def set_autonomy_policy(
    action: str, data: AutonomyPolicyUpdate,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_operator),
):
    from fastapi import HTTPException
    from app.services.autonomy_service import update_autonomy_policy
    if principal.role not in {"OPERATIONS_MANAGER", "ADMIN"}:
        raise HTTPException(403, "Operations/Admin role required.")
    try:
        return await update_autonomy_policy(
            db, action=action, level=data.level, enabled=data.enabled, actor_id=principal.actor_id,
            max_value=data.max_value, allowed_risks=data.allowed_risks, notes=data.notes,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/ask")
async def ask_ops(
    data: AskOpsRequest,
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_operator),
):
    from fastapi import HTTPException
    from app.core.config import settings
    from app.services.ask_ops_service import answer_ops_question
    if principal.role not in {"OPERATIONS_MANAGER", "ADMIN", "AUDITOR", "SALES_MANAGER", "FINANCE_MANAGER"}:
        raise HTTPException(403, "This role cannot query operations data.")
    if not settings.ask_ops_enabled:
        raise HTTPException(503, "Ask Ops is disabled by configuration.")
    try:
        return await answer_ops_question(db, data.question)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/release-readiness")
async def release_readiness_report(
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_operator),
):
    from fastapi import HTTPException
    from app.services.ops_service import release_readiness
    if principal.role not in {"OPERATIONS_MANAGER", "ADMIN", "AUDITOR"}:
        raise HTTPException(403, "Operations/Admin/Auditor role required.")
    return await release_readiness(db)


@router.get("/model-routing")
async def model_routing(principal=Depends(require_operator)):
    from app.core.config import settings
    if principal.role not in {"OPERATIONS_MANAGER", "ADMIN", "AUDITOR"}:
        from fastapi import HTTPException
        raise HTTPException(403, "Operations/Admin/Auditor role required.")
    return {
        "provider": settings.ai_provider,
        "text_model": settings.ollama_text_model or settings.ollama_model,
        "vision_model": settings.ollama_vision_model or settings.ollama_model,
        "probe_model": settings.ollama_probe_model,
        "fallbacks": [],
        "policy": "Deterministic authority is mandatory; provider/model routing cannot bypass validation, policy or approval.",
        "note": "Configured model names are not quality evidence. Use measured evaluation reports before increasing autonomy.",
    }


@router.get("/technical-metrics")
async def technical_metric_report(
    db: AsyncSession = Depends(get_db),
    principal=Depends(require_operator),
):
    from fastapi import HTTPException
    from app.services.ops_service import technical_metrics
    if principal.role not in {"OPERATIONS_MANAGER", "ADMIN", "AUDITOR"}:
        raise HTTPException(403, "Operations/Admin/Auditor role required.")
    return await technical_metrics(db)
