"""Application-layer HTTP hardening for the local/reference deployment.

A reverse proxy / API gateway remains responsible for production-grade global
rate limiting, TLS and network ACLs. These controls fail closed on obvious
oversize traffic and add correlation/security headers consistently.
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger("ordernexa.http")


class RequestMetricStore:
    """Small in-process latency/error sampler for the reference deployment.

    It is intentionally bounded and contains no request bodies or identities.
    Production can export the same fields to OpenTelemetry/Prometheus without
    changing business logic.
    """

    samples: dict[str, deque[tuple[float, int]]] = defaultdict(lambda: deque(maxlen=500))

    @classmethod
    def record(cls, route: str, duration_ms: float, status_code: int) -> None:
        cls.samples[route].append((duration_ms, status_code))

    @classmethod
    def snapshot(cls) -> dict:
        result = {}
        for route, values in cls.samples.items():
            if not values:
                continue
            durations = sorted(v[0] for v in values)
            def percentile(p: float) -> float:
                idx = min(len(durations) - 1, max(0, int(round((len(durations) - 1) * p))))
                return round(durations[idx], 2)
            result[route] = {
                "samples": len(values),
                "p50_ms": percentile(0.50),
                "p95_ms": percentile(0.95),
                "error_rate": round(sum(1 for _, code in values if code >= 500) / len(values), 4),
            }
        return result


def request_metrics_snapshot() -> dict:
    return RequestMetricStore.snapshot()


class RequestSafetyMiddleware(BaseHTTPMiddleware):
    _buckets: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID", "").strip()
        if not correlation_id or len(correlation_id) > 128:
            correlation_id = str(uuid4())
        request.state.correlation_id = correlation_id

        length = request.headers.get("content-length")
        if length:
            try:
                if int(length) > settings.security_max_request_bytes:
                    return self._response(413, "Request body exceeds configured maximum.", correlation_id)
            except ValueError:
                return self._response(400, "Invalid Content-Length header.", correlation_id)

        path = request.url.path
        is_webhook = any(fragment in path for fragment in (
            "/automation/graph/notifications", "/automation/graph/lifecycle",
            "/automation/n8n/intake", "/automation/voice/",
        ))
        limit = settings.webhook_rate_limit_requests_per_minute if is_webhook else settings.rate_limit_requests_per_minute
        client = request.client.host if request.client else "unknown"
        # Key only by client/path class: bounded local defense, not identity/RBAC.
        key = f"{client}:{'webhook' if is_webhook else 'api'}"
        now = time.monotonic()
        bucket = self._buckets[key]
        cutoff = now - 60.0
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if limit > 0 and len(bucket) >= limit:
            return self._response(429, "Application rate limit exceeded.", correlation_id)
        bucket.append(now)

        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000.0
        route_obj = request.scope.get("route")
        route_name = getattr(route_obj, "path", None) or path
        RequestMetricStore.record(route_name, duration_ms, response.status_code)
        logger.info(json.dumps({
            "event": "http_request",
            "method": request.method,
            "route": route_name,
            "status": response.status_code,
            "duration_ms": round(duration_ms, 2),
            "correlation_id": correlation_id,
        }, separators=(",", ":")))
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store" if path.startswith("/api/") else response.headers.get("Cache-Control", "no-cache")
        # CSP is intentionally self-only because the console is same-origin and does not need third-party script execution.
        if path.startswith("/console"):
            response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        return response

    @staticmethod
    def _response(code: int, message: str, correlation_id: str) -> JSONResponse:
        response = JSONResponse({"detail": message, "correlation_id": correlation_id}, status_code=code)
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

class ProductionIdentityBoundaryMiddleware(BaseHTTPMiddleware):
    """Require verified OIDC identity for internal API reads in non-development.

    Provider callbacks retain their dedicated secrets/signature validation and
    therefore bypass bearer auth. Route-level RBAC still applies to privileged
    actions after this middleware authenticates the principal.
    """

    PUBLIC_PREFIXES = (
        "/api/v1/health/",
        "/api/v1/automation/graph/notifications",
        "/api/v1/automation/graph/lifecycle",
        "/api/v1/automation/n8n/intake",
        "/api/v1/automation/voice/status/",
        "/api/v1/automation/voice/change-request",
        "/api/v1/payments/stripe/webhook",
    )

    async def dispatch(self, request: Request, call_next):
        if settings.app_env == "development" or request.method == "OPTIONS":
            return await call_next(request)
        path = request.url.path
        if not path.startswith("/api/v1/") or any(path.startswith(p) for p in self.PUBLIC_PREFIXES):
            return await call_next(request)
        from app.core.security import authenticate_bearer_token
        try:
            principal = await authenticate_bearer_token(request.headers.get("Authorization"))
        except Exception as exc:
            from fastapi import HTTPException
            if isinstance(exc, HTTPException):
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            raise
        request.state.principal = principal
        return await call_next(request)
