from __future__ import annotations

import logging
from io import StringIO
from unittest.mock import patch

import sqlalchemy as sa
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.api.observability import (
    configure_api_logging,
    install_enhanced_request_observability,
)
from shared.config import Settings


def test_structured_log_emitted_for_successful_request() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    app = create_app(engine, Settings(app_env="test", auth_provider="local"))

    @app.get("/hello")
    def hello() -> dict[str, str]:
        return {"ok": "yes"}

    with patch("services.api.main.logger.info") as mock_info:
        client = TestClient(app)
        response = client.get("/hello")

    assert response.status_code == 200
    mock_info.assert_called_once()
    args, kwargs = mock_info.call_args
    assert args[0] == "http_request_completed"
    assert kwargs["extra"]["component"] == "api"
    assert kwargs["extra"]["outcome"] == "success"


def test_structured_log_emitted_for_internal_server_error() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    app = create_app(engine, Settings(app_env="test", auth_provider="local"))

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("boom")

    with patch("services.api.main.logger.error") as mock_error:
        client = TestClient(app)
        response = client.get("/boom")

    assert response.status_code == 500
    assert "X-Request-ID" in response.headers
    mock_error.assert_called_once()
    args, kwargs = mock_error.call_args
    assert args[0] == "http_request_failed"
    assert kwargs["extra"]["error_type"] == "RuntimeError"
    assert kwargs["extra"]["component"] == "api"
    assert kwargs["extra"]["outcome"] == "failure"


def test_enhanced_observability_logs_unhandled_errors() -> None:
    engine = sa.create_engine("sqlite:///:memory:")
    app = create_app(engine, Settings(app_env="test", auth_provider="local"))
    install_enhanced_request_observability(app)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("boom")

    client = TestClient(app)
    logger = logging.getLogger("services.api.observability")
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    original_level = logger.level
    original_propagate = logger.propagate
    try:
        logger.addHandler(handler)
        logger.setLevel(logging.ERROR)
        logger.propagate = False

        response = client.get("/boom", headers={"X-Request-ID": "connector-debug"})
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)
        logger.propagate = original_propagate

    text = stream.getvalue()
    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "connector-debug"
    assert "Unhandled API request error" in text
    assert "request_id=connector-debug" in text
    assert "method=GET" in text
    assert "path=/boom" in text
    assert "error_type=RuntimeError" in text


def test_configure_api_logging_sets_expected_service_loggers() -> None:
    logger_names = ["", "services", "shared", "uvicorn.error", "uvicorn.access"]
    loggers = {name: logging.getLogger(name) for name in logger_names}
    original_levels = {name: logger.level for name, logger in loggers.items()}
    original_root_handlers = list(logging.getLogger().handlers)
    try:
        configure_api_logging("debug")

        assert logging.getLogger().level == logging.DEBUG
        assert logging.getLogger("services").level == logging.DEBUG
        assert logging.getLogger("shared").level == logging.DEBUG
        assert logging.getLogger("uvicorn.error").level == logging.DEBUG
        assert logging.getLogger("uvicorn.access").level == logging.DEBUG
    finally:
        for name, level in original_levels.items():
            logging.getLogger(name).setLevel(level)
        logging.getLogger().handlers = original_root_handlers
