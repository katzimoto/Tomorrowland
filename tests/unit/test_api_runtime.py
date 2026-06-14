from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from fastapi.testclient import TestClient

from services.api.main import create_app
from shared.config import Settings


def _iter_routes(app: Any) -> list[Any]:
    """Recursively walk ``app.routes``, yielding every route that has ``.path``.

    Handles ``_IncludedRouter`` wrappers (FastAPI >=0.115) that don't carry
    ``.path`` themselves but contain sub-routes in ``.routes``.
    """
    result: list[Any] = []
    for route in app.routes:
        if hasattr(route, "path"):
            result.append(route)
        if hasattr(route, "routes"):
            result.extend(_iter_routes(route))
    return result


def test_health_route_is_public_runtime_probe() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    app = create_app(engine, Settings(_env_file=None, auth_provider="local", jwt_secret="x" * 32))
    route = next(route for route in _iter_routes(app) if route.path == "/health")

    assert route.endpoint() == {"status": "ok", "service": "api"}


def test_cors_allows_configured_origin() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    app = create_app(
        engine,
        Settings(
            _env_file=None,
            auth_provider="local",
            jwt_secret="x" * 32,
            cors_origins="https://tomorrowland.example",
        ),
    )
    client = TestClient(app)

    response = client.options(
        "/health",
        headers={
            "Origin": "https://tomorrowland.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://tomorrowland.example"


def test_cors_rejects_unconfigured_origin() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    app = create_app(
        engine,
        Settings(
            _env_file=None,
            auth_provider="local",
            jwt_secret="x" * 32,
            cors_origins="https://tomorrowland.example",
        ),
    )
    client = TestClient(app)

    response = client.options(
        "/health",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
