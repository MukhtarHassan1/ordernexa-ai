from decimal import Decimal

from pydantic import BaseModel


class OperationsOverview(BaseModel):
    total_transactions: int

    completed_transactions: int

    approval_required: int

    degraded_transactions: int

    pending_approvals: int

    open_incidents: int

    verified_erp_orders: int

    ai_decisions: int

    total_order_value: Decimal

    blocked_revenue: Decimal

    pricing_discrepancies_prevented: int


class DependencyHealth(BaseModel):
    name: str

    status: str

    detail: str | None = None


class IntegrationHealthResponse(
    BaseModel
):
    dependencies: list[
        DependencyHealth
    ]