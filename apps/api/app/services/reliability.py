"""Shared reliability primitives for outbound integrations.

The goal is not to hide failures with retries. We classify errors, open a
persisted circuit when a dependency is unhealthy, and quarantine outcomes that
may already have committed remotely.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.digital_twin import IntegrationCircuit


class FailureCategory(StrEnum):
    TRANSIENT = "TRANSIENT"
    AUTHENTICATION = "AUTHENTICATION"
    RATE_LIMIT = "RATE_LIMIT"
    VALIDATION = "VALIDATION"
    POLICY = "POLICY"
    PERMANENT_BUSINESS = "PERMANENT_BUSINESS"
    UNCERTAIN_REMOTE_STATE = "UNCERTAIN_REMOTE_STATE"
    CONFIGURATION = "CONFIGURATION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ClassifiedFailure:
    category: FailureCategory
    retryable: bool
    remote_state_uncertain: bool = False


def classify_http_exception(exc: Exception, *, write_attempted: bool = False) -> ClassifiedFailure:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in {401, 403}:
            return ClassifiedFailure(FailureCategory.AUTHENTICATION, False)
        if code == 429:
            return ClassifiedFailure(
                FailureCategory.UNCERTAIN_REMOTE_STATE if write_attempted else FailureCategory.RATE_LIMIT,
                retryable=not write_attempted,
                remote_state_uncertain=write_attempted,
            )
        if code in {400, 404, 409, 412, 422}:
            return ClassifiedFailure(FailureCategory.VALIDATION, False)
        if 500 <= code <= 599:
            return ClassifiedFailure(
                FailureCategory.UNCERTAIN_REMOTE_STATE if write_attempted else FailureCategory.TRANSIENT,
                retryable=not write_attempted,
                remote_state_uncertain=write_attempted,
            )
    if isinstance(exc, (httpx.TimeoutException, httpx.RequestError)):
        return ClassifiedFailure(
            FailureCategory.UNCERTAIN_REMOTE_STATE if write_attempted else FailureCategory.TRANSIENT,
            retryable=not write_attempted,
            remote_state_uncertain=write_attempted,
        )
    return ClassifiedFailure(FailureCategory.UNKNOWN, False, remote_state_uncertain=write_attempted)


class CircuitOpen(RuntimeError):
    def __init__(self, provider: str, retry_after_seconds: int):
        super().__init__(f"{provider} circuit is open; retry after dependency cooldown.")
        self.provider = provider
        self.retry_after_seconds = retry_after_seconds


async def _get_circuit(session: AsyncSession, provider: str, *, lock: bool = False) -> IntegrationCircuit:
    stmt = select(IntegrationCircuit).where(IntegrationCircuit.provider == provider.upper())
    if lock:
        stmt = stmt.with_for_update()
    row = await session.scalar(stmt)
    if row is None:
        row = IntegrationCircuit(provider=provider.upper(), state="CLOSED", failure_count=0)
        session.add(row)
        await session.flush()
    return row


async def assert_circuit_allows(session: AsyncSession, provider: str) -> IntegrationCircuit:
    now = datetime.now(UTC)
    circuit = await _get_circuit(session, provider, lock=True)
    if circuit.state == "OPEN":
        if circuit.half_open_after and circuit.half_open_after <= now:
            circuit.state = "HALF_OPEN"
            await session.flush()
            return circuit
        retry_after = 1
        if circuit.half_open_after:
            retry_after = max(1, int((circuit.half_open_after - now).total_seconds()))
        raise CircuitOpen(provider.upper(), retry_after)
    return circuit


async def record_integration_success(session: AsyncSession, provider: str) -> None:
    circuit = await _get_circuit(session, provider, lock=True)
    circuit.state = "CLOSED"
    circuit.failure_count = 0
    circuit.opened_at = None
    circuit.half_open_after = None
    circuit.last_error_category = None
    circuit.last_success_at = datetime.now(UTC)
    await session.flush()


async def record_integration_failure(
    session: AsyncSession,
    provider: str,
    category: FailureCategory | str,
) -> None:
    now = datetime.now(UTC)
    category_value = category.value if isinstance(category, FailureCategory) else str(category)
    circuit = await _get_circuit(session, provider, lock=True)
    circuit.failure_count += 1
    circuit.last_error_category = category_value
    circuit.last_error_at = now

    # Validation/policy failures are request-specific and should not make the
    # dependency itself look unhealthy. Auth failures *do* open a circuit early
    # because hammering an expired credential is pointless.
    should_open = category_value in {
        FailureCategory.AUTHENTICATION.value,
        FailureCategory.RATE_LIMIT.value,
        FailureCategory.TRANSIENT.value,
        FailureCategory.UNCERTAIN_REMOTE_STATE.value,
        FailureCategory.UNKNOWN.value,
    } and (
        circuit.failure_count >= settings.circuit_failure_threshold
        or category_value == FailureCategory.AUTHENTICATION.value
    )
    if should_open:
        circuit.state = "OPEN"
        circuit.opened_at = now
        circuit.half_open_after = now + timedelta(seconds=settings.circuit_cooldown_seconds)
    await session.flush()


def safe_error_summary(exc: Exception) -> str:
    """Do not persist raw remote bodies or secrets in operational error fields."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP_{exc.response.status_code}"
    return type(exc).__name__
