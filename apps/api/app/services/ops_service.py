import httpx
from decimal import Decimal

from sqlalchemy import (
    func,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
)

from app.core.config import settings
from app.models.digital_twin import (
    AIDecision,
    Approval,
    Evidence,
    Incident,
    IntegrationCommand,
)
from app.models.transaction import (
    Transaction,
)
from app.schemas.ops import (
    DependencyHealth,
    IntegrationHealthResponse,
    OperationsOverview,
)
from app.services.ai_gateway import (
    get_ai_provider,
)
from app.services.object_storage import (
    object_storage,
)


async def get_operations_overview(
    session: AsyncSession,
) -> OperationsOverview:
    total = (
        await session.scalar(
            select(
                func.count(
                    Transaction.id
                )
            )
        )
        or 0
    )

    completed = (
        await session.scalar(
            select(
                func.count(
                    Transaction.id
                )
            )
            .where(
                Transaction.status
                == "COMPLETED"
            )
        )
        or 0
    )

    approval_required = (
        await session.scalar(
            select(
                func.count(
                    Transaction.id
                )
            )
            .where(
                Transaction.status
                == "APPROVAL_REQUIRED"
            )
        )
        or 0
    )

    degraded = (
        await session.scalar(
            select(
                func.count(
                    Transaction.id
                )
            )
            .where(
                Transaction.status
                == "DEGRADED"
            )
        )
        or 0
    )

    pending_approvals = (
        await session.scalar(
            select(
                func.count(
                    Approval.id
                )
            )
            .where(
                Approval.status
                == "PENDING"
            )
        )
        or 0
    )

    open_incidents = (
        await session.scalar(
            select(
                func.count(
                    Incident.id
                )
            )
            .where(
                Incident.status
                == "OPEN"
            )
        )
        or 0
    )

    verified_erp_orders = (
        await session.scalar(
            select(
                func.count(
                    IntegrationCommand.id
                )
            )
            .where(
                IntegrationCommand.provider
                == "ODOO",
                IntegrationCommand.action
                == "CREATE_SALE_ORDER",
                IntegrationCommand.status
                == "VERIFIED",
            )
        )
        or 0
    )

    ai_decisions = (
        await session.scalar(
            select(
                func.count(
                    AIDecision.id
                )
            )
        )
        or 0
    )

    total_value = (
        await session.scalar(
            select(
                func.coalesce(
                    func.sum(
                        Transaction.value
                    ),
                    0,
                )
            )
        )
        or Decimal("0")
    )

    blocked_statuses = [
        "APPROVAL_REQUIRED",
        "DEGRADED",
        "FAILED_RETRYABLE",
        "FAILED_MANUAL",
        "RECOVERY_PENDING",
    ]

    blocked_revenue = (
        await session.scalar(
            select(
                func.coalesce(
                    func.sum(
                        Transaction.value
                    ),
                    0,
                )
            )
            .where(
                Transaction.status.in_(
                    blocked_statuses
                )
            )
        )
        or Decimal("0")
    )

    evidence_result = await session.execute(
        select(Evidence)
        .where(
            Evidence.evidence_type
            == "PRICING_AUTHORITY"
        )
    )

    pricing_discrepancies = sum(
        1
        for item
        in evidence_result
        .scalars()
        .all()
        if (
            item.details
            .get(
                "pricing_exception",
                False,
            )
        )
    )

    return OperationsOverview(
        total_transactions=total,
        completed_transactions=completed,
        approval_required=(
            approval_required
        ),
        degraded_transactions=degraded,
        pending_approvals=(
            pending_approvals
        ),
        open_incidents=open_incidents,
        verified_erp_orders=(
            verified_erp_orders
        ),
        ai_decisions=ai_decisions,
        total_order_value=(
            Decimal(total_value)
        ),
        blocked_revenue=(
            Decimal(blocked_revenue)
        ),
        pricing_discrepancies_prevented=(
            pricing_discrepancies
        ),
    )


