from __future__ import annotations

import time
from uuid import uuid4

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match
from starlette.types import ASGIApp

from shared.metrics import normalize_route, status_class

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Accept or generate a request ID and echo it on every response."""

    async def dispatch(self, request: Request, call_next: object) -> Response:
        """Process a request, attaching or creating a request ID."""
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
        request.state.request_id = request_id
        response: Response = await call_next(request)  # type: ignore[operator]
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record per-request Prometheus metrics."""

    def __init__(
        self,
        app: ASGIApp,
        requests_total: Counter,
        request_duration_seconds: Histogram,
        exceptions_total: Counter,
    ) -> None:
        """Initialise the middleware with the metric instruments."""
        super().__init__(app)
        self._requests_total = requests_total
        self._request_duration_seconds = request_duration_seconds
        self._exceptions_total = exceptions_total

    def _resolve_route(self, request: Request) -> str:
        """Return the normalised route template for the incoming request."""
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                raw: str = getattr(route, "path", request.url.path)
                return normalize_route(raw)
        return normalize_route(request.url.path)

    async def dispatch(self, request: Request, call_next: object) -> Response:
        """Record timing and outcome metrics for each HTTP request."""
        route = self._resolve_route(request)
        method = request.method
        start = time.perf_counter()
        try:
            response: Response = await call_next(request)  # type: ignore[operator]
        except Exception as exc:
            error_type = type(exc).__name__
            self._exceptions_total.labels(route=route, error_type=error_type).inc()
            raise
        duration = time.perf_counter() - start
        status_cls = status_class(response.status_code)
        self._requests_total.labels(method=method, route=route, status_class=status_cls).inc()
        self._request_duration_seconds.labels(method=method, route=route).observe(duration)
        return response
