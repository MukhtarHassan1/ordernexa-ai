import hashlib
import hmac
from decimal import Decimal

import pytest

from app.integrations.stripe_sandbox import StripeSandboxError, amount_to_minor, verify_stripe_signature


def test_amount_to_minor_is_deterministic_for_demo_currencies():
    assert amount_to_minor(Decimal("13995.00"), "GBP") == 1_399_500
    assert amount_to_minor(Decimal("10.235"), "EUR") == 1024


def test_amount_to_minor_fails_closed_for_unmodelled_currency():
    with pytest.raises(StripeSandboxError):
        amount_to_minor(Decimal("100"), "JPY")


def test_stripe_signature_verification_and_replay_window():
    body = b'{"id":"evt_test_1"}'
    secret = "whsec_test_reference_secret_1234567890"
    timestamp = 1_800_000_000
    digest = hmac.new(secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256).hexdigest()
    header = f"t={timestamp},v1={digest}"
    assert verify_stripe_signature(body, header, secret=secret, now=timestamp)
    assert not verify_stripe_signature(body + b"x", header, secret=secret, now=timestamp)
    assert not verify_stripe_signature(body, header, secret=secret, now=timestamp + 301)
