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

    # Persisted circuit/subscription state supplements live probes. It never
    # fabricates "healthy" for an integration that has not been configured.
    from app.models.automation import AutomationJob
    from app.models.digital_twin import ExternalSubscription, IntegrationCircuit
    circuits = (await session.execute(select(IntegrationCircuit))).scalars().all()
    for circuit in circuits:
        dependencies.append(DependencyHealth(
            name=f"Circuit/{circuit.provider}",
            status=circuit.state,
            detail=(f"failures={circuit.failure_count}; last_error={circuit.last_error_category or 'none'}"),
        ))

    graph_subscription = await session.scalar(
        select(ExternalSubscription)
        .where(ExternalSubscription.provider == "MICROSOFT_GRAPH")
        .order_by(ExternalSubscription.expires_at.desc()).limit(1)
    )
    if graph_subscription:
        dependencies.append(DependencyHealth(
            name="Microsoft Graph subscription", status=graph_subscription.status,
            detail=f"expires={graph_subscription.expires_at.isoformat()}; delta_initialized={bool(graph_subscription.delta_link)}",
        ))
    else:
        dependencies.append(DependencyHealth(
            name="Microsoft Graph subscription",
            status="CONFIGURED_NOT_VERIFIED" if (settings.graph_client_id and settings.graph_mailbox) else "NOT_CONFIGURED",
            detail="No durable subscription record has been verified yet.",
        ))

    for name, configured in [
        ("HubSpot", bool(settings.hubspot_access_token)),
        ("Teams", bool(settings.teams_approval_webhook_url)),
        ("Voice/Vapi contract", len(settings.voice_server_secret) >= 32),
        ("n8n ingress", len(settings.n8n_ingest_secret) >= 32),
        ("Stripe sandbox", bool(settings.stripe_enabled and settings.stripe_secret_key.startswith("sk_test_") and settings.stripe_webhook_secret)),
        ("Production OIDC", bool(settings.oidc_issuer and settings.oidc_audience and settings.oidc_jwks_url.startswith("https://"))),
    ]:
        dependencies.append(DependencyHealth(
            name=name, status="CONFIGURED_NOT_LIVE_VERIFIED" if configured else "NOT_CONFIGURED",
        ))

    pending_jobs = await session.scalar(
        select(func.count(AutomationJob.id)).where(AutomationJob.status.in_(["PENDING", "RUNNING", "FAILED_RETRYABLE", "BLOCKED_UNCERTAIN"]))
    ) or 0
    dependencies.append(DependencyHealth(
        name="Automation worker",
        status="CONFIGURED" if settings.automation_worker_enabled else "DISABLED",
        detail=f"external_writes={settings.automation_live_writes}; active_or_recoverable_jobs={pending_jobs}",
    ))

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


