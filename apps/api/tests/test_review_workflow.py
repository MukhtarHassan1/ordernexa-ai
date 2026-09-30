"""Offline regression: stored originals, secure review and download invariants."""
import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services import intake_service as service
from app.api.routes import intake as routes


def item(payload: bytes, name='po.txt'):
    return SimpleNamespace(
        id=uuid4(), object_key='intake/test/original',
        sha256=hashlib.sha256(payload).hexdigest(),
        original_name=name,
    )


@pytest.mark.asyncio
async def test_verified_original_matches_checksum(monkeypatch):
    doc=b'TEST FIXTURE ORIGINAL PO'
    monkeypatch.setattr(service.object_storage,'get_bytes',AsyncMock(return_value=doc))
    assert await service.get_verified_original_bytes(item(doc)) == doc


@pytest.mark.asyncio
async def test_corrupted_original_is_rejected_before_review(monkeypatch):
    doc=b'TEST FIXTURE ORIGINAL PO'
    monkeypatch.setattr(service.object_storage,'get_bytes',AsyncMock(return_value=doc+b'tampered'))
    with pytest.raises(ValueError, match='checksum mismatch'):
        await service.get_verified_original_bytes(item(doc))


@pytest.mark.asyncio
async def test_oversize_saved_original_is_rejected(monkeypatch):
    doc=b'synthetic'
    monkeypatch.setattr(service.object_storage,'get_bytes',AsyncMock(return_value=doc))
    monkeypatch.setattr(service.settings,'max_upload_bytes',3)
    with pytest.raises(ValueError, match='upload limit'):
        await service.get_verified_original_bytes(item(doc))


@pytest.mark.asyncio
async def test_original_download_enforces_review_role():
    with pytest.raises(HTTPException) as exc:
        await routes.download_saved_original(
            uuid4(), db=object(),
            principal=SimpleNamespace(role='AUDITOR'),
        )
    assert exc.value.status_code==403


@pytest.mark.asyncio
async def test_original_download_is_attachment_with_safety_headers(monkeypatch):
    doc=b'SYNTHETIC TEST SOURCE'
    saved=item(doc, name='../../unsafe\"name.txt')
    monkeypatch.setattr(routes,'get_original_artifact',AsyncMock(return_value=saved))
    monkeypatch.setattr(routes,'get_verified_original_bytes',AsyncMock(return_value=doc))
    r=await routes.download_saved_original(
        saved.id, db=object(),
        principal=SimpleNamespace(role='SALES_MANAGER'),
    )
    assert r.body==doc
    assert r.headers['x-content-type-options']=='nosniff'
    assert r.headers['cache-control']=='private, no-store'
    assert r.headers['content-disposition'].startswith('attachment; filename=')
    assert 'unsafe' in r.headers['content-disposition']
    assert '"name' not in r.headers['content-disposition']


@pytest.mark.asyncio
async def test_manual_preview_never_uses_corrupted_original(monkeypatch):
    doc=b'SYNTHETIC TEST SOURCE'
    saved=item(doc)
    monkeypatch.setattr(routes,'get_original_artifact',AsyncMock(return_value=saved))
    monkeypatch.setattr(routes,'get_verified_original_bytes',AsyncMock(side_effect=ValueError('Saved original checksum mismatch')))
    with pytest.raises(HTTPException) as exc:
        await routes.human_preview(
            saved.id, db=object(),principal=SimpleNamespace(role='SALES_MANAGER'),
        )
    assert exc.value.status_code==422
    assert exc.value.detail['code']=='INVALID_REVIEW'

def test_review_http_contract_is_actionable_and_fail_closed():
    exc=service.DocumentNeedsReview('Conflicting PO number.',{
        'artifact_id':'550e8400-e29b-41d4-a716-446655440000',
        'manual_review_available':True,
        'review_flags':['REVIEW_REQUIRED_SOURCE_CONFLICT_PO_NUMBER'],
    })
    result=routes._translate(exc)
    assert result.status_code==422
    assert result.detail['workflow_state']=='NEEDS_HUMAN_REVIEW'
    assert result.detail['artifact_id']==exc.details['artifact_id']
    assert '/preview' in result.detail['next_step']
    assert result.detail['details']['review_flags']


@pytest.mark.asyncio
async def test_human_preview_enforces_review_role():
    with pytest.raises(HTTPException) as exc:
        await routes.human_preview(
            uuid4(), db=object(), principal=SimpleNamespace(role='AUDITOR'),
        )
    assert exc.value.status_code==403
