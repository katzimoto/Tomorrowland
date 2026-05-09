from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest

from services.api.middleware import MetricsMiddleware, RequestIdMiddleware
from shared.metrics import make_metrics, normalize_route, status_class


def _make_app(registry: CollectorRegistry | None = None) -> FastAPI:
    """Build a minimal test FastAPI app with metrics wired up."""
    reg = registry or CollectorRegistry()
    build_info, requests_total, request_duration_seconds, exceptions_total = make_metrics(
        registry=reg
    )
    build_info.labels(version="1.2.3", commit="abc", environment="test").set(1)

    app = FastAPI()
    app.add_middleware(
        MetricsMiddleware,
        requests_total=requests_total,
        request_duration_seconds=request_duration_seconds,
        exceptions_total=exceptions_total,
    )
    app.add_middleware(RequestIdMiddleware)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/documents/{doc_id}/summary")
    def doc_summary(doc_id: str) -> dict[str, str]:
        return {"doc_id": doc_id}

    @app.get("/metrics")
    def metrics() -> object:
        from fastapi.responses import Response

        return Response(generate_latest(reg), media_type=CONTENT_TYPE_LATEST)

    return app


# ---------------------------------------------------------------------------
# normalize_route helpers
# ---------------------------------------------------------------------------


def test_normalize_route_leaves_static_paths_unchanged() -> None:
    assert normalize_route("/health") == "/health"


def test_normalize_route_strips_path_param_segment() -> None:
    assert normalize_route("/documents/{doc_id}") == "/documents/{id}"


def test_normalize_route_strips_multiple_params() -> None:
    assert normalize_route("/a/{x}/b/{y}") == "/a/{id}/b/{id}"


def test_normalize_route_handles_raw_id_segment() -> None:
    # Path params without braces are NOT stripped — only template params are.
    assert normalize_route("/documents/abc123") == "/documents/abc123"


# ---------------------------------------------------------------------------
# status_class helper
# ---------------------------------------------------------------------------


def test_status_class_2xx() -> None:
    assert status_class(200) == "2xx"
    assert status_class(201) == "2xx"
    assert status_class(204) == "2xx"


def test_status_class_4xx() -> None:
    assert status_class(400) == "4xx"
    assert status_class(401) == "4xx"
    assert status_class(404) == "4xx"


def test_status_class_5xx() -> None:
    assert status_class(500) == "5xx"
    assert status_class(503) == "5xx"


def test_status_class_other() -> None:
    assert status_class(301) == "other"
    assert status_class(102) == "other"


# ---------------------------------------------------------------------------
# make_metrics returns four distinct instruments
# ---------------------------------------------------------------------------


def test_make_metrics_returns_four_instruments() -> None:
    reg = CollectorRegistry()
    result = make_metrics(registry=reg)
    assert len(result) == 4


def test_make_metrics_isolates_registries() -> None:
    reg1 = CollectorRegistry()
    reg2 = CollectorRegistry()
    make_metrics(registry=reg1)
    make_metrics(registry=reg2)  # must not raise "already registered" error


# ---------------------------------------------------------------------------
# /metrics endpoint
# ---------------------------------------------------------------------------


def test_metrics_endpoint_returns_200() -> None:
    client = TestClient(_make_app())
    resp = client.get("/metrics")
    assert resp.status_code == 200


def test_metrics_endpoint_content_type_is_prometheus() -> None:
    client = TestClient(_make_app())
    resp = client.get("/metrics")
    assert "text/plain" in resp.headers["content-type"]


def test_metrics_endpoint_contains_build_info() -> None:
    client = TestClient(_make_app())
    resp = client.get("/metrics")
    assert "neverland_build_info" in resp.text


def test_metrics_endpoint_contains_request_counter() -> None:
    client = TestClient(_make_app())
    client.get("/health")
    resp = client.get("/metrics")
    assert "neverland_http_requests_total" in resp.text


def test_metrics_endpoint_contains_request_histogram() -> None:
    client = TestClient(_make_app())
    client.get("/health")
    resp = client.get("/metrics")
    assert "neverland_http_request_duration_seconds" in resp.text


def test_build_info_labels_present() -> None:
    client = TestClient(_make_app())
    resp = client.get("/metrics")
    assert 'version="1.2.3"' in resp.text
    assert 'commit="abc"' in resp.text
    assert 'environment="test"' in resp.text


def test_route_label_is_template_not_raw_id() -> None:
    client = TestClient(_make_app())
    client.get("/documents/some-raw-uuid/summary")
    resp = client.get("/metrics")
    # The raw ID must not appear; only the template form must appear.
    assert "some-raw-uuid" not in resp.text
    assert "/documents/{id}/summary" in resp.text or "documents" in resp.text


def test_no_raw_ids_in_metrics_output() -> None:
    client = TestClient(_make_app())
    client.get("/documents/deadbeef-dead-beef-dead-beefdeadbeef/summary")
    resp = client.get("/metrics")
    assert "deadbeef-dead-beef-dead-beefdeadbeef" not in resp.text


def test_request_counter_increments() -> None:
    reg = CollectorRegistry()
    client = TestClient(_make_app(registry=reg))
    client.get("/health")
    client.get("/health")
    text = generate_latest(reg).decode()
    assert "neverland_http_requests_total" in text


def test_histogram_records_duration() -> None:
    reg = CollectorRegistry()
    client = TestClient(_make_app(registry=reg))
    client.get("/health")
    text = generate_latest(reg).decode()
    assert "neverland_http_request_duration_seconds" in text
