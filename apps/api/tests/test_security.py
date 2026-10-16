import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.core.security as security


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/api/v1/ops", "headers": [], "query_string": b"", "server": ("testserver", 80), "client": ("testclient", 50000), "scheme": "http"})


@pytest.mark.asyncio
async def test_local_operator_roles_come_from_private_server_config(monkeypatch):
    monkeypatch.setattr(security.settings, "app_env", "development")
    monkeypatch.setattr(security.settings, "auth_mode", "local_keys")
    monkeypatch.setattr(security.settings, "ordernexa_role_keys_json", '{"SALES_MANAGER":"test-key-for-sales-manager-12345"}')
    monkeypatch.setattr(security.settings, "ordernexa_operator_key", "")

    principal = await security.require_operator(_request(), x_ordernexa_operator_key="test-key-for-sales-manager-12345")
    assert principal.role == "SALES_MANAGER"
    assert principal.actor_id == "LOCAL_SALES_MANAGER"
    assert principal.auth_source == "LOCAL_KEY"

    with pytest.raises(HTTPException) as exc:
        await security.require_operator(_request(), x_ordernexa_operator_key="wrong")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_deployment_fail_closed_without_real_identity(monkeypatch):
    monkeypatch.setattr(security.settings, "app_env", "production")
    monkeypatch.setattr(security.settings, "auth_mode", "auto")
    monkeypatch.setattr(security.settings, "oidc_issuer", "")
    monkeypatch.setattr(security.settings, "oidc_audience", "")
    monkeypatch.setattr(security.settings, "oidc_jwks_url", "")

    with pytest.raises(HTTPException) as exc:
        await security.require_operator(_request(), authorization=None)
    assert exc.value.status_code in {401, 503}


def test_oidc_role_map_is_case_insensitive_and_exactly_one(monkeypatch):
    monkeypatch.setattr(security.settings, "oidc_role_map_json", '{"Sales.Approvers":"SALES_MANAGER"}')
    assert security._select_internal_role(["sales.approvers"]) == "SALES_MANAGER"


def test_oidc_multiple_internal_roles_are_rejected(monkeypatch):
    monkeypatch.setattr(security.settings, "oidc_role_map_json", '{"sales":"SALES_MANAGER","finance":"FINANCE_MANAGER"}')
    with pytest.raises(HTTPException) as exc:
        security._select_internal_role(["sales", "finance"])
    assert exc.value.status_code == 403
