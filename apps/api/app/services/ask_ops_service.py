"""Read-only operations assistant over approved, parameterized queries.

No model-generated SQL is executed. This is intentionally a constrained tool
router so the natural-language layer cannot acquire write authority.
"""
from __future__ import annotations

import re
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.digital_twin import Approval, Incident, IntegrationCommand
from app.models.transaction import Transaction
from app.services.ops_service import business_kpis, transaction_decision_summary

_TXN = re.compile(r"\bTXN-\d{4}-\d{6}\b", re.I)


async def answer_ops_question(session: AsyncSession, question: str) -> dict:
    q = " ".join(question.strip().split())
    if not q or len(q) > 500:
        raise ValueError("Question must contain 1-500 characters.")
    match = _TXN.search(q)
    if match:
        txn = match.group(0).upper()
        summary = await transaction_decision_summary(session, txn)
        if not summary:
            return {"answer": f"No stored transaction matches {txn}.", "tool": "transaction_decision_summary", "data": None}
        return {"answer": f"Stored transaction {txn} is {summary['transaction']['status']}. See the structured evidence below.",
                "tool": "transaction_decision_summary", "data": summary}

    lower = q.lower()
    if any(term in lower for term in ["blocked", "awaiting approval", "exceptions", "revenue awaiting"]):
        rows = (await session.execute(
            select(Transaction.public_id, Transaction.status, Transaction.value, Transaction.currency)
            .where(Transaction.status.in_(["APPROVAL_REQUIRED", "WAITING_CUSTOMER", "DUPLICATE_REVIEW", "DEGRADED", "BLOCKED_UNCERTAIN", "FAILED_RETRYABLE", "FAILED_MANUAL", "RECOVERY_PENDING"]))
            .order_by(Transaction.created_at.desc()).limit(50)
        )).all()
        value = sum((r.value or 0) for r in rows)
        return {"answer": f"{len(rows)} stored transactions are currently blocked or require intervention; recorded value is {value} across their native currencies.",
                "tool": "blocked_transactions", "data": [{"public_id": r.public_id, "status": r.status, "value": str(r.value or 0), "currency": r.currency} for r in rows]}

    if any(term in lower for term in ["integration", "failure", "incident", "recovery"]):
        incidents = (await session.execute(select(Incident).where(Incident.status == "OPEN").order_by(Incident.created_at.desc()).limit(50))).scalars().all()
        failed = await session.scalar(select(func.count(IntegrationCommand.id)).where(IntegrationCommand.status.in_(["FAILED", "FAILED_RETRYABLE", "FAILED_MANUAL", "BLOCKED_UNCERTAIN"]))) or 0
        return {"answer": f"There are {len(incidents)} open incidents and {failed} integration commands in failure/uncertain states.",
                "tool": "integration_incidents", "data": [{"category": x.category, "severity": x.severity, "message": x.message} for x in incidents]}

    if any(term in lower for term in ["kpi", "cycle time", "straight-through", "automation rate", "duplicate"]):
        kpis = await business_kpis(session)
        return {"answer": "These are database-backed OrderNexa KPIs. Null values mean the system does not yet store enough evidence to calculate that metric.",
                "tool": "business_kpis", "data": kpis}

    if "approval" in lower:
        pending = await session.scalar(select(func.count(Approval.id)).where(Approval.status == "PENDING")) or 0
        return {"answer": f"There are {pending} pending approval decisions in the authoritative database.", "tool": "pending_approvals", "data": {"pending": pending}}

    return {"answer": "I can answer read-only questions about a TXN reference, blocked transactions, approvals, integration incidents/recovery, or business KPIs. No arbitrary SQL or write tool is available.",
            "tool": "capabilities", "data": None}
