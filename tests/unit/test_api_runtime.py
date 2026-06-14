from __future__ import annotations

import sqlalchemy as sa
from fastapi.testclient import TestClient

from services.api.main import create_app
from shared.config import Settings


def test_health_route_is_public_runtime_probe() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    app = create_app(
        engine,
        Settings(
            _env_file=None,
            auth_provider="local",
            jwt_secret="x" * 32,
            feature_meilisearch_search=False,
            feature_document_chat=False,
        ),
    )
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api"}


def test_cors_allows_configured_origin() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    app = create_app(
        engine,
        Settings(
            _env_file=None,
            auth_provider="local",
            jwt_secret="x" * 32,
            cors_origins="https://tomorrowland.example",
            feature_meilisearch_search=False,
            feature_document_chat=False,
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
            feature_meilisearch_search=False,
            feature_document_chat=False,
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
