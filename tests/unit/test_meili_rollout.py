from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from services.search.meili_rollout import (
    initialize_meilisearch,
    is_search_enabled,
    is_shadow_enabled,
    meilisearch_health_probe,
    record_index_metrics,
    record_search_metrics,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(*, search: bool = False, shadow: bool = False) -> MagicMock:
    s = MagicMock()
    s.feature_meilisearch_search = search
    s.feature_meilisearch_shadow_index = shadow
    return s


def _provider(*, ok: bool = True, latency_ms: float = 12.0) -> MagicMock:
    p = MagicMock()
    result: dict = {"ok": ok, "latency_ms": latency_ms}
    if not ok:
        result["error"] = "connection refused"
    p.health_check.return_value = result
    return p


def _metrics() -> MagicMock:
    m = MagicMock()
    # Simulate chained label calls returning a fresh mock each time
    m.dependency_up.labels.return_value = MagicMock()
    m.dependency_latency_seconds.labels.return_value = MagicMock()
    m.search_backend_duration_seconds.labels.return_value = MagicMock()
    m.search_requests_total.labels.return_value = MagicMock()
    m.pipeline_stage_duration_seconds.labels.return_value = MagicMock()
    m.pipeline_documents_total.labels.return_value = MagicMock()
    return m


# ---------------------------------------------------------------------------
# is_search_enabled / is_shadow_enabled
# ---------------------------------------------------------------------------


def test_is_search_enabled_false_by_default() -> None:
    assert is_search_enabled(_settings(search=False)) is False


def test_is_search_enabled_true_when_set() -> None:
    assert is_search_enabled(_settings(search=True)) is True


def test_is_shadow_enabled_false_by_default() -> None:
    assert is_shadow_enabled(_settings(shadow=False)) is False


def test_is_shadow_enabled_true_when_set() -> None:
    assert is_shadow_enabled(_settings(shadow=True)) is True


# ---------------------------------------------------------------------------
# initialize_meilisearch
# ---------------------------------------------------------------------------


@patch("services.search.meili_rollout.apply_index_settings")
def test_initialize_applies_live_index_always(mock_apply: MagicMock) -> None:
    client = MagicMock()
    initialize_meilisearch(client, _settings(search=True, shadow=False))
    mock_apply.assert_any_call(client, shadow=False)


@patch("services.search.meili_rollout.apply_index_settings")
def test_initialize_applies_shadow_when_flag_on(mock_apply: MagicMock) -> None:
    client = MagicMock()
    initialize_meilisearch(client, _settings(shadow=True))
    mock_apply.assert_any_call(client, shadow=True)


@patch("services.search.meili_rollout.apply_index_settings")
def test_initialize_skips_shadow_when_flag_off(mock_apply: MagicMock) -> None:
    client = MagicMock()
    initialize_meilisearch(client, _settings(shadow=False))
    shadow_calls = [c for c in mock_apply.call_args_list if c == call(client, shadow=True)]
    assert shadow_calls == []


@patch("services.search.meili_rollout.apply_index_settings")
def test_initialize_calls_apply_twice_when_shadow_on(mock_apply: MagicMock) -> None:
    client = MagicMock()
    initialize_meilisearch(client, _settings(shadow=True))
    assert mock_apply.call_count == 2


@patch("services.search.meili_rollout.apply_index_settings")
def test_initialize_calls_apply_once_when_shadow_off(mock_apply: MagicMock) -> None:
    client = MagicMock()
    initialize_meilisearch(client, _settings(shadow=False))
    assert mock_apply.call_count == 1


# ---------------------------------------------------------------------------
# meilisearch_health_probe
# ---------------------------------------------------------------------------


def test_health_probe_returns_provider_result() -> None:
    provider = _provider(ok=True, latency_ms=5.0)
    result = meilisearch_health_probe(provider)
    assert result["ok"] is True
    assert result["latency_ms"] == pytest.approx(5.0)


def test_health_probe_sets_dependency_up_gauge_on_ok() -> None:
    provider = _provider(ok=True, latency_ms=10.0)
    metrics = _metrics()
    meilisearch_health_probe(provider, metrics)
    metrics.dependency_up.labels.assert_called_with(dependency="meilisearch")
    metrics.dependency_up.labels().set.assert_called_with(1)


def test_health_probe_sets_dependency_up_gauge_on_failure() -> None:
    provider = _provider(ok=False, latency_ms=0.0)
    metrics = _metrics()
    meilisearch_health_probe(provider, metrics)
    metrics.dependency_up.labels().set.assert_called_with(0)


def test_health_probe_observes_latency() -> None:
    provider = _provider(ok=True, latency_ms=200.0)
    metrics = _metrics()
    meilisearch_health_probe(provider, metrics)
    metrics.dependency_latency_seconds.labels.assert_called_with(
        dependency="meilisearch", operation="health"
    )
    metrics.dependency_latency_seconds.labels().observe.assert_called_with(pytest.approx(0.2))


def test_health_probe_skips_metrics_when_none() -> None:
    # Must not raise even when metrics=None
    provider = _provider(ok=True)
    result = meilisearch_health_probe(provider, metrics=None)
    assert result["ok"] is True


def test_health_probe_calls_provider_health_check_once() -> None:
    provider = _provider()
    meilisearch_health_probe(provider)
    provider.health_check.assert_called_once()


# ---------------------------------------------------------------------------
# record_search_metrics
# ---------------------------------------------------------------------------


def test_record_search_metrics_emits_duration() -> None:
    metrics = _metrics()
    record_search_metrics(metrics, duration_s=0.05, hits=10, outcome="ok")
    metrics.search_backend_duration_seconds.labels.assert_called_with(
        backend="meilisearch", operation="search"
    )
    metrics.search_backend_duration_seconds.labels().observe.assert_called_with(pytest.approx(0.05))


def test_record_search_metrics_emits_request_counter() -> None:
    metrics = _metrics()
    record_search_metrics(metrics, duration_s=0.05, hits=10, outcome="ok")
    metrics.search_requests_total.labels.assert_called_with(mode="meilisearch", outcome="ok")
    metrics.search_requests_total.labels().inc.assert_called_once()


def test_record_search_metrics_error_outcome() -> None:
    metrics = _metrics()
    record_search_metrics(metrics, duration_s=1.5, hits=0, outcome="connection_error")
    metrics.search_requests_total.labels.assert_called_with(
        mode="meilisearch", outcome="connection_error"
    )


def test_record_search_metrics_noop_when_metrics_none() -> None:
    # Must not raise
    record_search_metrics(None, duration_s=0.1, hits=5, outcome="ok")


# ---------------------------------------------------------------------------
# record_index_metrics
# ---------------------------------------------------------------------------


def test_record_index_metrics_emits_stage_duration() -> None:
    metrics = _metrics()
    record_index_metrics(metrics, duration_s=0.3, chunk_count=5, outcome="ok")
    metrics.pipeline_stage_duration_seconds.labels.assert_called_with(stage="meilisearch_index")
    metrics.pipeline_stage_duration_seconds.labels().observe.assert_called_with(pytest.approx(0.3))


def test_record_index_metrics_increments_by_chunk_count() -> None:
    metrics = _metrics()
    record_index_metrics(metrics, duration_s=0.1, chunk_count=7, outcome="ok")
    metrics.pipeline_documents_total.labels.assert_called_with(
        stage="meilisearch_index", outcome="ok"
    )
    metrics.pipeline_documents_total.labels().inc.assert_called_with(7)


def test_record_index_metrics_error_outcome() -> None:
    metrics = _metrics()
    record_index_metrics(metrics, duration_s=0.0, chunk_count=0, outcome="timeout")
    metrics.pipeline_documents_total.labels.assert_called_with(
        stage="meilisearch_index", outcome="timeout"
    )


def test_record_index_metrics_noop_when_metrics_none() -> None:
    # Must not raise
    record_index_metrics(None, duration_s=0.1, chunk_count=3, outcome="ok")


class TestAppInitialization:
    """Tests that Meilisearch provider is initialized in create_app."""

    def test_meili_provider_initialized_when_flag_enabled(self) -> None:
        import sqlalchemy as sa

        from services.api.main import create_app
        from shared.config import Settings

        engine = sa.create_engine("sqlite:///:memory:")
        settings = Settings(app_env="test", auth_provider="local", jwt_secret="x" * 32)
        settings.feature_meilisearch_search = True
        settings.meilisearch_url = "http://meilisearch:7700"
        settings.meilisearch_master_key = "test-key"

        app = create_app(engine, settings=settings)
        assert app.state.meili_provider is not None

    def test_meili_provider_none_when_flag_disabled(self) -> None:
        import sqlalchemy as sa

        from services.api.main import create_app
        from shared.config import Settings

        engine = sa.create_engine("sqlite:///:memory:")
        settings = Settings(app_env="test", auth_provider="local", jwt_secret="x" * 32)
        settings.feature_meilisearch_search = False

        app = create_app(engine, settings=settings)
        assert app.state.meili_provider is None