async def get_integration_health(
    session: AsyncSession,
) -> IntegrationHealthResponse:
    dependencies: list[
        DependencyHealth
    ] = []

    try:
        await session.execute(
            select(1)
        )

        dependencies.append(
            DependencyHealth(
                name="PostgreSQL",
                status="HEALTHY",
            )
        )

    except Exception as exc:
        dependencies.append(
            DependencyHealth(
                name="PostgreSQL",
                status="UNHEALTHY",
                detail=str(exc),
            )
        )

    if await object_storage.bucket_exists():
        dependencies.append(
            DependencyHealth(
                name="MinIO",
                status="HEALTHY",
            )
        )

    else:
        dependencies.append(
            DependencyHealth(
                name="MinIO",
                status="UNHEALTHY",
            )
        )

    ai_provider = get_ai_provider()

    if await ai_provider.health():
        dependencies.append(
            DependencyHealth(
                name="Ollama",
                status="SERVER_REACHABLE_MODEL_UNVERIFIED",
                detail=(
                    f"text={settings.ollama_text_model or settings.ollama_model}; "
                    f"vision={settings.ollama_vision_model or settings.ollama_model}. "
                    "Model installation not verified; run the inference probe or preflight."
                ),
            )
        )

    else:
        dependencies.append(
            DependencyHealth(
                name="Ollama",
                status="UNHEALTHY",
            )
        )

    try:
        async with httpx.AsyncClient(
            timeout=5
        ) as client:
            response = await client.get(
                (
                    settings
                    .odoo_base_url
                    .rstrip("/")
                    + "/ordernexa/api/"
                    "health"
                ),
                headers={
                    "X-OrderNexa-Key": (
                        settings
                        .ordernexa_odoo_shared_secret
                    )
                },
            )

        dependencies.append(
            DependencyHealth(
                name="Odoo",
                status=(
                    "HEALTHY"
                    if response
                    .status_code
                    == 200
                    else "UNHEALTHY"
                ),
                detail=(
                    None
                    if response
                    .status_code
                    == 200
                    else response.text[
                        :300
                    ]
                ),
            )
        )

    except Exception as exc:
        dependencies.append(
            DependencyHealth(
                name="Odoo",
                status="UNHEALTHY",
                detail=str(exc),
            )
        )

    return IntegrationHealthResponse(
        dependencies=dependencies
    )

async def list_pending_approvals(session: AsyncSession) -> list[dict]:
    result = await session.execute(
        select(Approval, Transaction).join(Transaction, Transaction.id == Approval.transaction_id)
        .where(Approval.status == "PENDING")
        .order_by(Approval.created_at.asc()).limit(100)
    )
    return [
        {"approval_id": str(approval.id), "transaction_public_id": transaction.public_id,
         "customer_reference": transaction.customer_reference, "approver_role": approval.approver_role,
         "reason": approval.reason, "value": str(transaction.value or 0),
         "currency": transaction.currency, "status": transaction.status,
         "created_at": approval.created_at.isoformat() if approval.created_at else None}
        for approval, transaction in result.all()
    ]


async def list_open_incidents(session: AsyncSession) -> list[dict]:
    result = await session.execute(
        select(Incident, Transaction).join(Transaction, Transaction.id == Incident.transaction_id)
        .where(Incident.status == "OPEN").order_by(Incident.created_at.desc()).limit(100)
    )
    return [
        {"incident_id": str(incident.id), "transaction_public_id": transaction.public_id,
         "category": incident.category, "severity": incident.severity,
         "message": incident.message, "status": transaction.status,
         "value": str(transaction.value or 0), "currency": transaction.currency}
        for incident, transaction in result.all()
    ]


async def ai_quality_snapshot(session: AsyncSession) -> dict:
    # These counts are real stored records. They are NOT accuracy metrics: an
    # independently labeled evaluation set is required before accuracy claims.
    total = await session.scalar(select(func.count(AIDecision.id))) or 0
    failures = await session.scalar(
        select(func.count(AIDecision.id)).where(AIDecision.validation_result != "SCHEMA_VALID_AND_ACCEPTED")
    ) or 0
    return {"recorded_ai_decisions": total, "non_accepted_decisions": failures,
            "curated_eval_cases_run": None, "field_accuracy": None,
            "note": "Operational decision counts are NOT extraction-accuracy measurements."}
