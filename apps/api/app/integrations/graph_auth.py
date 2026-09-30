"""Confidential-client token provider for configured Microsoft Graph scopes."""
import asyncio
import time
import httpx
from app.core.config import settings

class GraphAuthError(RuntimeError):
    pass

_token: str | None = None
_expiry: float = 0
_lock = asyncio.Lock()


async def application_token() -> str:
    global _token, _expiry
    if not all((settings.graph_client_id, settings.graph_client_secret, settings.graph_tenant_id)):
        raise GraphAuthError('Microsoft Entra app credentials are not configured.')
    if _token and time.monotonic() < _expiry - 120:
        return _token
    async with _lock:
        if _token and time.monotonic() < _expiry - 120:
            return _token
        url = f'https://login.microsoftonline.com/{settings.graph_tenant_id}/oauth2/v2.0/token'
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(url, data={
                    'client_id': settings.graph_client_id,
                    'client_secret': settings.graph_client_secret,
                    'scope': 'https://graph.microsoft.com/.default',
                    'grant_type': 'client_credentials',
                })
                response.raise_for_status()
                body = response.json()
                _token = body['access_token']
                _expiry = time.monotonic() + max(120, int(body.get('expires_in', 3600)))
                return _token
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise GraphAuthError('Microsoft token request failed; check app permissions, secret and tenant.') from exc
