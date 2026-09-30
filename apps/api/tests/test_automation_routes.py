"""Mocked HTTP/webhook contracts (no real PostgreSQL or remote accounts)."""
import importlib
import sys
import types
import asyncio
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.automation.contracts import ReconcileRequest
from app.automation.outlook_release import validate_draft, DraftReleaseRejected


@pytest.fixture
def isolated_route(monkeypatch):
    # Stub ONLY the database dependency import, not route behavior. No SQL is
    # executed by the ingress checks under test.
    stub = types.ModuleType('app.db.session')
    async def get_db():
        yield object()
    stub.get_db = get_db
    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, 'app.db.session', stub)
        sys.modules.pop('app.api.routes.automation', None)
        routes = importlib.import_module('app.api.routes.automation')
        app = FastAPI()
        app.include_router(routes.router, prefix='/api/v1')
        yield routes, TestClient(app)
    sys.modules.pop('app.api.routes.automation', None)


def test_graph_validation_handshake_uses_plain_text(isolated_route):
    _, client = isolated_route
    response = client.post('/api/v1/automation/graph/notifications?validationToken=opaque-123')
    assert response.status_code == 200
    assert response.text == 'opaque-123'
    assert 'text/plain' in response.headers['content-type']
    response = client.post('/api/v1/automation/graph/lifecycle?validationToken=opaque-456')
    assert response.status_code == 200 and response.text == 'opaque-456'


def test_webhook_rejects_unconfigured_subscription(isolated_route, monkeypatch):
    routes, client = isolated_route
    monkeypatch.setattr(routes.settings, 'graph_subscription_id', '')
    response = client.post('/api/v1/automation/graph/notifications', json={'value': []})
    assert response.status_code == 503


def test_graph_rejects_invalid_clientstate_and_accepts_configured_created(isolated_route, monkeypatch):
    routes, client = isolated_route
    s = 'long-unique-client-state-at-least-32-chars'
    monkeypatch.setattr(routes.settings, 'graph_subscription_id', 'configured-sub')
    monkeypatch.setattr(routes.settings, 'graph_client_state', s)
    monkeypatch.setattr(routes.settings, 'graph_mailbox', 'demo@example.invalid')
    publish = AsyncMock(return_value=(object(),True))
    monkeypatch.setattr(routes, 'publish_job', publish)
    bad = {'subscriptionId':'configured-sub','clientState':'wrong','changeType':'created',
           'resourceData':{'id':'message-1'}}
    response = client.post('/api/v1/automation/graph/notifications', json={'value':[bad]})
    assert response.status_code == 202 and response.headers['x-queued-count'] == '0'
    publish.assert_not_called()
    bad['clientState'] = s
    response = client.post('/api/v1/automation/graph/notifications', json={'value':[bad]})
    assert response.status_code == 202 and response.headers['x-queued-count'] == '1'
    assert publish.await_count == 1


def test_n8n_denies_missing_header_before_object_storage(isolated_route):
    _, client = isolated_route
    response = client.post('/api/v1/automation/n8n/intake', json={'event_id':'event-1234','body_text':'PO'})
    assert response.status_code == 403


def test_voice_endpoint_denies_missing_integration_secret(isolated_route):
    _, client = isolated_route
    response = client.get('/api/v1/automation/voice/status/TXN-2026-000001')
    assert response.status_code == 403


def test_outlook_draft_must_be_unsent_and_single_correct_recipient():
    sample = {'id':'draft-id','isDraft':True, 'subject':'Approved subject',
              'body':{'contentType':'text','content':'Approved message text'},
              'toRecipients':[{'emailAddress':{'address':'human@example.invalid'}}],
              'ccRecipients':[],'bccRecipients':[]}
    result = validate_draft(sample, draft_id='draft-id', subject='Approved subject', recipient='human@example.invalid')
    assert result['preview_sha256'] == validate_draft(sample, draft_id='draft-id',
       subject='Approved subject', recipient='human@example.invalid')['preview_sha256']
    for field,bad in [('isDraft',False), ('subject','Tampered'), ('ccRecipients',[{'emailAddress':{'address':'leak@example.invalid'}}])]:
        changed = {**sample, field:bad}
        with pytest.raises(DraftReleaseRejected):
            validate_draft(changed,draft_id='draft-id',subject='Approved subject',recipient='human@example.invalid')


def test_reconcile_requires_recorded_human_investigation():
    with pytest.raises(Exception):
        ReconcileRequest(operator_note='Looked in the remote system')
    valid = ReconcileRequest(operator_note='Inspected remote system and found matching artifact',
                              confirm_manual_review=True)
    assert valid.remote_id is None
