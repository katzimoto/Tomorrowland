from __future__ import annotations

from prometheus_client import generate_latest

from shared.metrics import MetricsRegistry, metric_names, mime_family


def _metrics_text(metrics: MetricsRegistry) -> str:
    return generate_latest(metrics.registry).decode("utf-8")


def test_domain_metric_catalog_collectors_are_registered() -> None:
    metrics = MetricsRegistry(version="1", commit="abc", environment="test")

    metrics.auth_login_attempts_total.labels("local", "success").inc(0)
    metrics.authz_denials_total.labels("source", "read").inc(0)
    metrics.admin_actions_total.labels("create", "user").inc(0)
    metrics.ingestion_syncs_total.labels("folder", "success").inc(0)
    metrics.ingestion_documents_total.labels("folder", "success").inc(0)
    metrics.pipeline_documents_total.labels("document", "success").inc(0)
    metrics.pipeline_stage_duration_seconds.labels("extraction").observe(0)
    metrics.pipeline_document_bytes.labels("folder").observe(0)
    metrics.pipeline_chunks_total.labels("success").inc(0)
    metrics.dlq_records_total.labels("reason", "folder").inc(0)
    metrics.search_requests_total.labels("hybrid", "success").inc(0)
    metrics.search_duration_seconds.labels("hybrid").observe(0)
    metrics.search_backend_duration_seconds.labels("qdrant", "search").observe(0)
    metrics.search_results_count.labels("hybrid").observe(0)
    metrics.search_index_documents.labels("qdrant").set(0)
    metrics.translation_requests_total.labels("manual", "success").inc(0)
    metrics.translation_duration_seconds.labels("manual").observe(0)
    metrics.translation_characters_total.labels("manual").inc(0)
    metrics.intelligence_tasks_total.labels("summarize", "success").inc(0)
    metrics.intelligence_task_duration_seconds.labels("summarize").observe(0)
    metrics.ollama_requests_total.labels("generate", "success").inc(0)
    metrics.ollama_duration_seconds.labels("generate").observe(0)
    metrics.rag_requests_total.labels("success").inc(0)
    metrics.rag_duration_seconds.labels("retrieval").observe(0)
    metrics.rag_citations_count.observe(0)
    metrics.preview_requests_total.labels("text", "success").inc(0)
    metrics.download_requests_total.labels("success").inc(0)
    metrics.comments_total.labels("create", "success").inc(0)
    metrics.annotations_total.labels("create", "shared", "success").inc(0)
    metrics.subscriptions_total.labels("create", "success").inc(0)
    metrics.notifications_total.labels("create", "success").inc(0)
    names = set(metric_names(metrics.registry))

    expected = {
        "neverland_auth_login_attempts_total",
        "neverland_authz_denials_total",
        "neverland_admin_actions_total",
        "neverland_ingestion_syncs_total",
        "neverland_ingestion_documents_total",
        "neverland_pipeline_documents_total",
        "neverland_pipeline_stage_duration_seconds_bucket",
        "neverland_pipeline_document_bytes_bucket",
        "neverland_pipeline_chunks_total",
        "neverland_dlq_records_total",
        "neverland_dlq_pending",
        "neverland_search_requests_total",
        "neverland_search_duration_seconds_bucket",
        "neverland_search_backend_duration_seconds_bucket",
        "neverland_search_results_count_bucket",
        "neverland_search_index_documents",
        "neverland_translation_requests_total",
        "neverland_translation_duration_seconds_bucket",
        "neverland_translation_characters_total",
        "neverland_intelligence_tasks_total",
        "neverland_intelligence_task_duration_seconds_bucket",
        "neverland_ollama_requests_total",
        "neverland_ollama_duration_seconds_bucket",
        "neverland_rag_requests_total",
        "neverland_rag_duration_seconds_bucket",
        "neverland_rag_citations_count_bucket",
        "neverland_preview_requests_total",
        "neverland_download_requests_total",
        "neverland_comments_total",
        "neverland_annotations_total",
        "neverland_subscriptions_total",
        "neverland_notifications_total",
    }
    assert expected <= names


