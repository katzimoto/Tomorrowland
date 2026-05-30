from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import Engine

from services.intelligence.ollama_client import OllamaClient
from services.intelligence.repository import IntelligenceRepository
from services.intelligence.worker import IntelligenceWorker


@pytest.fixture
def ollama_client() -> OllamaClient:
    return OllamaClient(base_url="http://ollama:11434", model="mistral")


def test_worker_summarizes_and_stores(
    migrated_engine: Engine,
    ollama_client: OllamaClient,
) -> None:
    document_id = uuid4()
    content = "This is a document about artificial intelligence and finance."

    # Mock Ollama to return a predictable summary
    ollama_client.generate = MagicMock(return_value="A document about AI and finance.")

    with migrated_engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        worker = IntelligenceWorker(
            repository=repo,
            ollama_client=ollama_client,
            )
        worker.process_document(document_id, content)

    with migrated_engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        summary = repo.get_summary(document_id)
        assert summary is not None
        assert summary["summary"] == "A document about AI and finance."



def test_worker_extracts_entities(
    migrated_engine: Engine,
    ollama_client: OllamaClient,
) -> None:
    document_id = uuid4()
    content = "Alice from Acme Corp visited Paris."

    ollama_client.generate = MagicMock(
        return_value=(
            '[{"name": "Alice", "type": "person"},'
            ' {"name": "Acme Corp", "type": "organization"},'
            ' {"name": "Paris", "type": "location"}]'
        )
    )

    with migrated_engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        worker = IntelligenceWorker(
            repository=repo,
            ollama_client=ollama_client,
            )
        worker.process_document(document_id, content)

    with migrated_engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        entities = repo.get_entities(document_id)
        names = {e["name"]: e["type"] for e in entities}
        assert names["Alice"] == "person"
        assert names["Acme Corp"] == "organization"
        assert names["Paris"] == "location"


def test_worker_auto_tags(
    migrated_engine: Engine,
    ollama_client: OllamaClient,
) -> None:
    document_id = uuid4()
    content = "Quarterly earnings report for finance sector."

    ollama_client.generate = MagicMock(return_value='["finance", "earnings", "Q3"]')

    with migrated_engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        worker = IntelligenceWorker(
            repository=repo,
            ollama_client=ollama_client,
            )
        worker.process_document(document_id, content)

    with migrated_engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        tags = repo.get_tags(document_id)
        assert set(tags) == {"finance", "earnings", "Q3"}


def test_worker_skips_disabled_tasks(
    migrated_engine: Engine,
    ollama_client: OllamaClient,
) -> None:
    document_id = uuid4()
    content = "Some content"

    ollama_client.generate = MagicMock(return_value="")

    config = {
        "feature.summarization": False,
        "feature.entity_extraction": False,
        "feature.auto_tagging": False,
        "feature.key_points": False,
    }

    with migrated_engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        worker = IntelligenceWorker(
            repository=repo,
            ollama_client=ollama_client,
                config_source=config,
        )
        worker.process_document(document_id, content)

    ollama_client.generate.assert_not_called()


def test_worker_failure_does_not_block(
    migrated_engine: Engine,
    ollama_client: OllamaClient,
) -> None:
    document_id = uuid4()
    content = "Some content"

    ollama_client.generate = MagicMock(side_effect=RuntimeError("Ollama unavailable"))

    with migrated_engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        worker = IntelligenceWorker(
            repository=repo,
            ollama_client=ollama_client,
            )
        # Should not raise
        worker.process_document(document_id, content)

    with migrated_engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        summary = repo.get_summary(document_id)
        assert summary is not None
        assert summary["status"] == "failed"
        assert summary["error_type"] is not None


def test_worker_task_failures_are_swallowed(
    migrated_engine: Engine,
    ollama_client: OllamaClient,
) -> None:
    """Partial task failure must not raise — all tasks are best-effort."""
    document_id = uuid4()
    content = "Some content"

    # Summary succeeds (degraded — plain text, not JSON), entities fail
    ollama_client.generate = MagicMock(side_effect=["A summary", RuntimeError("Ollama failed")])

    with migrated_engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        worker = IntelligenceWorker(
            repository=repo,
            ollama_client=ollama_client,
            )
        # Must not raise even when entity extraction (and auto-tag) fail
        worker.process_document(document_id, content)

    with migrated_engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        summary = repo.get_summary(document_id)
        assert summary is not None
        # No entities because the extraction task failed silently
        entities = repo.get_entities(document_id)
        assert len(entities) == 0

    # summarize + extract_entities + auto_tag each call generate once;
    # key_points uses rule-based only (no config_source) → 3 total calls
    assert ollama_client.generate.call_count == 3
