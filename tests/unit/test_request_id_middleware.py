from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi.testclient import TestClient

from services.api.main import create_app
from shared.config import Settings


def _client() -> TestClient:
    engine = sa.create_engine("sqlite:///:memory:")
    app = create_app(engine, Settings(app_env="test", auth_provider="local", jwt_secret="x" * 32))
    return TestClient(app)


def test_request_id_header_is_generated_when_absent() -> None:
    client = _client()

    response = client.get("/health")

    assert response.status_code == 200
    request_id = response.headers["X-Request-ID"]
    assert UUID(request_id)


def test_request_id_header_is_echoed_when_present() -> None:
    client = _client()

    response = client.get("/health", headers={"X-Request-ID": "support-ticket-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "support-ticket-123"


def test_request_id_header_is_echoed_on_auth_errors() -> None:
    client = _client()

    response = client.get("/auth/me", headers={"X-Request-ID": "auth-debug"})

    assert response.status_code == 401
    assert response.headers["X-Request-ID"] == "auth-debug"


def test_request_id_header_is_echoed_on_unhandled_errors() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    app = create_app(engine, Settings(app_env="test", auth_provider="local", jwt_secret="x" * 32))

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("boom")

    client = TestClient(app)

    response = client.get("/boom", headers={"X-Request-ID": "boom-debug"})

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "boom-debug"
    assert response.text == "Internal Server Error"
    assert (
        'neverland_http_exceptions_total{error_type="RuntimeError",route="/boom"} 1.0'
        in client.get("/metrics").text
    )
