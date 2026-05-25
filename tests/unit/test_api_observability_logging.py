from __future__ import annotations

import logging

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.api.observability import install_enhanced_request_observability
from shared.config import Settings


def test_enhanced_observability_logs_unhandled_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    app = create_app(engine, Settings(_env_file=None, app_env="test", auth_provider="local"))
    install_enhanced_request_observability(app)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("boom")

    client = TestClient(app)

    with caplog.at_level(logging.ERROR, logger="services.api.observability"):
        response = client.get("/boom", headers={"X-Request-ID": "connector-debug"})

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "connector-debug"
    assert "Unhandled API request error" in caplog.text
    assert "request_id=connector-debug" in caplog.text
    assert "method=GET" in caplog.text
    assert "path=/boom" in caplog.text
    assert "error_type=RuntimeError" in caplog.text
