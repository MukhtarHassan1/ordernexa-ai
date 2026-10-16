from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.services.autonomy_service as autonomy


@pytest.mark.asyncio
async def test_disabled_policy_never_authorizes_machine_execution(monkeypatch):
    row = SimpleNamespace(level=2, enabled=False, allowed_risks=["LOW"], max_value=None, require_verified_evidence=True)
    session = SimpleNamespace(get=AsyncMock(return_value=row))
    monkeypatch.setattr(autonomy, "seed_default_autonomy_policies", AsyncMock(return_value=[]))
    decision = await autonomy.evaluate_autonomy(
        session, action="ARCHIVE_VERIFIED_DOCUMENT", risk="LOW", value=Decimal("10"),
        human_requested=False, evidence_verified=True,
    )
    assert decision == {"allowed": False, "reason": "AUTONOMY_DISABLED", "level": 2}


@pytest.mark.asyncio
async def test_policy_bounded_autonomy_enforces_risk_and_value(monkeypatch):
    row = SimpleNamespace(level=2, enabled=True, allowed_risks=["LOW"], max_value=Decimal("100"), require_verified_evidence=True)
    session = SimpleNamespace(get=AsyncMock(return_value=row))
    monkeypatch.setattr(autonomy, "seed_default_autonomy_policies", AsyncMock(return_value=[]))
    allowed = await autonomy.evaluate_autonomy(
        session, action="SYNC_CRM_ACTIVITY", risk="LOW", value=Decimal("99"),
        human_requested=False, evidence_verified=True,
    )
    blocked = await autonomy.evaluate_autonomy(
        session, action="SYNC_CRM_ACTIVITY", risk="HIGH", value=Decimal("99"),
        human_requested=False, evidence_verified=True,
    )
    assert allowed["allowed"] is True
    assert blocked["reason"] == "RISK_OUTSIDE_POLICY"
