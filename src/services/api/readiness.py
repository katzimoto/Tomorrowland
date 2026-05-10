from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, TypedDict

import httpx
import sqlalchemy as sa
from sqlalchemy import Engine

from shared.config import Settings
from shared.metrics import MetricsRegistry

DependencyStatus = Literal["ok", "degraded", "down"]
OverallStatus = Literal["ok", "degraded", "down"]

READINESS_DEPENDENCIES: tuple[str, ...] = (
    "postgres",
    "elasticsearch",
    "qdrant",
    "libretranslate",
    "ollama",
)


class DependencyResult(TypedDict):
    """JSON-serializable status and latency for one dependency probe."""

    status: DependencyStatus
    latency_ms: int


class ReadinessResponse(TypedDict):
    """JSON-serializable readiness response."""

    status: OverallStatus
    service: str
    checked_at: str
    dependencies: dict[str, DependencyResult]


class HttpGetter(Protocol):
    """Protocol for injectable HTTP GET calls used by readiness probes."""

    def __call__(self, url: str, *, timeout: float) -> httpx.Response: ...


@dataclass(frozen=True)
class _CachedReadiness:
    checked_at_monotonic: float
    response: ReadinessResponse


class ReadinessChecker:
    """Cached dependency readiness checks for the admin readiness endpoint."""

    def __init__(
        self,
        *,
        engine: Engine,
        settings: Settings,
        metrics: MetricsRegistry,
        cache_ttl_seconds: float = 15.0,
        probe_timeout_seconds: float = 2.0,
        http_get: HttpGetter = httpx.get,
        monotonic: Callable[[], float] = time.monotonic,
        perf_counter: Callable[[], float] = time.perf_counter,
    ) -> None:
        """Initialize readiness probes with short timeouts and a small result cache."""
        self._engine = engine
        self._settings = settings
        self._metrics = metrics
        self._cache_ttl_seconds = cache_ttl_seconds
        self._probe_timeout_seconds = probe_timeout_seconds
        self._http_get = http_get
        self._monotonic = monotonic
        self._perf_counter = perf_counter
        self._cached: _CachedReadiness | None = None

    def check(self) -> ReadinessResponse:
        """Return cached readiness when fresh, otherwise probe dependencies."""
        now = self._monotonic()
        if (
            self._cached is not None
            and now - self._cached.checked_at_monotonic < self._cache_ttl_seconds
        ):
            self._set_dependency_gauges(self._cached.response)
            return self._cached.response

        dependencies = {
            "postgres": self._probe_postgres(),
            "elasticsearch": self._probe_http(f"{self._settings.elastic_url.rstrip('/')}/"),
            "qdrant": self._probe_http(f"{self._settings.qdrant_url.rstrip('/')}/readyz"),
            "libretranslate": self._probe_http(
                f"{self._settings.libretranslate_url.rstrip('/')}/languages"
            ),
            "ollama": self._probe_http(f"{self._settings.ollama_url.rstrip('/')}/api/tags"),
        }
        response = ReadinessResponse(
            status=self._overall_status(dependencies),
            service="api",
            checked_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            dependencies=dependencies,
        )
        self._cached = _CachedReadiness(checked_at_monotonic=now, response=response)
        self._record_dependency_metrics(response, observe_latency=True)
        return response

    def _probe_postgres(self) -> DependencyResult:
        return self._timed_probe(lambda: self._execute_postgres_probe())

    def _execute_postgres_probe(self) -> None:
        with self._engine.begin() as connection:
            connection.execute(sa.text("SELECT 1"))

    def _probe_http(self, url: str) -> DependencyResult:
        def execute_probe() -> None:
            response = self._http_get(url, timeout=self._probe_timeout_seconds)
            response.raise_for_status()

        return self._timed_probe(execute_probe)

    def _timed_probe(self, probe: Callable[[], None]) -> DependencyResult:
        start = self._perf_counter()
        try:
            probe()
            status: DependencyStatus = "ok"
        except Exception:
            status = "down"
        latency_ms = max(0, round((self._perf_counter() - start) * 1000))
        return {"status": status, "latency_ms": latency_ms}

    def _overall_status(self, dependencies: dict[str, DependencyResult]) -> OverallStatus:
        if any(
            dependencies[name]["status"] == "down"
            for name in ("postgres", "elasticsearch", "qdrant")
        ):
            return "down"
        optional_down = dependencies["libretranslate"]["status"] == "down" or (
            self._ollama_affects_readiness() and dependencies["ollama"]["status"] == "down"
        )
        if optional_down:
            return "degraded"
        return "ok"

    def _ollama_affects_readiness(self) -> bool:
        return any(
            (
                self._settings.feature_rag_qa,
                self._settings.feature_summarization,
                self._settings.feature_entity_extraction,
                self._settings.feature_auto_tagging,
            )
        )

    def _set_dependency_gauges(self, response: ReadinessResponse) -> None:
        self._record_dependency_metrics(response, observe_latency=False)

    def _record_dependency_metrics(
        self, response: ReadinessResponse, *, observe_latency: bool
    ) -> None:
        dependencies = response["dependencies"]
        for name in READINESS_DEPENDENCIES:
            result = dependencies.get(name)
            if result is None:
                continue
            up = 1.0 if result["status"] == "ok" else 0.0
            self._metrics.dependency_up.labels(name).set(up)
            if observe_latency:
                self._metrics.dependency_latency_seconds.labels(name, "readiness").observe(
                    float(result["latency_ms"]) / 1000
                )
