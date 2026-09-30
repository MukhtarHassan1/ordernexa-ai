"""Contract-tested Microsoft Graph transport; no credentials are bundled.

These are integration primitives, not a claim of configured Graph subscriptions,
permissions, live SharePoint archives, Teams approval delivery or sent messages.
Use least-privilege Graph tokens appropriate for each action.
"""
import base64
from html.parser import HTMLParser
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


class GraphIntegrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class InboundMail:
    external_id: str
    internet_message_id: str | None
    subject: str
    sender: str
    body_text: str
    attachments: list[tuple[str, bytes, str]]


class _ReadableHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.muted = 0

    def handle_starttag(self, tag, attrs):
        if tag in {'style', 'script'}:
            self.muted += 1
        if tag in {'p', 'div', 'br', 'li'}:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in {'style', 'script'} and self.muted:
            self.muted -= 1

    def handle_data(self, data):
        if not self.muted:
            self.parts.append(data)

    def result(self):
        return ' '.join(''.join(self.parts).split())


class MicrosoftGraph:
    def __init__(
        self, *, token_provider: Callable[[], Awaitable[str]],
        client: httpx.AsyncClient | None = None, base_url: str = "https://graph.microsoft.com/v1.0",
    ) -> None:
        self.token_provider = token_provider
        self.base_url = base_url.rstrip("/")
        self._client = client

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        token = await self.token_provider()
        if not token:
            raise GraphIntegrationError("No configured Graph token; setup required.")
        client = self._client or httpx.AsyncClient(timeout=25)
        close_after = self._client is None
        try:
            res = await client.request(
                method, self.base_url + path,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                **kwargs,
            )
            res.raise_for_status()
            return res.json() if res.content else {}
        except httpx.HTTPStatusError as exc:
            raise GraphIntegrationError(f"Microsoft Graph returned HTTP {exc.response.status_code}.") from exc
        except httpx.RequestError as exc:
            raise GraphIntegrationError("Microsoft Graph transport unavailable.") from exc
        finally:
            if close_after:
                await client.aclose()

    async def get_message_with_attachments(self, mailbox: str, message_id: str) -> InboundMail:
        # Mail.Read and access to the specified mailbox are prerequisites.
        root = f"/users/{quote(mailbox, safe='')}/messages/{quote(message_id, safe='')}"
        msg = await self._request("GET", root + "?$select=id,internetMessageId,subject,from,body")
        att = await self._request("GET", root + "/attachments")
        if att.get("@odata.nextLink"):
            raise GraphIntegrationError("Attachment pagination requires further processing; refusing a partial order.")
        attachments = []
        for obj in att.get("value", []):
            if obj.get("@odata.type") != "#microsoft.graph.fileAttachment":
                continue
            encoded = obj.get("contentBytes")
            if not encoded:
                continue
            if len(encoded) > 25 * 1024 * 1024:
                raise GraphIntegrationError("Incoming Graph attachment exceeds safe demo size.")
            try:
                data = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError) as exc:
                raise GraphIntegrationError("Invalid Graph attachment encoding.") from exc
            attachments.append((obj.get("name") or "attachment", data,
                                obj.get("contentType") or "application/octet-stream"))
        sender = ((msg.get("from") or {}).get("emailAddress") or {}).get("address", "")
        body = msg.get('body') or {}
        if body.get('contentType', '').lower() == 'html':
            parser = _ReadableHTML()
            parser.feed(body.get('content', ''))
            body_text = parser.result()
        else:
            body_text = body.get('content', '')
        return InboundMail(
            external_id=msg["id"], internet_message_id=msg.get("internetMessageId"),
            subject=msg.get("subject") or "", sender=sender,
            body_text=body_text, attachments=attachments,
        )

    async def archive_file(self, *, drive_id: str, path: str, data: bytes) -> dict:
        """PUT a small file to a pre-authorized SharePoint drive. Graph permissions
        and Sites.Selected grants MUST be supplied by the site owner beforehand.
        """
        if not path or path.startswith("/") or ".." in path.split("/"):
            raise ValueError("Archive paths must be relative and must not traverse parent directories.")
        safe_path = "/".join(quote(segment, safe="") for segment in path.split("/"))
        return await self._request(
            "PUT", f"/drives/{quote(drive_id, safe='')}/root:/{safe_path}:/content",
            content=data,
        )

    async def send_confirmed_email(self, *, sender_id: str, recipient: str,
                                   subject: str, plain_text: str) -> None:
        """EXPLICIT SEND ONLY: requires Mail.Send, a verified approved state
        at the caller, and a unique persisted integration-command key.
        Never call directly from probabilistic extraction.
        """
        if not (recipient and subject and plain_text):
            raise ValueError("Recipient, subject and approved content are required.")
        await self._request("POST", f"/users/{quote(sender_id, safe='')}/sendMail", json={
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": plain_text},
                "toRecipients": [{"emailAddress": {"address": recipient}}],
            }, "saveToSentItems": True,
        })

    async def inspect_archive(self, *, drive_id: str, path: str) -> dict | None:
        """Read a known path only; caller compares remote content byte-for-byte."""
        if not path or path.startswith('/') or '..' in path.split('/'):
            raise ValueError('Invalid archive path.')
        safe_path = '/'.join(quote(segment, safe='') for segment in path.split('/'))
        try:
            return await self._request('GET', f'/drives/{quote(drive_id, safe="")}/root:/{safe_path}')
        except GraphIntegrationError as exc:
            if 'HTTP 404' in str(exc):
                return None
            raise

    async def archive_content(self, *, drive_id: str, path: str) -> bytes:
        """Byte-level read-after-write. Never infer success from metadata alone."""
        if not path or path.startswith('/') or '..' in path.split('/'):
            raise ValueError('Invalid archive path.')
        token = await self.token_provider()
        safe_path = '/'.join(quote(segment, safe='') for segment in path.split('/'))
        async with httpx.AsyncClient(timeout=40, follow_redirects=True) as client:
            res = await client.get(self.base_url +
                f'/drives/{quote(drive_id, safe="")}/root:/{safe_path}:/content',
                headers={'Authorization': f'Bearer {token}'})
            res.raise_for_status()
            return res.content

    async def create_confirmation_draft(self, *, sender_id: str, recipient: str,
                                        subject: str, plain_text: str) -> dict:
        if not recipient or '@' not in recipient or not subject or not plain_text:
            raise ValueError('Verified recipient and approved draft contents required.')
        return await self._request('POST', f'/users/{quote(sender_id, safe="")}/messages', json={
            'subject': subject,
            'body': {'contentType': 'Text', 'content': plain_text},
            'toRecipients': [{'emailAddress': {'address': recipient}}],
        })

    async def get_draft(self, *, sender_id: str, draft_id: str) -> dict:
        return await self._request('GET', f'/users/{quote(sender_id, safe="")}/messages/{quote(draft_id, safe="")}'
                                   '?$select=id,subject,isDraft,toRecipients,ccRecipients,bccRecipients,body')

    async def send_existing_draft_once(self, *, sender_id: str, draft_id: str) -> None:
        """No API retry here. Caller persists unique command BEFORE sending."""
        if not sender_id or not draft_id:
            raise ValueError('Mailbox and existing draft ID are required.')
        await self._request('POST', f'/users/{quote(sender_id, safe="")}/messages/{quote(draft_id, safe="")}/send')
