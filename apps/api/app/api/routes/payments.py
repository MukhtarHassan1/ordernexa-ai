"""Optional V1.5 Stripe test-mode payment endpoints."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import DemoPrincipal, require_operator
from app.db.session import get_db
from app.integrations.stripe_sandbox import StripeSandboxError, verify_stripe_signature
from app.services.payment_service import apply_verified_stripe_event, create_payment_checkout, payment_status

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/stripe/transactions/{public_id}/checkout")
async def create_stripe_checkout(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    if principal.role not in {"FINANCE_MANAGER", "OPERATIONS_MANAGER", "ADMIN"}:
        raise HTTPException(403, "Finance/Operations/Admin role required.")
    try:
        return await create_payment_checkout(db, public_id=public_id, actor_id=principal.actor_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, StripeSandboxError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/stripe/transactions/{public_id}")
async def stripe_payment_status(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    principal: DemoPrincipal = Depends(require_operator),
):
    if principal.role not in {"FINANCE_MANAGER", "OPERATIONS_MANAGER", "ADMIN", "AUDITOR"}:
        raise HTTPException(403, "Finance/Operations/Admin/Auditor role required.")
    try:
        return await payment_status(db, public_id=public_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
):
    if not settings.stripe_enabled or not settings.stripe_webhook_secret:
        raise HTTPException(503, "Stripe sandbox webhook is disabled or not configured.")
    raw = await request.body()
    if len(raw) > 512_000:
        raise HTTPException(413, "Stripe webhook payload too large.")
    if not verify_stripe_signature(
        raw,
        stripe_signature,
        secret=settings.stripe_webhook_secret,
        tolerance_seconds=settings.stripe_webhook_tolerance_seconds,
    ):
        raise HTTPException(400, "Invalid or stale Stripe webhook signature.")
    try:
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise ValueError
        return await apply_verified_stripe_event(db, event)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(409, "Stripe event failed authoritative validation.") from exc
