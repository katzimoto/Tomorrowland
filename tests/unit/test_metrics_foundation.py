from __future__ import annotations

import re
from uuid import uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from services.api.main import create_app
from shared.config import Settings
from shared.metrics import metric_names, normalize_route_template


def _client() -> TestClient:
    engine = sa.create_engine("sqlite:///:memory:")
    app = create_app(
        engine,
        Settings(
            app_env="test",
            app_version="9.9.9",
            build_commit="abc123",
            auth_provider="local",
            jwt_secret="x" * 32,
        ),
    )
    return TestClient(app)


def test_metrics_endpoint_exposes_prometheus_runtime_and_build_metrics() -> None:
    client = _client()

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    metric_families = list(text_string_to_metric_families(response.text))
    names = {family.name for family in metric_families}
    assert "tomorrowland_build_info" in names
    assert "process_virtual_memory_bytes" in names
    assert "python_gc_objects_collected" in names
    assert 'version="9.9.9"' in response.text
    assert 'commit="abc123"' in response.text
    assert 'environment="test"' in response.text


def test_http_metrics_increment_with_route_templates_not_raw_ids() -> None:
    client = _client()
    raw_id = str(uuid4())

    response = client.post(f"/admin/ingestion/{raw_id}/sync-now")

    assert response.status_code == 401
    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200
    metrics_text = metrics_response.text
    expected_count = (
        'tomorrowland_http_requests_total{method="POST",'
        'route="/admin/ingestion/{source_id}/sync-now",status_class="4xx"} 1.0'
    )
    assert expected_count in metrics_text
    assert raw_id not in metrics_text
    assert "source_id" in metrics_text


def test_metrics_are_isolated_per_app_instance() -> None:
    first = _client()
    second = _client()

    first.get("/health")
    second.get("/health")

    first_metrics = first.get("/metrics").text
    second_metrics = second.get("/metrics").text
    pattern = re.compile(
        r'tomorrowland_http_requests_total\{method="GET",route="/health",status_class="2xx"\} 1\.0'
    )
    assert pattern.search(first_metrics)
    assert pattern.search(second_metrics)


def test_normalize_route_template_rejects_raw_paths_and_keeps_templates() -> None:
    assert normalize_route_template("/documents/{doc_id}") == "/documents/{doc_id}"
    assert normalize_route_template("documents/abc") == "__unknown__"


def test_metric_names_helper_lists_samples() -> None:
    client = _client()
    app = client.app

    names = set(metric_names(app.state.metrics.registry))

    assert "tomorrowland_build_info" in names
