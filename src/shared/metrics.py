from __future__ import annotations

import re

from prometheus_client import REGISTRY as DEFAULT_REGISTRY
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

_PATH_PARAM_RE = re.compile(r"/\{[^}]+\}")

# Buckets cover typical fast API calls through slow LLM/search operations.
_DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)


def normalize_route(path: str) -> str:
    """Return the route template with path parameters replaced by a placeholder.

    Ensures label cardinality stays low and no raw IDs leak into metric labels.
    Only FastAPI-style ``{param}`` template segments are normalised; literal path
    segments such as UUIDs that slipped through routing are left unchanged.

    Examples::

        normalize_route("/documents/{doc_id}") -> "/documents/{id}"
        normalize_route("/a/{x}/b/{y}") -> "/a/{id}/b/{id}"
        normalize_route("/health") -> "/health"
    """
    return _PATH_PARAM_RE.sub("/{id}", path)


def status_class(status_code: int) -> str:
    """Return the status-class label (2xx, 4xx, 5xx, or other)."""
    if 200 <= status_code < 300:
        return "2xx"
    if 400 <= status_code < 500:
        return "4xx"
    if 500 <= status_code < 600:
        return "5xx"
    return "other"


def make_metrics(
    registry: CollectorRegistry | None = None,
) -> tuple[Gauge, Counter, Histogram, Counter]:
    """Create and register all Phase 10a metrics.

    Args:
        registry: Prometheus registry to use; defaults to the global registry.
            Pass an isolated ``CollectorRegistry()`` in tests.

    Returns:
        Tuple of (build_info, requests_total, request_duration_seconds,
        exceptions_total).
    """
    reg = registry or DEFAULT_REGISTRY

    build_info: Gauge = Gauge(
        "neverland_build_info",
        "Build and environment information",
        ["version", "commit", "environment"],
        registry=reg,
    )

    requests_total: Counter = Counter(
        "neverland_http_requests_total",
        "Total HTTP requests",
        ["method", "route", "status_class"],
        registry=reg,
    )

    request_duration_seconds: Histogram = Histogram(
        "neverland_http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "route"],
        buckets=_DURATION_BUCKETS,
        registry=reg,
    )

    exceptions_total: Counter = Counter(
        "neverland_http_exceptions_total",
        "Total unhandled exceptions",
        ["route", "error_type"],
        registry=reg,
    )

    return build_info, requests_total, request_duration_seconds, exceptions_total


# Module-level singletons registered in the global Prometheus registry.
# Import these in application code; use make_metrics(registry=...) in tests.
BUILD_INFO, HTTP_REQUESTS_TOTAL, HTTP_REQUEST_DURATION_SECONDS, HTTP_EXCEPTIONS_TOTAL = (
    make_metrics()
)
