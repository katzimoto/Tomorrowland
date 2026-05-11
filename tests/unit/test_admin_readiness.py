from __future__ import annotations

from uuid import UUID

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.api.readiness import HttpGetter, ReadinessChecker
from services.auth.jwt import JwtService
from services.auth.models import UserIdentity
from shared.config import Settings

TEST_JWT_SECRET = "x" * 32


class Clock:
    """Deterministic clock for readiness cache tests."""

    def __init__(self) -> None:
        self.monotonic_value = 100.0
        self.perf_value = 200.0

    def monotonic(self) -> float:
        return self.monotonic_value

    def perf_counter(self) -> float:
        self.perf_value += 0.001
        return self.perf_value


def _token(*, is_admin: bool) -> str:
    payload = UserIdentity(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        email="admin@example.com" if is_admin else "user@example.com",
        display_name="Admin" if is_admin else "User",
        auth_source="local",
        is_admin=is_admin,
        groups=[UUID("00000000-0000-0000-0000-000000000002")],
    )
    return JwtService(TEST_JWT_SECRET).encode(payload)


def _checker(
    migrated_engine: Engine,
    clock: Clock,
    http_get: HttpGetter,
    settings: Settings | None = None,
) -> ReadinessChecker:
    app = create_app(
        migrated_engine,
        settings or Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
    )
    return ReadinessChecker(
        engine=migrated_engine,
        settings=app.state.settings,
        metrics=app.state.metrics,
        cache_ttl_seconds=15,
        http_get=http_get,
        monotonic=clock.monotonic,
        perf_counter=clock.perf_counter,
    )


def test_admin_readiness_reports_ok_and_caches_probe_results(migrated_engine: Engine) -> None:
    clock = Clock()
    calls: list[str] = []

    def http_get(url: str, *, timeout: float) -> httpx.Response:
        calls.append(url)
        assert timeout == 2.0
        return httpx.Response(200, request=httpx.Request("GET", url))

    checker = _checker(migrated_engine, clock, http_get)

    first = checker.check()
    second = checker.check()

    assert first is second
    assert first["status"] == "ok"
    assert first["service"] == "api"
    assert first["checked_at"].endswith("Z")
    assert set(first["dependencies"]) == {
        "postgres",
        "elasticsearch",
        "qdrant",
        "libretranslate",
        "ollama",
    }
    assert all(dep["status"] == "ok" for dep in first["dependencies"].values())
    assert len(calls) == 4

    clock.monotonic_value += 16
    checker.check()

    assert len(calls) == 8


def test_admin_readiness_reports_degraded_for_optional_dependency_failure(
    migrated_engine: Engine,
) -> None:
    clock = Clock()

    def http_get(url: str, *, timeout: float) -> httpx.Response:
        if url.endswith("/api/tags"):
            raise httpx.ConnectError("ollama unavailable")
        return httpx.Response(200, request=httpx.Request("GET", url))

    response = _checker(migrated_engine, clock, http_get).check()

    assert response["status"] == "degraded"
    assert response["dependencies"]["ollama"]["status"] == "down"
    assert response["dependencies"]["postgres"]["status"] == "ok"


def test_admin_readiness_reports_down_for_core_dependency_failure(migrated_engine: Engine) -> None:
    clock = Clock()

    def http_get(url: str, *, timeout: float) -> httpx.Response:
        if "elasticsearch" in url:
            return httpx.Response(503, request=httpx.Request("GET", url))
        return httpx.Response(200, request=httpx.Request("GET", url))

    response = _checker(migrated_engine, clock, http_get).check()

    assert response["status"] == "down"
    assert response["dependencies"]["elasticsearch"]["status"] == "down"


def test_admin_readiness_updates_dependency_metrics(migrated_engine: Engine) -> None:
    clock = Clock()

    def http_get(url: str, *, timeout: float) -> httpx.Response:
        if url.endswith("/languages"):
            raise httpx.ConnectError("libretranslate unavailable")
        return httpx.Response(200, request=httpx.Request("GET", url))

    app = create_app(
        migrated_engine,
        Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
    )
    checker = ReadinessChecker(
        engine=migrated_engine,
        settings=app.state.settings,
        metrics=app.state.metrics,
        http_get=http_get,
        monotonic=clock.monotonic,
        perf_counter=clock.perf_counter,
    )

    checker.check()
    samples = {
        sample.name: sample
        for metric in app.state.metrics.registry.collect()
        for sample in metric.samples
        if sample.name == "tomorrowland_dependency_up"
        and sample.labels.get("dependency") == "libretranslate"
    }

    assert samples["tomorrowland_dependency_up"].value == 0


def test_admin_readiness_route_requires_admin(migrated_engine: Engine) -> None:
    app = create_app(
        migrated_engine,
        Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
    )
    client = TestClient(app)

    missing = client.get("/admin/readiness")
    user = client.get(
        "/admin/readiness",
        headers={"Authorization": f"Bearer {_token(is_admin=False)}"},
    )

    assert missing.status_code == 401
    assert user.status_code == 403


def test_admin_readiness_route_returns_cached_response(migrated_engine: Engine) -> None:
    app = create_app(
        migrated_engine,
        Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
    )
    app.state.readiness_checker = type(
        "FakeReadinessChecker",
        (),
        {"check": lambda self: {"status": "ok", "service": "api", "dependencies": {}}},
    )()
    client = TestClient(app)

    response = client.get(
        "/admin/readiness",
        headers={"Authorization": f"Bearer {_token(is_admin=True)}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
