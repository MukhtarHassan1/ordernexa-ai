import pytest
from fastapi import HTTPException
from app.core.security import require_operator
import app.core.security as security


@pytest.mark.asyncio
async def test_local_operator_roles_come_from_private_server_config(monkeypatch):
    monkeypatch.setattr(security.settings,'app_env','development')
    monkeypatch.setattr(security.settings,'ordernexa_role_keys_json','{"SALES_MANAGER":"test-key-for-sales-manager-12345"}')
    monkeypatch.setattr(security.settings,'ordernexa_operator_key','')
    principal=await require_operator('test-key-for-sales-manager-12345')
    assert principal.role=='SALES_MANAGER'
    assert principal.actor_id=='LOCAL_DEMO_SALES_MANAGER'
    with pytest.raises(HTTPException) as exc:
        await require_operator('wrong')
    assert exc.value.status_code==403


@pytest.mark.asyncio
async def test_deployment_fail_closed_without_real_identity(monkeypatch):
    monkeypatch.setattr(security.settings,'app_env','production')
    with pytest.raises(HTTPException) as exc:
        await require_operator('test-key-for-sales-manager-12345')
    assert exc.value.status_code==503
