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


@dataclass(frozen=True)
class CompanyUpsert:
    domain: str
    name: str


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


    async def upsert_company(self, value: CompanyUpsert) -> dict:
        if not self.access_token:
            raise HubSpotIntegrationError("HubSpot token not configured.")
        domain = value.domain.strip().lower()
        if not domain or "." not in domain or "/" in domain or "@" in domain:
            raise ValueError("A canonical customer domain is required for company deduplication.")
        client = self._client or httpx.AsyncClient(timeout=20)
        try:
            res = await client.post(
                self.base_url + "/crm/v3/objects/companies/batch/upsert",
                headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"},
                json={"inputs": [{
                    "id": domain, "idProperty": "domain",
                    "properties": {"domain": domain, "name": value.name},
                }]},
            )
            res.raise_for_status()
            return res.json()
        except httpx.HTTPStatusError as exc:
            raise HubSpotIntegrationError(f"HubSpot company upsert returned HTTP {exc.response.status_code}.") from exc
        except httpx.RequestError as exc:
            raise HubSpotIntegrationError("HubSpot company transport unavailable.") from exc
        finally:
            if self._client is None:
                await client.aclose()

    async def get_company(self, company_id: str) -> dict:
        if not self.access_token or not company_id:
            raise HubSpotIntegrationError("Configured token and company ID are required.")
        if not company_id.isdigit():
            raise ValueError("HubSpot company ID must be numeric.")
        client = self._client or httpx.AsyncClient(timeout=20)
        try:
            response = await client.get(
                self.base_url + "/crm/v3/objects/companies/" + company_id + "?properties=name,domain",
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise HubSpotIntegrationError("Company read-after-write verification failed.") from exc
        finally:
            if self._client is None:
                await client.aclose()

    async def search_contact_by_email(self, email: str) -> list[dict]:
        """Read-only reconciliation path for an uncertain contact upsert."""
        if not self.access_token or not email or "@" not in email:
            raise ValueError("Verified email is required for HubSpot reconciliation.")
        client = self._client or httpx.AsyncClient(timeout=20)
        try:
            response = await client.post(
                self.base_url + "/crm/v3/objects/contacts/search",
                headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"},
                json={
                    "filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}],
                    "properties": ["email", "company"],
                    "limit": 10,
                },
            )
            response.raise_for_status()
            results = response.json().get("results") or []
            return [item for item in results if isinstance(item, dict)]
        except httpx.HTTPError as exc:
            raise HubSpotIntegrationError("HubSpot contact reconciliation search failed.") from exc
        finally:
            if self._client is None:
                await client.aclose()
