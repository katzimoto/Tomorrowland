from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from services.api.main import create_app
from shared.config import Settings


def _client() -> TestClient:
    """Create a minimal TestClient wired to an in-memory SQLite app."""
    engine = sa.create_engine("sqlite:///:memory:")
    app = create_app(
        engine,
        Settings(
            _env_file=None,
            app_env="test",
            app_version="9.9.9",
            build_commit="abc123",
            auth_provider="local",
            jwt_secret="x" * 32,
        ),
    )
    return TestClient(app)


def test_metrics_endpoint_returns_prometheus_text_format() -> None:
    """The /metrics endpoint returns valid Prometheus text format."""
    client = _client()

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")

    # Must be parseable as Prometheus metric families
    families = list(text_string_to_metric_families(response.text))
    assert len(families) > 0, "expected at least one metric family"


def test_metrics_includes_required_http_metrics() -> None:
    """After at least one request, the metrics output contains request count,
    latency, and error count per the acceptance criteria."""
    client = _client()

    # Make requests so HTTP counters have data
    client.get("/health")
    client.get("/nonexistent/404")

    response = client.get("/metrics")
    assert response.status_code == 200
    text = response.text

    # The counters must appear in the Prometheus text output
    assert "tomorrowland_http_requests_total{" in text, "request_count metric missing"
    assert "tomorrowland_http_request_duration_seconds" in text, (
        "request_latency_seconds metric missing"
    )

    # Exceptions may not be triggered in a clean run, but the collector must exist
    assert "tomorrowland_http_exceptions_total" in text, "error_count metric missing"


def test_metrics_route_labels_use_templates_not_raw_values() -> None:
    """Metric route labels must not contain user-specified path values like UUIDs."""
    client = _client()
    raw_id = str(uuid4())

    # Hit a parameterized admin route (expects 401 — no token)
    client.post(f"/admin/ingestion/{raw_id}/sync-now")

    metrics_text = client.get("/metrics").text

    # The route template should appear, not the raw UUID
    assert 'route="/admin/ingestion/{source_id}/sync-now"' in metrics_text
    assert raw_id not in metrics_text


def test_metrics_includes_build_info() -> None:
    """The /metrics endpoint exposes build metadata as specified."""
    client = _client()

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "tomorrowland_build_info{" in response.text
    assert 'version="9.9.9"' in response.text
    assert 'commit="abc123"' in response.text
    assert 'environment="test"' in response.text


class TestMetricsContentType:
    """Grouping for content-type related assertions."""

    def test_content_type_is_prometheus(self) -> None:
        """The /metrics endpoint must return the Prometheus content type."""
        client = _client()

        response = client.get("/metrics")

        # prometheus_client.CONTENT_TYPE_LATEST should be matched
        ct = response.headers["content-type"]
        assert "text/plain" in ct
        assert "version=0.0.4" in ct or "version=" in ct
