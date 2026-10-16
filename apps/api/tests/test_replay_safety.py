"""Service-level replay/failure tests with external transport mocked.

They establish code behavior, not an independently verified live Odoo database.
"""
import json
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import app.services.erp_service as erp
import app.services.recovery_service as recovery
from app.models.enums import TransactionStatus


def fake_session():
    s=SimpleNamespace()
    s.scalar=AsyncMock()
    s.get=AsyncMock()
    s.execute=AsyncMock()
    s.flush=AsyncMock()
    s.commit=AsyncMock()
    s.refresh=AsyncMock()
    s.add=MagicMock()
    return s


@pytest.mark.asyncio
async def test_uncertain_erp_response_verifies_original_before_any_post(monkeypatch):
    tid=uuid4();pub='TXN-2026-778899';key=f'odoo:create-sales-order:{pub}'
    transaction=SimpleNamespace(id=tid,customer_id=uuid4(),public_id=pub,customer_reference='TEST-PO',
                                currency='GBP',status=TransactionStatus.ERP_PENDING.value)
    customer=SimpleNamespace(id=uuid4(),code='CUST-1001',name='Synthetic Customer')
    line=SimpleNamespace(line_number=1,quantity=Decimal('2'),executable_unit_price=Decimal('17.00'))
    product=SimpleNamespace(sku='XTR-420')
    payload={'transaction_id':pub,'idempotency_key':key,'po_number':'TEST-PO','business_order_key':key,
             'customer_code':customer.code,'customer_name':customer.name,'currency':'GBP',
             'lines':[{'line_number':1,'sku':'XTR-420','quantity':'2','unit_price':'17.00'}]}
    cmd=SimpleNamespace(status='FAILED_RETRYABLE',attempt_count=1,request_payload=payload,
                        response_payload={},idempotency_key=key,external_id=None)
    session=fake_session()
    session.scalar.side_effect=[transaction,cmd]
    session.get.return_value=customer
    rows=MagicMock();rows.all.return_value=[(line,product)]
    session.execute.return_value=rows
    session.refresh.return_value=None
    url_calls=[]
    def handler(req):
        url_calls.append((req.method,req.url.path))
        if req.method=='GET':
            return httpx.Response(200,json={'id':201,'name':'SO201','state':'sale'})
        return httpx.Response(500,json={'error':'POST SHOULD NEVER OCCUR ON VERIFIED REPLAY'})
    original=httpx.AsyncClient
    monkeypatch.setattr(erp.httpx,'AsyncClient',lambda **kw: original(transport=httpx.MockTransport(handler),**kw))
    monkeypatch.setattr(erp.settings,'ordernexa_odoo_shared_secret','synthetic-credential-only')
    monkeypatch.setattr(erp,'transaction_business_identity',AsyncMock(return_value=None))
    async def adv(session,transaction,request):
        transaction.status=request.target_status
        return transaction
    monkeypatch.setattr(erp,'advance_transaction',adv)
    result=await erp.execute_erp_order(session,public_id=pub)
    assert result.replayed is True and result.external_id=='201'
    assert len(url_calls)==1 and url_calls[0][0]=='GET'
    assert transaction.status=='ERP_CREATED'
    assert cmd.status=='VERIFIED'


@pytest.mark.asyncio
async def test_changed_payload_blocks_replay(monkeypatch):
    tid=uuid4();pub='TXN-2026-778900'
    transaction=SimpleNamespace(id=tid,customer_id=uuid4(),public_id=pub,customer_reference='TEST-PO',
                                currency='GBP',status=TransactionStatus.ERP_PENDING.value)
    cmd=SimpleNamespace(status='FAILED_RETRYABLE',attempt_count=1,
                        request_payload={'tampered':'changed'},
                        idempotency_key=f'odoo:create-sales-order:{pub}',external_id=None)
    session=fake_session()
    session.scalar.side_effect=[transaction,cmd]
    session.get.return_value=SimpleNamespace(id=uuid4(),code='CUST-1001',name='Synthetic Customer')
    line=SimpleNamespace(line_number=1,quantity=Decimal('2'),executable_unit_price=Decimal('17.00'))
    product=SimpleNamespace(sku='XTR-420')
    rows=MagicMock();rows.all.return_value=[(line,product)]
    session.execute.return_value=rows
    monkeypatch.setattr(erp,'transaction_business_identity',AsyncMock(return_value=None))
    with pytest.raises(ValueError,match='payload changed'):
        await erp.execute_erp_order(session,public_id=pub)
    assert not session.commit.await_count


@pytest.mark.asyncio
async def test_existing_valid_minio_archive_is_reused(monkeypatch):
    tid=uuid4();pub='TXN-2026-778901';oid='201'
    transaction=SimpleNamespace(id=tid,public_id=pub,status='ERP_CREATED',
                                customer_reference='TEST-PO',value=Decimal('35'),currency='GBP')
    cmd=SimpleNamespace(attempt_count=1,status='PENDING',request_payload={},response_payload={})
    session=fake_session();session.scalar.side_effect=[transaction,cmd]
    incidents=MagicMock();incidents.scalars.return_value.all.return_value=[]
    session.execute.return_value=incidents
    async def external_id(session,transaction_id):return (oid,{'name':'SO201'})
    monkeypatch.setattr(recovery,'_get_erp_external_id',external_id)
    monkeypatch.setattr(recovery.object_storage,'exists',AsyncMock(return_value=True))
    monkeypatch.setattr(recovery.object_storage,'get_bytes',AsyncMock(return_value=json.dumps({
        'transaction_id':pub,'erp':{'external_id':oid},
    }).encode()))
    put=AsyncMock()
    monkeypatch.setattr(recovery.object_storage,'put_json',put)
    async def advance(session,transaction,request):
        transaction.status=request.target_status
        return transaction
    monkeypatch.setattr(recovery,'advance_transaction',advance)
    result=await recovery.archive_and_complete(session,public_id=pub)
    assert result.status=='COMPLETED'
    assert put.await_count==0
    assert cmd.status=='VERIFIED'


@pytest.mark.asyncio
async def test_real_minio_failure_becomes_degraded_incident_not_duplicate_erp(monkeypatch):
    tid=uuid4();pub='TXN-2026-778902'
    transaction=SimpleNamespace(id=tid,public_id=pub,status='ERP_CREATED',
                                customer_reference='TEST-PO',value=Decimal('35'),currency='GBP')
    session=fake_session();session.scalar.side_effect=[transaction,None]
    session.refresh.side_effect=lambda obj: setattr(obj,'id',uuid4())
    async def external_id(session,transaction_id):return ('202',{'name':'SO202'})
    monkeypatch.setattr(recovery,'_get_erp_external_id',external_id)
    monkeypatch.setattr(recovery.object_storage,'exists',AsyncMock(return_value=False))
    monkeypatch.setattr(recovery.object_storage,'put_json',AsyncMock(side_effect=OSError('synthetic outage')))
    async def advance(session,transaction,request):
        transaction.status=request.target_status
        return transaction
    monkeypatch.setattr(recovery,'advance_transaction',advance)
    result=await recovery.archive_and_complete(session,public_id=pub)
    assert result.status=='DEGRADED'
    assert result.incident_id is not None
    assert transaction.status=='DEGRADED'
    assert all(call.args[0].__class__.__name__!='AIDecision' for call in session.add.call_args_list)
