from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.schemas.c2c import ManualOrderInput, ManualOrderLineInput
from app.services.business_order_service import normalize_po_number, order_content_fingerprint
from app.services.reliability import FailureCategory, classify_http_exception
import app.services.erp_service as erp
from app.integrations.microsoft_graph import MicrosoftGraph
from app.integrations.hubspot import HubSpot, CompanyUpsert


def sample_order(price=Decimal("260")):
    return ManualOrderInput(
        po_number="PO-88192",
        customer_hint="Northstar Engineering Ltd",
        currency="GBP",
        delivery_warehouse_code="MAN",
        lines=[ManualOrderLineInput(line_number=1, product_term="XTR-42", quantity=Decimal("40"), uom="EA", requested_unit_price=price)],
    )


def test_po_identity_normalizes_separator_variants():
    assert normalize_po_number(" PO-88192 ") == "PO88192"
    assert normalize_po_number("po 88192") == "PO88192"
    assert normalize_po_number("PO/88192") == "PO88192"


def test_order_fingerprint_is_stable_and_content_sensitive():
    a = order_content_fingerprint(sample_order())
    b = order_content_fingerprint(sample_order())
    c = order_content_fingerprint(sample_order(Decimal("261")))
    assert a == b and len(a) == 64 and a != c


def test_retry_classification_separates_auth_rate_and_uncertain_write():
    assert classify_http_exception(httpx.HTTPStatusError("auth", request=httpx.Request("GET", "https://x"), response=httpx.Response(401)), write_attempted=False).category == FailureCategory.AUTHENTICATION
    assert classify_http_exception(httpx.HTTPStatusError("rate", request=httpx.Request("GET", "https://x"), response=httpx.Response(429)), write_attempted=False).category == FailureCategory.RATE_LIMIT
    uncertain = classify_http_exception(httpx.ReadTimeout("lost response"), write_attempted=True)
    assert uncertain.category == FailureCategory.UNCERTAIN_REMOTE_STATE
    assert uncertain.remote_state_uncertain is True and uncertain.retryable is False


@pytest.mark.asyncio
async def test_business_identity_drives_cross_transaction_erp_idempotency_key(monkeypatch):
    customer_id = uuid4()
    identity = SimpleNamespace(customer_id=customer_id, normalized_po="PO88192", revision=1)
    monkeypatch.setattr(erp, "transaction_business_identity", AsyncMock(return_value=identity))
    key = await erp._erp_idempotency_key(SimpleNamespace(), SimpleNamespace(id=uuid4(), public_id="TXN-2026-999991"))
    assert key == f"odoo:create-sales-order:{customer_id}:PO88192:r1"


@pytest.mark.asyncio
async def test_graph_delta_follows_pages_and_returns_delta_token():
    calls=[]
    def handler(req):
        calls.append(str(req.url))
        if len(calls)==1:
            return httpx.Response(200,json={"value":[{"id":"M1"}],"@odata.nextLink":"https://mock.graph/v1.0/next"})
        return httpx.Response(200,json={"value":[{"id":"M2"}],"@odata.deltaLink":"https://mock.graph/v1.0/delta-token"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        async def token(): return "token"
        adapter=MicrosoftGraph(token_provider=token,client=client,base_url="https://mock.graph/v1.0")
        changes, delta_link=await adapter.message_delta(mailbox="sales@example.test",max_pages=3)
    assert [x["id"] for x in changes]==["M1","M2"]
    assert delta_link.endswith("delta-token") and len(calls)==2


@pytest.mark.asyncio
async def test_hubspot_company_upsert_uses_domain_identity():
    def handler(req):
        import json
        body=json.loads(req.content)
        assert req.url.path.endswith('/companies/batch/upsert')
        assert body['inputs'][0]['idProperty']=='domain'
        assert body['inputs'][0]['id']=='northstar.example'
        return httpx.Response(200,json={'results':[{'id':'COMPANY-1'}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result=await HubSpot(access_token='synthetic-test-only',client=client,base_url='https://mock.hubspot').upsert_company(
            CompanyUpsert(domain='northstar.example',name='Northstar Engineering Ltd'))
    assert result['results'][0]['id']=='COMPANY-1'
