"""Local portfolio demonstration operator gate, NOT production identity/RBAC.

Never trust `approver_role` or `actor_id` supplied by a browser. The configured
key maps to a server-side role, and all sensitive writes fail closed when no
key exists. For real deployment, replace with OAuth/OIDC/JWT verified identity.
"""
import hmac
import json
from dataclasses import dataclass

from fastapi import Header, HTTPException, status
from app.core.config import settings


@dataclass(frozen=True)
class DemoPrincipal:
    role: str
    actor_id: str


async def require_operator(x_ordernexa_operator_key: str | None = Header(default=None)) -> DemoPrincipal:
    if settings.app_env != "development":
        raise HTTPException(503, "Production identity provider not configured; sensitive actions are disabled.")
    entries: list[tuple[str, str]] = []
    if settings.ordernexa_role_keys_json:
        try:
            raw = json.loads(settings.ordernexa_role_keys_json)
            if not isinstance(raw, dict):
                raise ValueError("Expected role-to-key map")
            entries.extend((str(k), str(v)) for k, v in raw.items())
        except (TypeError, ValueError):
            raise HTTPException(503, "Invalid local operator role configuration.") from None
    if settings.ordernexa_operator_key:
        entries.append((settings.ordernexa_operator_role, settings.ordernexa_operator_key))
    entries = [(role, key) for role, key in entries
               if key and key != "CHANGE_ME" and len(key) >= 24]
    if not entries:
        raise HTTPException(503, "Set a securely generated operator key in the private .env file.")
    if not x_ordernexa_operator_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-OrderNexa-Operator-Key is required.")
    matches = [role for role, key in entries if hmac.compare_digest(x_ordernexa_operator_key, key)]
    if len(set(matches)) > 1:
        raise HTTPException(503, "Duplicate operator key assigned to conflicting roles.")
    if matches:
        role = matches[0]
        return DemoPrincipal(role=role, actor_id=f"LOCAL_DEMO_{role}")
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid local operator key.")
