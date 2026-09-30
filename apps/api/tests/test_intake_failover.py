"""Prove failed local AI does not lose or duplicate the original source."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.ai_gateway import AIProviderError
from app.services.document_intelligence import DocumentContent
import app.services.intake_service as intake


def stub_session():
    return SimpleNamespace(
        scalar=AsyncMock(return_value=None), add=MagicMock(),
        commit=AsyncMock(), rollback=AsyncMock(), refresh=AsyncMock(),
        get=AsyncMock(), execute=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_inference_failure_retains_original_and_returns_artifact_id(monkeypatch):
    session=stub_session();original=[]
    async def refresh(obj):
        if not getattr(obj,'id',None):obj.id=uuid4()
        original.append(obj)
    session.refresh.side_effect=refresh
    async def get(cls,ref):return original[0]
    session.get.side_effect=get
    store=AsyncMock()
    monkeypatch.setattr(intake.object_storage,'put_bytes',store)
    monkeypatch.setattr(intake,'extract_document',lambda **kw:DocumentContent(
        text='SYNTHETIC PO',images=[],extraction_method='TEXT',page_count=1))
    monkeypatch.setattr(intake,'extract_order_draft',AsyncMock(side_effect=AIProviderError(
        'MODEL_TIMEOUT','synthetic model runner did not generate')))
    with pytest.raises(AIProviderError) as exc:
        await intake.ingest_order_file(session,filename='PO.txt',content_type='text/plain',data=b'SYNTHETIC PO')
    assert exc.value.code=='MODEL_TIMEOUT'
    assert exc.value.artifact_id==original[0].id
    assert original[0].extra_data['status']=='AI_UNAVAILABLE'
    assert store.await_count==1
    assert session.rollback.await_count==1


@pytest.mark.asyncio
async def test_retried_orphan_does_not_write_second_source(monkeypatch):
    original=SimpleNamespace(
        id=uuid4(), sha256=__import__('hashlib').sha256(b'SYNTHETIC PO').hexdigest(),
        object_key='intake/saved/original.txt', transaction_id=None,
        original_name='PO.txt',mime_type='text/plain',
        storage_provider='MINIO',artifact_type='ORIGINAL_DOCUMENT',extra_data={'status':'AI_UNAVAILABLE'},
    )
    session=stub_session(); session.get.return_value=original
    monkeypatch.setattr(intake.object_storage,'exists',AsyncMock(return_value=True))
    store=AsyncMock()
    monkeypatch.setattr(intake.object_storage,'put_bytes',store)
    monkeypatch.setattr(intake,'extract_document',lambda **kw: DocumentContent(
        text='SYNTHETIC PO',images=[],extraction_method='TEXT',page_count=1))
    monkeypatch.setattr(intake,'extract_order_draft',AsyncMock(side_effect=AIProviderError(
        'MODEL_TIMEOUT','synthetic model runner did not generate')))
    with pytest.raises(AIProviderError) as exc:
        await intake.ingest_order_file(session,filename='PO.txt',content_type='text/plain',
                                       data=b'SYNTHETIC PO',existing_artifact_id=original.id)
    assert exc.value.artifact_id==original.id
    assert original.extra_data['status']=='AI_UNAVAILABLE'
    assert store.await_count==0
