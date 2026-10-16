"""OrderNexa identity boundary.

Development uses explicit role keys from the private .env so the local portfolio can
run without an external identity provider. Non-development environments fail
closed unless a signed OIDC JWT can be verified against the configured issuer
and JWKS. Browser supplied role/actor fields are never trusted.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Header, HTTPException, Request, status

from app.core.config import settings


INTERNAL_ROLES = {
    "OPERATOR",
    "SALES_MANAGER",
    "FINANCE_MANAGER",
    "OPERATIONS_MANAGER",
    "ADMIN",
    "AUDITOR",
}


@dataclass(frozen=True)
class DemoPrincipal:
    """Authenticated application principal.

    The historic name is retained to avoid breaking existing imports. In OIDC
    mode this represents a production identity, not a demo identity.
    """

    role: str
    actor_id: str
    auth_source: str = "LOCAL_KEY"


_jwks_cache: dict[str, Any] = {"value": None, "expires_at": 0.0}
_jwks_lock = asyncio.Lock()


def _local_key_principal(provided: str | None) -> DemoPrincipal:
    entries: list[tuple[str, str]] = []
    if settings.ordernexa_role_keys_json:
        try:
            raw = json.loads(settings.ordernexa_role_keys_json)
            if not isinstance(raw, dict):
                raise ValueError("Expected role-to-key map")
            entries.extend((str(k).upper(), str(v)) for k, v in raw.items())
        except (TypeError, ValueError, json.JSONDecodeError):
            raise HTTPException(503, "Invalid local operator role configuration.") from None
    if settings.ordernexa_operator_key:
        entries.append((settings.ordernexa_operator_role.upper(), settings.ordernexa_operator_key))

    entries = [
        (role, key)
        for role, key in entries
        if role in INTERNAL_ROLES and key and key != "CHANGE_ME" and len(key) >= 24
    ]
    if not entries:
        raise HTTPException(503, "Set securely generated local role keys in the private .env file.")
    if not provided:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-OrderNexa-Operator-Key is required.")

    matches = [role for role, key in entries if hmac.compare_digest(provided, key)]
    if len(set(matches)) > 1:
        raise HTTPException(503, "Duplicate operator key assigned to conflicting roles.")
    if matches:
        role = matches[0]
        return DemoPrincipal(role=role, actor_id=f"LOCAL_{role}", auth_source="LOCAL_KEY")
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid local operator key.")


def _oidc_role_map() -> dict[str, str]:
    if not settings.oidc_role_map_json:
        return {}
    try:
        raw = json.loads(settings.oidc_role_map_json)
        if not isinstance(raw, dict):
            raise ValueError
        mapped = {str(k).strip().lower(): str(v).upper() for k, v in raw.items()}
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(503, "OIDC_ROLE_MAP_JSON must be a JSON object.") from None
    invalid = [v for v in mapped.values() if v not in INTERNAL_ROLES]
    if invalid:
        raise HTTPException(503, "OIDC role map contains an unsupported OrderNexa role.")
    return mapped


def _select_internal_role(claim_value: Any) -> str:
    values: list[str]
    if isinstance(claim_value, str):
        values = [claim_value]
    elif isinstance(claim_value, list):
        values = [str(v) for v in claim_value if isinstance(v, (str, int))]
    else:
        values = []

    mapping = _oidc_role_map()
    candidates: list[str] = []
    for external in values:
        mapped = mapping.get(external.strip().lower())
        if mapped:
            candidates.append(mapped)
            continue
        direct = external.upper()
        if direct in INTERNAL_ROLES:
            candidates.append(direct)

    # Deterministic privilege selection is intentionally conservative: if a
    # token maps to several OrderNexa roles, configuration must resolve it.
    unique = sorted(set(candidates))
    if len(unique) != 1:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "OIDC identity must map to exactly one OrderNexa role.",
        )
    return unique[0]


def _oidc_urls() -> tuple[str, str]:
    issuer = settings.oidc_issuer.strip().rstrip("/")
    jwks_url = settings.oidc_jwks_url.strip()
    if not issuer or not settings.oidc_audience.strip() or not jwks_url.startswith("https://"):
        raise HTTPException(503, "OIDC issuer, audience and HTTPS JWKS URL must be configured.")
    return issuer, jwks_url


async def _get_jwks() -> dict:
    _, jwks_url = _oidc_urls()
    now = time.monotonic()
    cached = _jwks_cache.get("value")
    if isinstance(cached, dict) and now < float(_jwks_cache.get("expires_at", 0.0)):
        return cached

    async with _jwks_lock:
        now = time.monotonic()
        cached = _jwks_cache.get("value")
        if isinstance(cached, dict) and now < float(_jwks_cache.get("expires_at", 0.0)):
            return cached
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=3.0)) as client:
                response = await client.get(jwks_url, headers={"Accept": "application/json"})
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(503, "OIDC signing keys are temporarily unavailable.") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list) or not payload["keys"]:
            raise HTTPException(503, "OIDC JWKS response is invalid.")
        _jwks_cache["value"] = payload
        _jwks_cache["expires_at"] = now + max(60, settings.oidc_jwks_cache_seconds)
        return payload


async def authenticate_bearer_token(authorization: str | None) -> DemoPrincipal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer access token is required.")
    token = authorization[7:].strip()
    if not token or len(token) > 16_384:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid bearer access token.")

    try:
        import jwt
        from jwt import PyJWK
    except ImportError as exc:  # pragma: no cover - installation/config issue
        raise HTTPException(503, "OIDC support is not installed in this deployment.") from exc

    issuer, _ = _oidc_urls()
    allowed_algorithms = [
        a.strip() for a in settings.oidc_allowed_algorithms.split(",") if a.strip()
    ]
    if not allowed_algorithms or any(a.startswith("HS") or a.lower() == "none" for a in allowed_algorithms):
        raise HTTPException(503, "OIDC_ALLOWED_ALGORITHMS must contain only asymmetric algorithms.")

    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        alg = header.get("alg")
        if not isinstance(kid, str) or not kid or alg not in allowed_algorithms:
            raise ValueError("Unsupported JWT header")
        jwks = await _get_jwks()
        matching = [item for item in jwks["keys"] if isinstance(item, dict) and item.get("kid") == kid]
        if len(matching) != 1:
            # Key rotation may have occurred; force one refresh before rejecting.
            _jwks_cache["expires_at"] = 0.0
            jwks = await _get_jwks()
            matching = [item for item in jwks["keys"] if isinstance(item, dict) and item.get("kid") == kid]
        if len(matching) != 1:
            raise ValueError("Unknown JWT key id")
        key = PyJWK.from_dict(matching[0], algorithm=alg).key
        claims = jwt.decode(
            token,
            key=key,
            algorithms=allowed_algorithms,
            audience=settings.oidc_audience,
            issuer=issuer,
            options={"require": ["exp", "iat", "sub"]},
            leeway=max(0, settings.oidc_clock_skew_seconds),
        )
    except HTTPException:
        raise
    except Exception as exc:
        # Never return decoder internals or token material to the caller.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer access token verification failed.") from exc

    role = _select_internal_role(claims.get(settings.oidc_role_claim))
    actor = claims.get(settings.oidc_actor_claim) or claims.get("sub")
    if not isinstance(actor, str) or not actor or len(actor) > 240:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "OIDC token does not contain a usable actor identity.")
    return DemoPrincipal(role=role, actor_id=actor, auth_source="OIDC")


async def require_operator(
    request: Request,
    authorization: str | None = Header(default=None),
    x_ordernexa_operator_key: str | None = Header(default=None),
) -> DemoPrincipal:
    existing = getattr(request.state, "principal", None)
    if isinstance(existing, DemoPrincipal):
        return existing

    mode = settings.auth_mode.strip().lower()
    if mode not in {"auto", "local_keys", "oidc"}:
        raise HTTPException(503, "AUTH_MODE must be auto, local_keys or oidc.")
    if mode == "auto":
        mode = "local_keys" if settings.app_env == "development" else "oidc"

    if mode == "local_keys":
        if settings.app_env != "development":
            raise HTTPException(503, "Local-key authentication is disabled outside development.")
        principal = _local_key_principal(x_ordernexa_operator_key)
    else:
        principal = await authenticate_bearer_token(authorization)

    request.state.principal = principal
    return principal
