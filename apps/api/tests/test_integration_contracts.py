import base64
import httpx
import pytest
from app.integrations.microsoft_graph import MicrosoftGraph
from app.integrations.hubspot import ContactUpsert, HubSpot


@pytest.mark.asyncio
async def test_graph_mail_attachment_contract():
    urls=[]
    def handler(req):
        assert req.headers['Authorization']=='Bearer test-delegated-token'
        urls.append(req.url.path)
        if req.url.path.endswith('/attachments'):
            return httpx.Response(200,json={'value':[{'@odata.type':'#microsoft.graph.fileAttachment',
              'name':'purchase-order.txt','contentType':'text/plain',
              'contentBytes':base64.b64encode(b'PO TEST').decode()}]})
        return httpx.Response(200,json={'id':'M1','subject':'Purchase order',
          'internetMessageId':'external-message-id',
          'from':{'emailAddress':{'address':'orders@example.test'}},
          'body':{'content':'Synthetic test only'}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        async def token(): return 'test-delegated-token'
        adapter=MicrosoftGraph(token_provider=token,client=client,base_url='https://mock.graph/v1.0')
        item=await adapter.get_message_with_attachments('sales@example.test','M1')
    assert item.external_id=='M1' and item.attachments[0][1]==b'PO TEST'
    assert len(urls)==2


@pytest.mark.asyncio
async def test_hubspot_explicit_upsert_contract():
    def handler(req):
        import json
        assert req.url.path.endswith('/contacts/batch/upsert')
        assert req.headers['Authorization']=='Bearer synthetic-test-only'
        obj=json.loads(req.content)
        assert obj['inputs'][0]['idProperty']=='email'
        return httpx.Response(200,json={'results':[{'id':'synthetic-1'}]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result=await HubSpot(access_token='synthetic-test-only',client=client,
                             base_url='https://mock.hubspot').upsert_contact(
            ContactUpsert('person@example.test','Synthetic Customer'))
    assert result['results'][0]['id']=='synthetic-1'
