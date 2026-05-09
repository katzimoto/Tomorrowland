from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Final

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
from prometheus_client.gc_collector import GCCollector
from prometheus_client.platform_collector import PlatformCollector
from prometheus_client.process_collector import ProcessCollector
from starlette.requests import Request

HTTP_DURATION_BUCKETS: Final[tuple[float, ...]] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
)
_UNKNOWN_ROUTE: Final[str] = "__unknown__"
_BRACED_PATH_PARAMETER_RE: Final[re.Pattern[str]] = re.compile(r"\{[^}/]+\}")


class MetricsRegistry:
    """Prometheus collectors used by a single Neverland API app instance."""

    def __init__(self, *, version: str, commit: str, environment: str) -> None:
        """Initialize default runtime and Neverland application metrics."""
        self.registry = CollectorRegistry(auto_describe=True)
        ProcessCollector(registry=self.registry)
        PlatformCollector(registry=self.registry)
        GCCollector(registry=self.registry)

        self.build_info = Gauge(
            "neverland_build_info",
            "Static Neverland build and runtime metadata.",
            ("version", "commit", "environment"),
            registry=self.registry,
        )
        self.http_requests_total = Counter(
            "neverland_http_requests_total",
            "Total HTTP API requests by method, route template, and status class.",
            ("method", "route", "status_class"),
            registry=self.registry,
        )
        self.http_request_duration_seconds = Histogram(
            "neverland_http_request_duration_seconds",
            "HTTP API request duration in seconds by method and route template.",
            ("method", "route"),
            buckets=HTTP_DURATION_BUCKETS,
            registry=self.registry,
        )
        self.http_exceptions_total = Counter(
            "neverland_http_exceptions_total",
            "Unhandled HTTP API exceptions by route template and exception type.",
            ("route", "error_type"),
            registry=self.registry,
        )
        self.build_info.labels(
            version=safe_label_value(version),
            commit=safe_label_value(commit),
            environment=safe_label_value(environment),
        ).set(1)


def safe_label_value(value: str) -> str:
    """Return a bounded low-cardinality metric label value.

    The helper is intentionally conservative for operator-controlled values used
    as metric labels. Route labels should use :func:`route_template_for_request`.
    """
    normalized = value.strip() or "unknown"
    return normalized[:100]


def route_template_for_request(request: Request) -> str:
    """Return a low-cardinality route template label for an inbound request."""
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str) and route_path:
        return normalize_route_template(route_path)
    return _UNKNOWN_ROUTE


def normalize_route_template(route: str) -> str:
    """Normalize a route template so metric labels never contain path values."""
    if not route.startswith("/"):
        return _UNKNOWN_ROUTE
    segments = [segment for segment in route.split("/") if segment]
    if not segments:
        return "/"
    return "/" + "/".join(_normalize_segment(segment) for segment in segments)


def status_class(status_code: int) -> str:
    """Return the Prometheus status-class label for an HTTP status code."""
    if status_code < 100:
        return "unknown"
    return f"{status_code // 100}xx"


def _normalize_segment(segment: str) -> str:
    """Normalize one route-template path segment."""
    if segment.startswith("{") and segment.endswith("}"):
        return segment
    if _BRACED_PATH_PARAMETER_RE.search(segment):
        return _BRACED_PATH_PARAMETER_RE.sub("{param}", segment)
    return segment


def metric_names(registry: CollectorRegistry) -> Iterable[str]:
    """Yield metric sample names from a registry for unit-test assertions."""
    for metric in registry.collect():
        for sample in metric.samples:
            yield sample.name
