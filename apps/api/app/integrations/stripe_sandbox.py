"""Stripe sandbox adapter for deterministic payment collection.

The adapter intentionally creates a hosted Checkout Session from already-validated
OrderNexa transaction values. No AI-generated amount, currency, redirect URL or
payment destination is accepted.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode

import httpx

from app.core.config import settings


class StripeSandboxError(RuntimeError):
    pass


@dataclass(frozen=True)
class CheckoutSessionResult:
    session_id: str
    url: str
    amount_total_minor: int
    currency: str
    payment_status: str


def amount_to_minor(amount: Decimal, currency: str) -> int:
    """Convert a deterministic decimal amount to Stripe's integer minor unit.

    This reference implementation supports the configured two-decimal currencies.
    Unsupported zero-/three-decimal currencies fail closed instead of
    guessing their exponent.
    """
    currency = currency.upper().strip()
    if currency not in {"GBP", "EUR", "USD"}:
        raise StripeSandboxError("Stripe sandbox supports GBP/EUR/USD only; add an explicit currency exponent before expanding it.")
    value = (Decimal(amount) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    if value <= 0:
        raise StripeSandboxError("Payment amount must be positive.")
    if value > 99_999_999_999:
        raise StripeSandboxError("Payment amount exceeds the reference adapter safety limit.")
    return int(value)


def verify_stripe_signature(raw_body: bytes, signature_header: str | None, *, secret: str, tolerance_seconds: int = 300, now: int | None = None) -> bool:
    """Verify Stripe-Signature using timestamp + raw payload.

    Multiple v1 signatures are accepted to support secret rotation. Timestamp
    freshness is enforced to reduce replay risk.
    """
    if not raw_body or not signature_header or not secret or len(secret) < 16:
        return False
    parts: dict[str, list[str]] = {}
    for item in signature_header.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        parts.setdefault(key.strip(), []).append(value.strip())
    try:
        timestamp = int((parts.get("t") or [""])[0])
    except ValueError:
        return False
    current = int(time.time()) if now is None else int(now)
    if tolerance_seconds >= 0 and abs(current - timestamp) > tolerance_seconds:
        return False
    signed = str(timestamp).encode("ascii") + b"." + raw_body
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, candidate) for candidate in parts.get("v1", []))


class StripeSandbox:
    BASE = "https://api.stripe.com/v1"

    def __init__(self, *, client: httpx.AsyncClient | None = None, base_url: str | None = None) -> None:
        self._client = client
        self.base_url = (base_url or self.BASE).rstrip("/")
        if not settings.stripe_enabled:
            raise StripeSandboxError("Stripe sandbox is disabled by configuration.")
        if not settings.stripe_secret_key.startswith("sk_test_"):
            raise StripeSandboxError("Only a Stripe test-mode secret key (sk_test_) is permitted by this adapter.")
        if not settings.stripe_success_url.startswith("https://") and not settings.stripe_success_url.startswith("http://localhost"):
            raise StripeSandboxError("Configure a safe Stripe success URL.")
        if not settings.stripe_cancel_url.startswith("https://") and not settings.stripe_cancel_url.startswith("http://localhost"):
            raise StripeSandboxError("Configure a safe Stripe cancel URL.")

    async def create_checkout_session(
        self,
        *,
        transaction_public_id: str,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
    ) -> CheckoutSessionResult:
        minor = amount_to_minor(amount, currency)
        form = {
            "mode": "payment",
            "client_reference_id": transaction_public_id,
            "success_url": settings.stripe_success_url,
            "cancel_url": settings.stripe_cancel_url,
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": currency.lower(),
            "line_items[0][price_data][unit_amount]": str(minor),
            "line_items[0][price_data][product_data][name]": f"OrderNexa transaction {transaction_public_id}",
            "metadata[transaction_public_id]": transaction_public_id,
            "payment_intent_data[metadata][transaction_public_id]": transaction_public_id,
        }
        headers = {
            "Authorization": f"Bearer {settings.stripe_secret_key}",
            "Idempotency-Key": idempotency_key,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0))
        close_after = self._client is None
        try:
            response = await client.post(f"{self.base_url}/checkout/sessions", content=urlencode(form), headers=headers)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise StripeSandboxError("Stripe Checkout Session creation was not verified.") from exc
        finally:
            if close_after:
                await client.aclose()
        session_id = payload.get("id")
        url = payload.get("url")
        remote_amount = payload.get("amount_total")
        remote_currency = str(payload.get("currency") or "").upper()
        if not isinstance(session_id, str) or not session_id.startswith("cs_test_"):
            raise StripeSandboxError("Stripe returned a non-test or invalid Checkout Session ID.")
        if not isinstance(url, str) or not url.startswith("https://checkout.stripe.com/"):
            raise StripeSandboxError("Stripe did not return a hosted Checkout URL.")
        if int(remote_amount or 0) != minor or remote_currency != currency.upper():
            raise StripeSandboxError("Stripe read-after-create values do not match the authoritative transaction amount/currency.")
        return CheckoutSessionResult(
            session_id=session_id,
            url=url,
            amount_total_minor=minor,
            currency=currency.upper(),
            payment_status=str(payload.get("payment_status") or "unpaid"),
        )

    async def get_checkout_session(self, session_id: str) -> dict:
        if not session_id.startswith("cs_test_"):
            raise StripeSandboxError("Only test-mode Checkout Session IDs are allowed.")
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
        close_after = self._client is None
        try:
            response = await client.get(
                f"{self.base_url}/checkout/sessions/{session_id}",
                headers={"Authorization": f"Bearer {settings.stripe_secret_key}"},
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise StripeSandboxError("Stripe Checkout Session could not be read for verification.") from exc
        finally:
            if close_after:
                await client.aclose()