async def business_kpis(session: AsyncSession) -> dict:
    """Compute portfolio/business KPIs only from stored transaction history.

    Metrics that cannot be supported by current data are returned as null rather
    than invented. Human touch *time* is intentionally omitted until explicit
    work-session timestamps exist.
    """
    from app.models.transaction import TransactionEvent
    total = await session.scalar(select(func.count(Transaction.id))) or 0
    completed = await session.scalar(select(func.count(Transaction.id)).where(Transaction.status == "COMPLETED")) or 0
    completed_with_approval = await session.scalar(
        select(func.count(func.distinct(Transaction.id)))
        .join(Approval, Approval.transaction_id == Transaction.id)
        .where(Transaction.status == "COMPLETED")
    ) or 0
    straight_through = max(0, completed - completed_with_approval)

    exception_tx = await session.scalar(
        select(func.count(func.distinct(Transaction.id)))
        .outerjoin(Approval, Approval.transaction_id == Transaction.id)
        .outerjoin(Incident, Incident.transaction_id == Transaction.id)
        .where((Approval.id.is_not(None)) | (Incident.id.is_not(None)) | Transaction.status.in_([
            "DUPLICATE_REVIEW", "WAITING_CUSTOMER", "DEGRADED", "BLOCKED_UNCERTAIN",
            "FAILED_RETRYABLE", "FAILED_MANUAL", "RECOVERY_PENDING",
        ]))
    ) or 0

    duplicate_blocks = await session.scalar(
        select(func.count(TransactionEvent.id)).where(TransactionEvent.event_type == "BUSINESS_ORDER_DUPLICATE_BLOCKED")
    ) or 0

    completed_rows = (await session.execute(
        select(Transaction.created_at, Transaction.completed_at).where(Transaction.completed_at.is_not(None))
    )).all()
    cycle_seconds = [max(0.0, (done - created).total_seconds()) for created, done in completed_rows if created and done]

    incident_rows = (await session.execute(
        select(Incident.created_at, Incident.resolved_at).where(Incident.resolved_at.is_not(None))
    )).all()
    mttr_seconds = [max(0.0, (done - created).total_seconds()) for created, done in incident_rows if created and done]

    ai_tx_count = await session.scalar(select(func.count(func.distinct(AIDecision.transaction_id)))) or 0
    review_events = await session.scalar(
        select(func.count(func.distinct(TransactionEvent.transaction_id))).where(
            TransactionEvent.event_type.in_(["ORIGINAL_DOCUMENT_HUMAN_CONFIRMED", "AMENDMENT_VALIDATION_REQUIRED"])
        )
    ) or 0

    return {
        "stored_transactions": total,
        "completed_transactions": completed,
        "straight_through_completed": straight_through,
        "straight_through_processing_rate": (round(straight_through / completed, 4) if completed else None),
        "exception_transaction_rate": (round(exception_tx / total, 4) if total else None),
        "average_cycle_time_seconds": (round(sum(cycle_seconds) / len(cycle_seconds), 2) if cycle_seconds else None),
        "mean_time_to_recovery_seconds": (round(sum(mttr_seconds) / len(mttr_seconds), 2) if mttr_seconds else None),
        "duplicate_business_orders_blocked": duplicate_blocks,
        "ai_escalation_rate": (round(review_events / ai_tx_count, 4) if ai_tx_count else None),
        "human_touch_time_seconds": None,
        "human_touch_time_note": "Not measured until explicit operator work-session timestamps are captured.",
        "methodology": "All populated values are calculated from PostgreSQL transaction, approval, incident and event records.",
    }


