from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from services.search.meili_settings import apply_index_settings

if TYPE_CHECKING:
    from services.search.meili_provider import MeilisearchSearchProvider
    from shared.config import Settings
    from shared.metrics import MetricsRegistry

log = logging.getLogger(__name__)

_MEILI_DEPENDENCY = "meilisearch"
_MEILI_STAGE = "meilisearch_index"


# ---------------------------------------------------------------------------
# Feature-flag helpers
# ---------------------------------------------------------------------------


def is_search_enabled(settings: Settings) -> bool:
    return settings.feature_meilisearch_search


def is_shadow_enabled(settings: Settings) -> bool:
    return settings.feature_meilisearch_shadow_index


# ---------------------------------------------------------------------------
# Startup initialization
# ---------------------------------------------------------------------------


def initialize_meilisearch(client: object, settings: Settings) -> None:
    """Apply index settings to live (and optionally shadow) index at startup.

    Idempotent — safe to call on every application restart.
    """
    log.info("meilisearch.init: applying settings to live index")
    apply_index_settings(client, shadow=False)

    if is_shadow_enabled(settings):
        log.info("meilisearch.init: applying settings to shadow index")
        apply_index_settings(client, shadow=True)


# ---------------------------------------------------------------------------
# Health probe
# ---------------------------------------------------------------------------


def meilisearch_health_probe(
    provider: MeilisearchSearchProvider,
    metrics: MetricsRegistry | None = None,
) -> dict[str, Any]:
    """Run a health check and emit dependency metrics.

    Returns the raw dict from :meth:`MeilisearchSearchProvider.health_check`
    so callers can include it in ``/health`` endpoint responses.
    """
    result = provider.health_check()
    ok: bool = result.get("ok", False)
    latency_s: float = result.get("latency_ms", 0.0) / 1000.0

    if metrics is not None:
        metrics.dependency_up.labels(dependency=_MEILI_DEPENDENCY).set(1 if ok else 0)
        metrics.dependency_latency_seconds.labels(
            dependency=_MEILI_DEPENDENCY, operation="health"
        ).observe(latency_s)

    log.info(
        "meilisearch.health",
        extra={"ok": ok, "latency_ms": result.get("latency_ms"), "error": result.get("error")},
    )
    return result


# ---------------------------------------------------------------------------
# Search observability
# ---------------------------------------------------------------------------


def record_search_metrics(
    metrics: MetricsRegistry | None,
    *,
    duration_s: float,
    hits: int,
    outcome: str,
) -> None:
    """Emit search backend metrics after a Meilisearch query completes."""
    if metrics is None:
        return
    metrics.search_backend_duration_seconds.labels(
        backend=_MEILI_DEPENDENCY, operation="search"
    ).observe(duration_s)
    metrics.search_requests_total.labels(mode=_MEILI_DEPENDENCY, outcome=outcome).inc()


# ---------------------------------------------------------------------------
# Index / write observability
# ---------------------------------------------------------------------------


def record_index_metrics(
    metrics: MetricsRegistry | None,
    *,
    duration_s: float,
    chunk_count: int,
    outcome: str,
) -> None:
    """Emit pipeline metrics after a Meilisearch index (write) operation completes."""
    if metrics is None:
        return
    metrics.pipeline_stage_duration_seconds.labels(stage=_MEILI_STAGE).observe(duration_s)
    metrics.pipeline_documents_total.labels(stage=_MEILI_STAGE, outcome=outcome).inc(chunk_count)
