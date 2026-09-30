"""Opt-in HubSpot contact adapter; not active without real OAuth/private app access.

Do not transmit sensitive customer information to an unconfigured account.
Calls are explicit, never triggered by unvalidated AI document output.
"""
from dataclasses import dataclass
import httpx


class HubSpotIntegrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ContactUpsert:
    email: str
    company: str
    firstname: str = ""
    lastname: str = ""


class HubSpot:
    def __init__(self, *, access_token: str, client: httpx.AsyncClient | None = None,
                 base_url: str = "https://api.hubapi.com"):
        self.access_token = access_token
        self._client = client
        self.base_url = base_url.rstrip("/")

    async def upsert_contact(self, value: ContactUpsert) -> dict:
        if not self.access_token:
            raise HubSpotIntegrationError("HubSpot token not configured.")
        if not value.email or "@" not in value.email:
            raise ValueError("Contact email is required for idempotent upsert.")
        client = self._client or httpx.AsyncClient(timeout=20)
        try:
            res = await client.post(
                self.base_url + "/crm/v3/objects/contacts/batch/upsert",
                headers={"Authorization": f"Bearer {self.access_token}",
                         "Content-Type": "application/json"},
                json={"inputs": [{"id": value.email, "idProperty": "email",
                                  "properties": {"email": value.email,
                                                 "company": value.company,
                                                 "firstname": value.firstname,
                                                 "lastname": value.lastname}}]},
            )
            res.raise_for_status()
            return res.json()
        except httpx.HTTPStatusError as exc:
            raise HubSpotIntegrationError(f"HubSpot returned HTTP {exc.response.status_code}.") from exc
        except httpx.RequestError as exc:
            raise HubSpotIntegrationError("HubSpot transport unavailable.") from exc
        finally:
            if self._client is None:
                await client.aclose()

    async def get_contact(self, contact_id: str) -> dict:
        if not self.access_token or not contact_id:
            raise HubSpotIntegrationError('Configured token and contact ID are required.')
        if not contact_id.isdigit():
            raise ValueError('HubSpot contact ID must be numeric; do not accept arbitrary URL segments.')
        client = self._client or httpx.AsyncClient(timeout=20)
        try:
            response = await client.get(
                self.base_url + '/crm/v3/objects/contacts/' + httpx.URL('/' + contact_id).path.lstrip('/') +
                '?properties=email,company',
                headers={'Authorization': f'Bearer {self.access_token}'},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise HubSpotIntegrationError('Contact read-after-write verification failed.') from exc
        finally:
            if self._client is None:
                await client.aclose()
