"""Offline contracts: NO real accounts, Windows Ollama, DB or external writes."""
import base64
import json
import sys
import types
from pathlib import Path
import httpx
import pytest
from pydantic import ValidationError
from app.automation.contracts import N8NIngress, ExternalSchedule, VoiceChangeIn
from app.automation.jobs import canonical_hash, graph_event_id, verify_webhook_secret
from app.automation.manage_graph import safe_https
from app.integrations.microsoft_graph import MicrosoftGraph, GraphIntegrationError
from app.integrations.hubspot import HubSpot, ContactUpsert


def test_n8n_requires_document():
    with pytest.raises(ValidationError):
        N8NIngress(event_id='abc12345')


def test_n8n_base64_validation_and_limit():
    valid = N8NIngress(event_id='abc12345', content_base64=base64.b64encode(b'PO test').decode())
    assert valid.document_bytes(10) == b'PO test'
    with pytest.raises(ValueError):
        valid.document_bytes(2)
    broken = N8NIngress(event_id='abc12345', content_base64='this is invalid base64')
    with pytest.raises(ValueError):
        broken.document_bytes(100)


def test_external_writes_require_human_consent_and_verified_destination():
    with pytest.raises(ValidationError):
        ExternalSchedule(sharepoint=True)
    with pytest.raises(ValidationError):
        ExternalSchedule(sharepoint=False, hubspot=True, confirm_external_data_transfer=True)
    with pytest.raises(ValidationError):
        ExternalSchedule(sharepoint=False, confirm_external_data_transfer=True)
    good = ExternalSchedule(sharepoint=False, hubspot=True,
        verified_contact_email='verified@example.invalid', confirm_external_data_transfer=True)
    assert good.hubspot is True


@pytest.mark.parametrize('bad', ['BANK_CHANGE', 'REFUND', 'EXECUTE_ORDER', 'CHANGE_CONTRACT', ''])
def test_voice_restricts_actions(bad):
    with pytest.raises(ValidationError):
        VoiceChangeIn(event_id='abc12345', call_id='call-1234',
            transaction_public_id='TXN-2026-000001', request_type=bad,
            request_note='Please change the bank details.')


def test_voice_cannot_invent_other_transaction():
    with pytest.raises(ValidationError):
        VoiceChangeIn(event_id='abc12345', call_id='call-1234',
            transaction_public_id='PO-88192', request_type='CALLBACK',
            request_note='Please call me back later.')


def test_webhook_secret_fails_closed():
    k = 'test-token-over-32-characters-unique-to-test'
    assert verify_webhook_secret(k, k)
    assert not verify_webhook_secret('wrong', k)
    assert not verify_webhook_secret(k, '')
    assert not verify_webhook_secret(k, 'tiny')
    assert not verify_webhook_secret(None, k)


def test_idempotency_key_stability_and_hash_collision_refusal():
    k = graph_event_id('sub', 'msg')
    assert k == graph_event_id('sub', 'msg')
    assert k != graph_event_id('sub', 'msg2')
    assert canonical_hash({'a':1, 'b':2}) == canonical_hash({'b':2, 'a':1})
    assert canonical_hash({'a':1}) != canonical_hash({'a':2})


@pytest.mark.parametrize('url', ['http://invalid.example/callback', 'https://user:pass@example.org/a',
                                  'file:///etc/passwd', 'https://example.org/a#secret'])
def test_graph_callback_only_public_https_without_credential(url):
    with pytest.raises(ValueError):
        safe_https(url)


def test_graph_callback_valid_syntax():
    assert safe_https('https://hooks.example.org/api/v1/automation/graph/notifications')


@pytest.mark.asyncio
async def test_graph_message_normalizes_html_and_file_bytes():
    async def handler(request):
        if request.url.path.endswith('/attachments'):
            return httpx.Response(200, json={'value': [
                {'@odata.type':'#microsoft.graph.fileAttachment','name':'po.txt',
                 'contentBytes':base64.b64encode(b'PO-88192').decode(),'contentType':'text/plain'}]})
        return httpx.Response(200,json={'id':'msg-1','subject':'PO','body':{'contentType':'html','content':'<p>Order <b>40</b> parts</p><script>steal()</script>'},
                                       'from':{'emailAddress':{'address':'customer@example.invalid'}}})
    async def token(): return 'fake-test-token'
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        graph=MicrosoftGraph(token_provider=token,client=client,base_url='https://graph.example.invalid')
        result=await graph.get_message_with_attachments('mail@example.invalid','msg-1')
    assert result.attachments[0][1] == b'PO-88192'
    assert '40' in result.body_text
    assert 'steal' not in result.body_text


@pytest.mark.asyncio
async def test_graph_refuses_partial_attachment_pagination():
    async def handler(request):
        if request.url.path.endswith('/attachments'):
            return httpx.Response(200,json={'value': [],'@odata.nextLink':'https://graph.example.invalid/next'})
        return httpx.Response(200,json={'id':'id', 'body':{}})
    async def token(): return 'fake-test-token'
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        graph=MicrosoftGraph(token_provider=token,client=client,base_url='https://graph.example.invalid')
        with pytest.raises(GraphIntegrationError):
            await graph.get_message_with_attachments('mail@example.invalid','msg-1')


@pytest.mark.asyncio
async def test_hubspot_idempotent_upsert_and_verify_contact():
    calls=[]
    def handler(request):
        calls.append((request.method, request.url.path))
        if request.method == 'POST':
            body=json.loads(request.content)
            assert body['inputs'][0]['idProperty'] == 'email'
            return httpx.Response(200,json={'results':[{'id':'123'}]})
        return httpx.Response(200,json={'id':'123','properties':{'email':'example@example.invalid'}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        hub=HubSpot(access_token='fake',client=client,base_url='https://hubspot.example.invalid')
        await hub.upsert_contact(ContactUpsert(email='example@example.invalid',company='Example Ltd'))
        result=await hub.get_contact('123')
    assert result['properties']['email'] == 'example@example.invalid'
    assert len(calls) == 2


def test_500_case_generated_set_is_not_misrepresented_as_curated():
    filename = 'generated_draft_500_REQUIRES_REVIEW.jsonl'
    candidates = [Path('/evals/datasets') / filename]
    candidates.extend(
        parent / 'evals/datasets' / filename
        for parent in Path(__file__).resolve().parents
    )
    dataset = next(
        (path for path in candidates if path.is_file()),
        None
    )
    assert dataset is not None, "Evaluation dataset not found"

    cases=[json.loads(x) for x in dataset.read_text().splitlines()]
    assert len(cases) == 500
    assert len({x['id'] for x in cases}) == 500
    assert all(x['requires_human_label_review'] for x in cases)
    assert all(x['provenance']=='DETERMINISTICALLY_GENERATED_NOT_CURATED' for x in cases)
