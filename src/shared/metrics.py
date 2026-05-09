from __future__ import annotations

import re
from collections.abc import Iterable
from contextvars import ContextVar, Token
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
_CURRENT_METRICS: ContextVar[object | None] = ContextVar("neverland_metrics", default=None)


DOMAIN_DURATION_BUCKETS: Final[tuple[float, ...]] = (
    0.001,
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
    60.0,
)
DOCUMENT_BYTES_BUCKETS: Final[tuple[float, ...]] = (
    0,
    1024,
    10_240,
    102_400,
    1_048_576,
    10_485_760,
    104_857_600,
    1_073_741_824,
)
RESULT_COUNT_BUCKETS: Final[tuple[float, ...]] = (0, 1, 5, 10, 25, 50, 100, 250, 500, 1000)
CITATION_COUNT_BUCKETS: Final[tuple[float, ...]] = (0, 1, 2, 3, 5, 8, 13, 21, 34)


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
        self.auth_login_attempts_total = Counter(
            "neverland_auth_login_attempts_total",
            "Login attempts by configured provider and outcome.",
            ("provider", "outcome"),
            registry=self.registry,
        )
        self.authz_denials_total = Counter(
            "neverland_authz_denials_total",
            "Authorization denials by coarse resource type and action.",
            ("resource_type", "action"),
            registry=self.registry,
        )
        self.admin_actions_total = Counter(
            "neverland_admin_actions_total",
            "Administrative actions already written to the audit log.",
            ("action", "resource_type"),
            registry=self.registry,
        )
        self.ingestion_syncs_total = Counter(
            "neverland_ingestion_syncs_total",
            "Source sync attempts by connector type and outcome.",
            ("connector_type", "outcome"),
            registry=self.registry,
        )
        self.ingestion_documents_total = Counter(
            "neverland_ingestion_documents_total",
            "Documents discovered or accepted for processing by connector type and outcome.",
            ("connector_type", "outcome"),
            registry=self.registry,
        )
        self.pipeline_documents_total = Counter(
            "neverland_pipeline_documents_total",
            "Document processing attempts by pipeline stage and outcome.",
            ("stage", "outcome"),
            registry=self.registry,
        )
        self.pipeline_stage_duration_seconds = Histogram(
            "neverland_pipeline_stage_duration_seconds",
            "Pipeline stage duration in seconds.",
            ("stage",),
            buckets=DOMAIN_DURATION_BUCKETS,
            registry=self.registry,
        )
        self.pipeline_document_bytes = Histogram(
            "neverland_pipeline_document_bytes",
            "Original document size in bytes by connector type.",
            ("connector_type",),
            buckets=DOCUMENT_BYTES_BUCKETS,
            registry=self.registry,
        )
        self.pipeline_chunks_total = Counter(
            "neverland_pipeline_chunks_total",
            "Pipeline chunk creation attempts by outcome.",
            ("outcome",),
            registry=self.registry,
        )
        self.dlq_records_total = Counter(
            "neverland_dlq_records_total",
            "Records sent to the dead-letter queue by reason and coarse source type.",
            ("reason", "source"),
            registry=self.registry,
        )
        self.dlq_pending = Gauge(
            "neverland_dlq_pending",
            "Current pending dead-letter queue records.",
            registry=self.registry,
        )
        self.search_requests_total = Counter(
            "neverland_search_requests_total",
            "Search requests by mode and outcome.",
            ("mode", "outcome"),
            registry=self.registry,
        )
        self.search_duration_seconds = Histogram(
            "neverland_search_duration_seconds",
            "End-to-end search duration in seconds by mode.",
            ("mode",),
            buckets=DOMAIN_DURATION_BUCKETS,
            registry=self.registry,
        )
        self.search_backend_duration_seconds = Histogram(
            "neverland_search_backend_duration_seconds",
            "Search backend call duration in seconds.",
            ("backend", "operation"),
            buckets=DOMAIN_DURATION_BUCKETS,
            registry=self.registry,
        )
        self.search_results_count = Histogram(
            "neverland_search_results_count",
            "Search result count by mode.",
            ("mode",),
            buckets=RESULT_COUNT_BUCKETS,
            registry=self.registry,
        )
        self.search_index_documents = Gauge(
            "neverland_search_index_documents",
            "Approximate indexed documents by backend.",
            ("backend",),
            registry=self.registry,
        )
        self.translation_requests_total = Counter(
            "neverland_translation_requests_total",
            "Translation requests by kind and outcome.",
            ("kind", "outcome"),
            registry=self.registry,
        )
        self.translation_duration_seconds = Histogram(
            "neverland_translation_duration_seconds",
            "Translation duration in seconds by kind.",
            ("kind",),
            buckets=DOMAIN_DURATION_BUCKETS,
            registry=self.registry,
        )
        self.translation_characters_total = Counter(
            "neverland_translation_characters_total",
            "Characters submitted for translation by kind.",
            ("kind",),
            registry=self.registry,
        )
        self.intelligence_tasks_total = Counter(
            "neverland_intelligence_tasks_total",
            "Intelligence tasks by task type and outcome.",
            ("task", "outcome"),
            registry=self.registry,
        )
        self.intelligence_task_duration_seconds = Histogram(
            "neverland_intelligence_task_duration_seconds",
            "Intelligence task duration in seconds by task type.",
            ("task",),
            buckets=DOMAIN_DURATION_BUCKETS,
            registry=self.registry,
        )
        self.ollama_requests_total = Counter(
            "neverland_ollama_requests_total",
            "Ollama requests by operation and outcome.",
            ("operation", "outcome"),
            registry=self.registry,
        )
        self.ollama_duration_seconds = Histogram(
            "neverland_ollama_duration_seconds",
            "Ollama request duration in seconds by operation.",
            ("operation",),
            buckets=DOMAIN_DURATION_BUCKETS,
            registry=self.registry,
        )
        self.rag_requests_total = Counter(
            "neverland_rag_requests_total",
            "Retrieval-augmented generation requests by outcome.",
            ("outcome",),
            registry=self.registry,
        )
        self.rag_duration_seconds = Histogram(
            "neverland_rag_duration_seconds",
            "Retrieval-augmented generation duration in seconds by phase.",
            ("phase",),
            buckets=DOMAIN_DURATION_BUCKETS,
            registry=self.registry,
        )
        self.rag_citations_count = Histogram(
            "neverland_rag_citations_count",
            "Retrieval-augmented generation citation count.",
            buckets=CITATION_COUNT_BUCKETS,
            registry=self.registry,
        )
        self.preview_requests_total = Counter(
            "neverland_preview_requests_total",
            "Preview requests by coarse MIME family and outcome.",
            ("mime_family", "outcome"),
            registry=self.registry,
        )
        self.download_requests_total = Counter(
            "neverland_download_requests_total",
            "Safe download attempts by outcome.",
            ("outcome",),
            registry=self.registry,
        )
        self.comments_total = Counter(
            "neverland_comments_total",
            "Comment operations by action and outcome.",
            ("action", "outcome"),
            registry=self.registry,
        )
        self.annotations_total = Counter(
            "neverland_annotations_total",
            "Annotation operations by action, visibility, and outcome.",
            ("action", "visibility", "outcome"),
            registry=self.registry,
        )
        self.subscriptions_total = Counter(
            "neverland_subscriptions_total",
            "Subscription operations by action and outcome.",
            ("action", "outcome"),
            registry=self.registry,
        )
        self.notifications_total = Counter(
            "neverland_notifications_total",
            "Notification events by event type and outcome.",
            ("event", "outcome"),
            registry=self.registry,
        )
        self.build_info.labels(
            version=safe_label_value(version),
            commit=safe_label_value(commit),
            environment=safe_label_value(environment),
        ).set(1)


def set_current_metrics(metrics: MetricsRegistry | None) -> Token[object | None]:
    """Bind the active request metrics registry to the current context."""
    return _CURRENT_METRICS.set(metrics)


def reset_current_metrics(token: Token[object | None]) -> None:
    """Reset the active request metrics registry context token."""
    _CURRENT_METRICS.reset(token)


def current_metrics() -> MetricsRegistry | None:
    """Return the metrics registry bound to the active request, if any."""
    metrics = _CURRENT_METRICS.get()
    return metrics if isinstance(metrics, MetricsRegistry) else None


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


def mime_family(mime_type: str | None) -> str:
    """Return a coarse, low-cardinality MIME family label."""
    if not mime_type:
        return "unknown"
    family = mime_type.split("/", maxsplit=1)[0].strip().lower()
    if family in {"text", "image", "audio", "video", "application", "message", "multipart"}:
        return family
    return "other"
