"""Offline provider contract tests.

These tests deliberately use synthetic HTTP transports. They validate request/response
contracts, safety boundaries and replay-sensitive behavior without claiming a live
Microsoft, HubSpot, Vapi/Twilio, Teams or Stripe account was connected.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from app.automation.contracts import VoiceChangeIn
from app.automation.worker import verified_teams_workflow_url
from app.core.config import settings
from app.integrations.microsoft_graph import MicrosoftGraph
from app.integrations.stripe_sandbox import StripeSandbox, StripeSandboxError
from app.main import app


@pytest.mark.asyncio
async def test_graph_subscription_payload_matches_basic_mail_notification_contract():
    seen = {}

    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert request.url.path == "/v1.0/subscriptions"
        assert request.headers["Authorization"] == "Bearer synthetic-graph-token"
        body = json.loads(request.content)
        seen.update(body)
        return httpx.Response(201, json={
            "id": "sub-synthetic-1",
            "resource": body["resource"],
            "expirationDateTime": body["expirationDateTime"],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        async def token():
            return "synthetic-graph-token"

        graph = MicrosoftGraph(token_provider=token, client=client)
        result = await graph.create_subscription(
            resource="/users/orders@example.invalid/mailFolders('Inbox')/messages",
            notification_url="https://hooks.example.invalid/api/v1/automation/graph/notifications",
            lifecycle_url="https://hooks.example.invalid/api/v1/automation/graph/lifecycle",
            expiration=datetime.now(UTC) + timedelta(days=2),
            client_state="x" * 48,
        )

    assert result["id"] == "sub-synthetic-1"
    assert seen["changeType"] == "created"
    assert seen["latestSupportedTlsVersion"] == "v1_2"
    assert seen["notificationUrl"].endswith("/api/v1/automation/graph/notifications")
    assert seen["lifecycleNotificationUrl"].endswith("/api/v1/automation/graph/lifecycle")
    assert seen["expirationDateTime"].endswith("Z")


@pytest.mark.asyncio
async def test_graph_subscription_refuses_oversized_client_state_before_transport():
    called = False

    def handler(request):
        nonlocal called
        called = True
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        async def token():
            return "synthetic-graph-token"

        graph = MicrosoftGraph(token_provider=token, client=client)
        with pytest.raises(ValueError, match="32 and 128"):
            await graph.create_subscription(
                resource="/users/orders@example.invalid/messages",
                notification_url="https://hooks.example.invalid/api/v1/automation/graph/notifications",
                lifecycle_url="https://hooks.example.invalid/api/v1/automation/graph/lifecycle",
                expiration=datetime.now(UTC) + timedelta(hours=1),
                client_state="x" * 129,
            )
    assert called is False


@pytest.mark.asyncio
async def test_graph_sharepoint_upload_and_byte_readback_contract():
    payload = b'{"transaction_id":"TXN-2026-000001"}'
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request):
        calls.append((request.method, request.url.path))
        assert request.headers["Authorization"] == "Bearer synthetic-graph-token"
        if request.method == "PUT":
            assert request.content == payload
            return httpx.Response(201, json={"id": "drive-item-1", "name": "confirmation.json"})
        if request.url.path.endswith(":/content"):
            return httpx.Response(200, content=payload)
        return httpx.Response(200, json={"id": "drive-item-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        async def token():
            return "synthetic-graph-token"

        graph = MicrosoftGraph(token_provider=token, client=client)
        created = await graph.archive_file(
            drive_id="drive-123",
            path="OrderNexa/TXN-2026-000001/confirmation.json",
            data=payload,
        )
        remote = await graph.archive_content(
            drive_id="drive-123",
            path="OrderNexa/TXN-2026-000001/confirmation.json",
        )

    assert created["id"] == "drive-item-1"
    assert remote == payload
    assert calls[0][0] == "PUT"
    assert calls[-1][0] == "GET"


@pytest.mark.asyncio
async def test_graph_outlook_draft_create_readback_and_send_contract():
    draft_id = "draft-123"
    events = []

    def handler(request: httpx.Request):
        events.append((request.method, request.url.path))
        if request.method == "POST" and request.url.path.endswith("/messages"):
            body = json.loads(request.content)
            assert body["toRecipients"][0]["emailAddress"]["address"] == "buyer@example.invalid"
            return httpx.Response(201, json={"id": draft_id})
        if request.method == "GET":
            return httpx.Response(200, json={
                "id": draft_id,
                "isDraft": True,
                "subject": "Order confirmation",
                "toRecipients": [{"emailAddress": {"address": "buyer@example.invalid"}}],
                "body": {"contentType": "Text", "content": "Approved draft"},
            })
        if request.method == "POST" and request.url.path.endswith("/send"):
            return httpx.Response(202)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        async def token():
            return "synthetic-graph-token"

        graph = MicrosoftGraph(token_provider=token, client=client)
        created = await graph.create_confirmation_draft(
            sender_id="orders@example.invalid",
            recipient="buyer@example.invalid",
            subject="Order confirmation",
            plain_text="Approved draft",
        )
        readback = await graph.get_draft(sender_id="orders@example.invalid", draft_id=created["id"])
        await graph.send_existing_draft_once(sender_id="orders@example.invalid", draft_id=created["id"])

    assert readback["isDraft"] is True
    assert any(method == "POST" and path.endswith("/send") for method, path in events)


@pytest.mark.asyncio
async def test_stripe_checkout_session_contract_with_test_mode_mock(monkeypatch):
    monkeypatch.setattr(settings, "stripe_enabled", True)
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_synthetic_123456789")
    monkeypatch.setattr(settings, "stripe_success_url", "http://localhost:8000/console/?stripe=success")
    monkeypatch.setattr(settings, "stripe_cancel_url", "http://localhost:8000/console/?stripe=cancel")

    def handler(request: httpx.Request):
        assert request.headers["Authorization"] == "Bearer sk_test_synthetic_123456789"
        if request.method == "POST":
            assert request.headers["Idempotency-Key"] == "payment:TXN-2026-000001"
            form = parse_qs(request.content.decode())
            assert form["mode"] == ["payment"]
            assert form["client_reference_id"] == ["TXN-2026-000001"]
            assert form["line_items[0][price_data][unit_amount]"] == ["125050"]
            return httpx.Response(200, json={
                "id": "cs_test_synthetic_1",
                "url": "https://checkout.stripe.com/c/pay/cs_test_synthetic_1",
                "amount_total": 125050,
                "currency": "gbp",
                "payment_status": "unpaid",
            })
        return httpx.Response(200, json={
            "id": "cs_test_synthetic_1",
            "amount_total": 125050,
            "currency": "gbp",
            "payment_status": "paid",
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        stripe = StripeSandbox(client=client, base_url="https://stripe.example.invalid/v1")
        created = await stripe.create_checkout_session(
            transaction_public_id="TXN-2026-000001",
            amount=Decimal("1250.50"),
            currency="GBP",
            idempotency_key="payment:TXN-2026-000001",
        )
        readback = await stripe.get_checkout_session(created.session_id)

    assert created.session_id.startswith("cs_test_")
    assert created.amount_total_minor == 125050
    assert readback["payment_status"] == "paid"


@pytest.mark.asyncio
async def test_stripe_refuses_mismatched_remote_amount(monkeypatch):
    monkeypatch.setattr(settings, "stripe_enabled", True)
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_synthetic_123456789")

    def handler(request):
        return httpx.Response(200, json={
            "id": "cs_test_synthetic_2",
            "url": "https://checkout.stripe.com/c/pay/cs_test_synthetic_2",
            "amount_total": 999,
            "currency": "gbp",
            "payment_status": "unpaid",
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        stripe = StripeSandbox(client=client, base_url="https://stripe.example.invalid/v1")
        with pytest.raises(StripeSandboxError, match="do not match"):
            await stripe.create_checkout_session(
                transaction_public_id="TXN-2026-000001",
                amount=Decimal("10.00"),
                currency="GBP",
                idempotency_key="payment:TXN-2026-000001",
            )


def test_vapi_reference_contracts_match_order_nexa_routes_and_safe_actions():
    repo = Path(__file__).resolve().parents[3]
    contract = json.loads((repo / "integrations/vapi/OrderNexa_Vapi_Tool_Contracts.json").read_text())
    openapi = app.openapi()
    paths = openapi["paths"]

    assert contract["vapi_tool_type"] == "apiRequest"
    assert contract["public_https_required"] is True
    assert "Custom Credential" in contract["credential_strategy"]

    assert contract["tools"], "At least one Vapi API Request contract is required."
    for tool in contract["tools"]:
        if "path" in tool:
            route = tool["path"]
        else:
            route = tool["path_template"].replace("{transaction_public_id}", "{public_id}")
        assert route in paths
        assert tool["method"].lower() in paths[route]
        assert tool["headers"].get("X-OrderNexa-Voice-Secret")

    assert {tool["name"] for tool in contract["tools"]} == {
        "ordernexa_status_lookup", "ordernexa_change_request"
    }
    assert "direct ERP modification" in contract["forbidden_voice_actions"]


def test_voice_contract_remains_review_only_and_rejects_direct_execution():
    value = VoiceChangeIn(
        event_id="vapi-event-0001",
        call_id="call-0001",
        transaction_public_id="TXN-2026-000001",
        request_type="QUANTITY_CHANGE",
        request_note="Customer asks to change quantity to 55 after identity verification.",
    )
    assert value.request_type == "QUANTITY_CHANGE"

    with pytest.raises(Exception):
        VoiceChangeIn(
            event_id="vapi-event-0002",
            call_id="call-0002",
            transaction_public_id="TXN-2026-000001",
            request_type="EXECUTE_ORDER",
            request_note="Create the ERP order immediately.",
        )


def test_twilio_boundary_keeps_telephony_credentials_out_of_fastapi_backend():
    repo = Path(__file__).resolve().parents[3]
    config = (repo / "apps/api/app/core/config.py").read_text()
    readme = (repo / "integrations/twilio/README.md").read_text()
    assert "twilio_account_sid" not in config.lower()
    assert "twilio_auth_token" not in config.lower()
    assert "Twilio phone number -> Vapi assistant -> OrderNexa" in readme


@pytest.mark.parametrize("url,expected", [
    ("https://region.logic.azure.com/workflows/example/triggers/manual/paths/invoke", True),
    ("http://region.logic.azure.com/workflows/example", False),
    ("https://logic.azure.com.evil.invalid/workflows/example", False),
    ("https://user:pass@region.logic.azure.com/workflows/example", False),
    ("https://region.logic.azure.com/workflows/example#fragment", False),
])
def test_teams_workflow_url_boundary(url, expected):
    assert verified_teams_workflow_url(url) is expected

@pytest.mark.parametrize("url", [
    "https://localhost/api/v1/automation/graph/notifications",
    "https://127.0.0.1/api/v1/automation/graph/notifications",
    "https://10.0.0.8/api/v1/automation/graph/notifications",
    "http://hooks.example.invalid/api/v1/automation/graph/notifications",
    "https://user:pass@hooks.example.invalid/api/v1/automation/graph/notifications",
])
def test_graph_callback_contract_rejects_non_public_or_credentialed_destinations(url):
    from app.integrations.microsoft_graph import is_public_https_callback
    assert is_public_https_callback(url) is False