def test_domain_metrics_increment_success_paths_with_low_cardinality_labels() -> None:
    metrics = MetricsRegistry(version="1", commit="abc", environment="test")

    metrics.auth_login_attempts_total.labels("local", "success").inc()
    metrics.authz_denials_total.labels("source", "read").inc()
    metrics.admin_actions_total.labels("create", "user").inc()
    metrics.ingestion_syncs_total.labels("folder", "success").inc()
    metrics.ingestion_documents_total.labels("folder", "success").inc()
    metrics.pipeline_documents_total.labels("document", "success").inc()
    metrics.pipeline_stage_duration_seconds.labels("extraction").observe(0.01)
    metrics.pipeline_document_bytes.labels("folder").observe(42)
    metrics.pipeline_chunks_total.labels("success").inc(3)
    metrics.dlq_records_total.labels("extract_failed", "folder").inc()
    metrics.dlq_pending.set(2)
    metrics.search_requests_total.labels("hybrid", "success").inc()
    metrics.search_duration_seconds.labels("hybrid").observe(0.02)
    metrics.search_backend_duration_seconds.labels("qdrant", "search").observe(0.01)
    metrics.search_results_count.labels("hybrid").observe(7)
    metrics.search_index_documents.labels("qdrant").set(11)
    metrics.translation_requests_total.labels("manual", "success").inc()
    metrics.translation_duration_seconds.labels("manual").observe(0.03)
    metrics.translation_characters_total.labels("manual").inc(12)
    metrics.intelligence_tasks_total.labels("summarize", "success").inc()
    metrics.intelligence_task_duration_seconds.labels("summarize").observe(0.04)
    metrics.ollama_requests_total.labels("generate", "success").inc()
    metrics.ollama_duration_seconds.labels("generate").observe(0.05)
    metrics.rag_requests_total.labels("success").inc()
    metrics.rag_duration_seconds.labels("retrieval").observe(0.01)
    metrics.rag_citations_count.observe(2)
    metrics.preview_requests_total.labels("text", "success").inc()
    metrics.download_requests_total.labels("success").inc()
    metrics.comments_total.labels("create", "success").inc()
    metrics.annotations_total.labels("create", "shared", "success").inc()
    metrics.subscriptions_total.labels("create", "success").inc()
    metrics.notifications_total.labels("create", "success").inc()

    text = _metrics_text(metrics)

    assert 'neverland_auth_login_attempts_total{outcome="success",provider="local"} 1.0' in text
    assert (
        'neverland_ingestion_documents_total{connector_type="folder",outcome="success"} 1.0' in text
    )
    assert 'neverland_pipeline_chunks_total{outcome="success"} 3.0' in text
    assert "neverland_dlq_pending 2.0" in text
    assert 'neverland_search_index_documents{backend="qdrant"} 11.0' in text
    assert 'neverland_translation_characters_total{kind="manual"} 12.0' in text
    assert (
        'neverland_annotations_total{action="create",outcome="success",visibility="shared"} 1.0'
        in text
    )


def test_domain_metrics_increment_failure_outcomes() -> None:
    metrics = MetricsRegistry(version="1", commit="abc", environment="test")

    metrics.auth_login_attempts_total.labels("local", "failure").inc()
    metrics.ingestion_syncs_total.labels("folder", "failure").inc()
    metrics.pipeline_documents_total.labels("document", "failure").inc()
    metrics.translation_requests_total.labels("pipeline", "failure").inc()
    metrics.intelligence_tasks_total.labels("summarize", "failure").inc()
    metrics.ollama_requests_total.labels("generate", "failure").inc()
    metrics.rag_requests_total.labels("failure").inc()
    metrics.preview_requests_total.labels("unknown", "failure").inc()
    metrics.download_requests_total.labels("failure").inc()
    metrics.comments_total.labels("delete", "failure").inc()
    metrics.annotations_total.labels("delete", "private", "failure").inc()
    metrics.subscriptions_total.labels("delete", "failure").inc()
    metrics.notifications_total.labels("read", "failure").inc()

    text = _metrics_text(metrics)

    assert 'neverland_auth_login_attempts_total{outcome="failure",provider="local"} 1.0' in text
    assert 'neverland_pipeline_documents_total{outcome="failure",stage="document"} 1.0' in text
    assert (
        'neverland_annotations_total{action="delete",outcome="failure",visibility="private"} 1.0'
        in text
    )


def test_mime_family_coarsens_user_controlled_mime_values() -> None:
    assert mime_family("text/plain") == "text"
    assert (
        mime_family("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        == "application"
    )
    assert mime_family("x-user/specific") == "other"
    assert mime_family(None) == "unknown"