async def transaction_decision_summary(session: AsyncSession, public_id: str) -> dict | None:
    from app.models.digital_twin import OrderLine, PolicyDecision, Checkpoint, IntegrationCircuit
    from app.services.business_order_service import duplicate_history
    tx = await session.scalar(select(Transaction).where(Transaction.public_id == public_id))
    if not tx:
        return None
    lines = (await session.execute(
        select(OrderLine).where(OrderLine.transaction_id == tx.id).order_by(OrderLine.line_number)
    )).scalars().all()
    price_lines = []
    requested_total = Decimal("0")
    executable_total = Decimal("0")
    for line in lines:
        qty = Decimal(line.quantity or 0)
        req = Decimal(line.requested_unit_price) if line.requested_unit_price is not None else None
        exe = Decimal(line.executable_unit_price) if line.executable_unit_price is not None else None
        req_total = (req * qty).quantize(Decimal("0.01")) if req is not None else None
        exe_total = (exe * qty).quantize(Decimal("0.01")) if exe is not None else None
        if req_total is not None:
            requested_total += req_total
        if exe_total is not None:
            executable_total += exe_total
        price_lines.append({
            "line_number": line.line_number,
            "requested_product_term": line.requested_product_term,
            "quantity": str(qty),
            "requested_unit_price": str(req) if req is not None else None,
            "executable_unit_price": str(exe) if exe is not None else None,
            "unit_difference": str((exe - req).quantize(Decimal("0.01"))) if req is not None and exe is not None else None,
            "requested_line_total": str(req_total) if req_total is not None else None,
            "executable_line_total": str(exe_total) if exe_total is not None else None,
            "line_impact": str((exe_total - req_total).quantize(Decimal("0.01"))) if req_total is not None and exe_total is not None else None,
            "fulfillment_status": line.fulfillment_status,
            "fulfillment_plan": line.fulfillment_plan,
        })

    policy = await session.scalar(
        select(PolicyDecision).where(PolicyDecision.transaction_id == tx.id).order_by(PolicyDecision.created_at.desc()).limit(1)
    )
    approvals = (await session.execute(
        select(Approval).where(Approval.transaction_id == tx.id).order_by(Approval.created_at)
    )).scalars().all()
    commands = (await session.execute(
        select(IntegrationCommand).where(IntegrationCommand.transaction_id == tx.id).order_by(IntegrationCommand.created_at)
    )).scalars().all()
    incidents = (await session.execute(
        select(Incident).where(Incident.transaction_id == tx.id).order_by(Incident.created_at)
    )).scalars().all()
    checkpoints = (await session.execute(
        select(Checkpoint).where(Checkpoint.transaction_id == tx.id).order_by(Checkpoint.created_at)
    )).scalars().all()

    duplicate_info = await duplicate_history(session, transaction=tx)
    policy_inputs = policy.inputs if policy else {}
    credit = {
        key: policy_inputs.get(key)
        for key in ["credit_limit", "current_exposure", "order_value", "projected_exposure", "over_limit_by"]
        if key in policy_inputs
    }
    return {
        "transaction": {
            "public_id": tx.public_id, "po_number": tx.customer_reference,
            "status": tx.status, "risk": tx.risk, "value": str(tx.value or 0), "currency": tx.currency,
            "correlation_id": tx.correlation_id, "version": tx.version,
        },
        "pricing": {
            "lines": price_lines,
            "requested_total": str(requested_total.quantize(Decimal("0.01"))),
            "executable_total": str(executable_total.quantize(Decimal("0.01"))),
            "total_difference": str((executable_total - requested_total).quantize(Decimal("0.01"))),
        },
        "credit": credit,
        "policy": {
            "original_outcome": policy.outcome if policy else None,
            "policy_name": policy.policy_name if policy else None,
            "policy_version": policy.policy_version if policy else None,
            "reasons": policy.reasons if policy else [],
            "required_approvers": policy.required_approvers if policy else [],
            "current_transaction_status": tx.status,
            "approvals": [
                {"role": a.approver_role, "status": a.status, "reason": a.reason,
                 "decided_by": a.decided_by, "decision_at": a.decision_at.isoformat() if a.decision_at else None}
                for a in approvals
            ],
        },
        "duplicates": duplicate_info,
        "integrations": [
            {"provider": c.provider, "action": c.action, "status": c.status,
             "external_id": c.external_id, "attempts": c.attempt_count,
             "error_category": c.error_category, "verified_at": c.verified_at.isoformat() if c.verified_at else None}
            for c in commands
        ],
        "recovery": {
            "incidents": [
                {"id": str(i.id), "category": i.category, "severity": i.severity, "status": i.status,
                 "message": i.message, "created_at": i.created_at.isoformat(),
                 "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None}
                for i in incidents
            ],
            "checkpoints": [
                {"step": c.step, "status": c.status, "verified": c.verified,
                 "side_effects": c.side_effects, "created_at": c.created_at.isoformat()}
                for c in checkpoints
            ],
            "safe_replay_notice": "Verified committed external side effects are never repeated; uncertain writes require reconciliation first.",
        },
    }

async def technical_metrics(session: AsyncSession) -> dict:
    """Operational counters from durable state plus bounded API latency samples."""
    from app.core.middleware import request_metrics_snapshot
    from app.models.automation import AutomationJob
    from app.models.digital_twin import ExternalSubscription, IntegrationCircuit

    async def grouped(model, column):
        rows = (await session.execute(select(column, func.count()).select_from(model).group_by(column))).all()
        return {str(key or "UNKNOWN"): int(count) for key, count in rows}

    job_status = await grouped(AutomationJob, AutomationJob.status)
    command_status = await grouped(IntegrationCommand, IntegrationCommand.status)
    job_errors = (await session.execute(
        select(AutomationJob.error_category, func.count())
        .where(AutomationJob.error_category.is_not(None))
        .group_by(AutomationJob.error_category)
    )).all()
    command_errors = (await session.execute(
        select(IntegrationCommand.error_category, func.count())
        .where(IntegrationCommand.error_category.is_not(None))
        .group_by(IntegrationCommand.error_category)
    )).all()
    circuits = (await session.execute(select(IntegrationCircuit))).scalars().all()
    subscriptions = (await session.execute(select(ExternalSubscription))).scalars().all()

    return {
        "request_latency": request_metrics_snapshot(),
        "automation_jobs_by_status": job_status,
        "integration_commands_by_status": command_status,
        "automation_errors_by_category": {str(k): int(v) for k, v in job_errors},
        "integration_errors_by_category": {str(k): int(v) for k, v in command_errors},
        "open_incidents": int(await session.scalar(
            select(func.count(Incident.id)).where(Incident.status == "OPEN")
        ) or 0),
        "circuits": [
            {
                "provider": c.provider,
                "state": c.state,
                "failure_count": c.failure_count,
                "last_error_category": c.last_error_category,
                "last_success_at": c.last_success_at.isoformat() if c.last_success_at else None,
                "half_open_after": c.half_open_after.isoformat() if c.half_open_after else None,
            }
            for c in circuits
        ],
        "external_subscriptions": [
            {
                "provider": s.provider,
                "status": s.status,
                "expires_at": s.expires_at.isoformat(),
                "delta_initialized": bool(s.delta_link),
                "last_delta_sync_at": s.last_delta_sync_at.isoformat() if s.last_delta_sync_at else None,
            }
            for s in subscriptions
        ],
        "note": "Latency samples are bounded in-process telemetry; durable job/command/incident values are PostgreSQL-backed.",
    }


async def release_readiness(session: AsyncSession) -> dict:
    """Evidence-backed readiness matrix.

    This endpoint deliberately separates IMPLEMENTED, CONFIGURED, OBSERVED and
    VERIFIED. It never upgrades a capability merely because a credential exists.
    """
    from pathlib import Path
    import json
    from app.models.automation import AutomationJob, VoiceChangeRequest
    from app.models.digital_twin import ExternalSubscription, PaymentRecord

    def item(status: str, evidence: str, *, owner_action: str | None = None) -> dict:
        return {"status": status, "evidence": evidence, "owner_action": owner_action}

    # Core database access is proven by reaching this point and issuing a query.
    transaction_count = await session.scalar(select(func.count(Transaction.id))) or 0
    verified_odoo = await session.scalar(
        select(func.count(IntegrationCommand.id)).where(
            IntegrationCommand.provider == "ODOO",
            IntegrationCommand.action == "CREATE_SALE_ORDER",
            IntegrationCommand.status == "VERIFIED",
        )
    ) or 0
    resolved_incidents = await session.scalar(
        select(func.count(Incident.id)).where(Incident.resolved_at.is_not(None))
    ) or 0
    n8n_jobs = await session.scalar(
        select(func.count(AutomationJob.id)).where(AutomationJob.requested_by == "N8N_INGRESS")
    ) or 0
    graph_subscription = await session.scalar(
        select(ExternalSubscription)
        .where(ExternalSubscription.provider == "MICROSOFT_GRAPH")
        .order_by(ExternalSubscription.expires_at.desc())
        .limit(1)
    )

    provider_counts = {}
    action_counts: dict[tuple[str, str, str], int] = {}
    rows = (await session.execute(
        select(IntegrationCommand.provider, IntegrationCommand.action, IntegrationCommand.status,
               func.count(IntegrationCommand.id))
        .where(IntegrationCommand.status.in_(["VERIFIED", "ACKNOWLEDGED"]))
        .group_by(IntegrationCommand.provider, IntegrationCommand.action, IntegrationCommand.status)
    )).all()
    for provider, action, status, count in rows:
        provider_key = str(provider).upper()
        provider_counts[provider_key] = provider_counts.get(provider_key, 0) + int(count)
        action_counts[(provider_key, str(action).upper(), str(status).upper())] = int(count)

    sharepoint_verified = action_counts.get(("MICROSOFT_GRAPH", "ARCHIVE_SHAREPOINT", "VERIFIED"), 0)
    outlook_draft_verified = action_counts.get(("MICROSOFT_GRAPH", "CREATE_OUTLOOK_DRAFT", "VERIFIED"), 0)
    teams_verified = action_counts.get(("TEAMS", "NOTIFY_TRANSACTION", "VERIFIED"), 0) + action_counts.get(("TEAMS", "NOTIFY_APPROVAL_REQUIRED", "VERIFIED"), 0)
    teams_acknowledged = action_counts.get(("TEAMS", "NOTIFY_TRANSACTION", "ACKNOWLEDGED"), 0) + action_counts.get(("TEAMS", "NOTIFY_APPROVAL_REQUIRED", "ACKNOWLEDGED"), 0)
    hubspot_verified = action_counts.get(("HUBSPOT", "SYNC_CUSTOMER", "VERIFIED"), 0)

    voice_reviews = await session.scalar(
        select(func.count(VoiceChangeRequest.id)).where(VoiceChangeRequest.status != "PENDING_VERIFICATION")
    ) or 0
    verified_payments = await session.scalar(
        select(func.count(PaymentRecord.id)).where(PaymentRecord.status == "PAID", PaymentRecord.verified_at.is_not(None))
    ) or 0

    reports = []
    report_dir = Path("/evals/reports")
    if report_dir.exists():
        for path in sorted(report_dir.glob("*.json")):
            try:
                obj = json.loads(path.read_text())
            except (OSError, ValueError, TypeError):
                continue
            if isinstance(obj, dict) and isinstance(obj.get("cases"), int):
                reports.append(obj)
    gated_reports = [r for r in reports if r.get("critical_gate_pass") is True]

    configured_graph = bool(settings.graph_client_id and settings.graph_client_secret and settings.graph_tenant_id and settings.graph_mailbox)
    configured_oidc = bool(settings.oidc_issuer and settings.oidc_audience and settings.oidc_jwks_url.startswith("https://"))

    capabilities = {
        "transaction_core": item(
            "VERIFIED_LOCAL" if transaction_count else "READY_FOR_FIRST_RUN",
            f"PostgreSQL reachable; stored transactions={transaction_count}.",
        ),
        "odoo_exactly_once": item(
            "VERIFIED_LOCAL" if verified_odoo else "IMPLEMENTED_NOT_VERIFIED",
            f"Verified Odoo create commands={verified_odoo}.",
            owner_action=None if verified_odoo else "Run one controlled Odoo create + replay test.",
        ),
        "recovery": item(
            "VERIFIED_LOCAL" if resolved_incidents else "IMPLEMENTED_NOT_VERIFIED",
            f"Resolved incidents={resolved_incidents}.",
            owner_action=None if resolved_incidents else "Run the scripted post-ERP failure/recovery scenario.",
        ),
        "n8n": item(
            "OBSERVED_LOCAL" if n8n_jobs else ("CONFIGURED_NOT_VERIFIED" if len(settings.n8n_ingest_secret) >= 32 else "NOT_CONFIGURED"),
            f"Durable jobs requested by n8n={n8n_jobs}; ingress secret configured={len(settings.n8n_ingest_secret) >= 32}.",
            owner_action=None if n8n_jobs else "Import/configure the inactive workflows and execute the duplicate-ingress acceptance test.",
        ),
        "microsoft_graph": item(
            "OBSERVED_LIVE_STATE" if graph_subscription else ("CONFIGURED_NOT_VERIFIED" if configured_graph else "NOT_CONFIGURED"),
            (f"Durable subscription status={graph_subscription.status}; delta initialized={bool(graph_subscription.delta_link)}."
             if graph_subscription else f"Graph credentials configured={configured_graph}; no durable subscription observed."),
            owner_action=None if graph_subscription else "Configure Entra + public HTTPS callbacks, then create/renew and test delta recovery.",
        ),
        "sharepoint": item(
            "VERIFIED_REMOTE" if sharepoint_verified else ("CONFIGURED_NOT_VERIFIED" if settings.graph_drive_id else "NOT_CONFIGURED"),
            f"Verified SharePoint archive commands={sharepoint_verified}.",
            owner_action=None if sharepoint_verified else "Grant Sites.Selected and verify remote byte/hash readback.",
        ),
        "hubspot": item(
            "VERIFIED_REMOTE" if hubspot_verified else ("CONFIGURED_NOT_VERIFIED" if settings.hubspot_access_token else "NOT_CONFIGURED"),
            f"Verified HubSpot customer-sync commands={hubspot_verified}.",
            owner_action=None if hubspot_verified else "Configure a sandbox/private app and run upsert + read-after-write acceptance.",
        ),
        "outlook": item(
            "VERIFIED_REMOTE" if outlook_draft_verified else ("CONFIGURED_NOT_VERIFIED" if configured_graph else "NOT_CONFIGURED"),
            f"Verified Outlook draft commands={outlook_draft_verified}; customer sending enabled={settings.customer_email_enabled}.",
            owner_action=None if outlook_draft_verified else "Create/read back an unsent draft with a controlled test recipient.",
        ),
        "teams": item(
            "VERIFIED_REMOTE" if teams_verified else ("OBSERVED_REMOTE_ACK" if teams_acknowledged else ("CONFIGURED_NOT_VERIFIED" if settings.teams_approval_webhook_url else "NOT_CONFIGURED")),
            f"Verified Teams display commands={teams_verified}; remote webhook acknowledgements={teams_acknowledged}.",
            owner_action=None if teams_verified else "Confirm the notification is visibly delivered in the target Teams channel; HTTP acknowledgement alone is not delivery proof.",
        ),
        "voice": item(
            "OBSERVED_LOCAL" if voice_reviews else ("CONFIGURED_NOT_VERIFIED" if len(settings.voice_server_secret) >= 32 else "NOT_CONFIGURED"),
            f"Reviewed voice change requests={voice_reviews}; server secret configured={len(settings.voice_server_secret) >= 32}.",
            owner_action="Complete a real Vapi/Twilio test call; local API evidence alone is not telephony verification.",
        ),
        "stripe_sandbox": item(
            "VERIFIED_REMOTE" if verified_payments else ("CONFIGURED_NOT_VERIFIED" if settings.stripe_enabled else "DISABLED"),
            f"Verified sandbox payments={verified_payments}; adapter enabled={settings.stripe_enabled}.",
            owner_action=None if verified_payments else "Use Stripe test mode and verify signed webhook amount/currency mapping.",
        ),
        "production_oidc": item(
            "CONFIGURED_NOT_VERIFIED" if configured_oidc else "NOT_CONFIGURED",
            f"OIDC configuration complete={configured_oidc}; configuration is not a login test.",
            owner_action="Configure a real IdP and run role-by-role JWT/RBAC acceptance before public deployment.",
        ),
        "ai_evaluation": item(
            "MEASURED_GATE_PASS" if gated_reports else ("MEASURED_NO_GATE_PASS" if reports else "NO_MEASURED_REPORT"),
            f"Measured reports={len(reports)}; critical-gate passing reports={len(gated_reports)}. Generated 500-case draft is not counted as curated evidence.",
            owner_action=None if gated_reports else "Human-curate the 500-case set, then run the repeatable evaluation suite and record actual results.",
        ),
    }

    completed = sum(1 for value in capabilities.values() if value["status"] in {
        "VERIFIED_LOCAL", "VERIFIED_REMOTE", "OBSERVED_LIVE_STATE", "MEASURED_GATE_PASS"
    })
    return {
        "capabilities": capabilities,
        "evidence_complete_count": completed,
        "capability_count": len(capabilities),
        "truth_boundary": (
            "IMPLEMENTED/CONFIGURED are not synonyms for VERIFIED. Remote providers require owner credentials and live acceptance."
        ),
    }
