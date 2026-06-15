"""Unit tests for TranslationVersionRepository."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Engine

from services.auth.repository import AuthRepository
from services.documents.repository import DocumentRepository, TranslationVersionRepository
from services.pipeline.jobs import PipelineJobRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_doc(
    connection: sa.Connection,
    title: str = "Translatable Doc",
    source_language: str = "de",
) -> UUID:
    auth = AuthRepository(connection)
    source_id = auth.create_ingestion_source(f"source-{uuid4().hex[:8]}")
    doc = DocumentRepository(connection).create(
        source_id=source_id,
        external_id=f"doc-{uuid4().hex[:8]}",
        source="folder",
        mime_type="text/plain",
        title=title,
        source_language=source_language,
    )
    assert doc is not None
    return doc.id


# ---------------------------------------------------------------------------
# create_version
# ---------------------------------------------------------------------------


def test_create_version_without_text_is_pending(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        version = repo.create_version(
            doc_id, label="High quality", quality="high", request_type="manual"
        )

    assert version["status"] == "pending"
    assert version["version_number"] == 1
    assert version["target_language"] == "en"


def test_create_version_with_text_is_available(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        version = repo.create_version(
            doc_id,
            label="Pipeline",
            quality="fast",
            request_type="ingestion",
            translated_text="Hello world",
        )

    assert version["status"] == "available"


def test_create_version_increments_version_number(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        # Distinct request types: only one pending version is allowed per
        # (document_id, request_type) — see idx_dtv_one_active_per_type.
        first = repo.create_version(doc_id, label="v1", quality="fast", request_type="manual")
        second = repo.create_version(doc_id, label="v2", quality="high", request_type="auto_enrich")

    assert first["version_number"] == 1
    assert second["version_number"] == 2


def test_create_version_copies_source_language_from_document(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn, source_language="fr")
        repo = TranslationVersionRepository(conn)
        version = repo.create_version(doc_id, label="v1", quality="fast", request_type="manual")

    assert version["source_language"] == "fr"


# ---------------------------------------------------------------------------
# list_versions
# ---------------------------------------------------------------------------


def test_list_versions_newest_first(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        repo.create_version(doc_id, label="v1", quality="fast", request_type="manual")
        repo.create_version(doc_id, label="v2", quality="high", request_type="auto_enrich")
        versions = repo.list_versions(doc_id)

    assert [v["version_number"] for v in versions] == [2, 1]


def test_list_versions_excludes_noop_available_translation(migrated_engine: Engine) -> None:
    """Available versions identical to the stored content text are hidden."""
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        PipelineJobRepository(conn).update_content_text(doc_id, "Same text")
        repo = TranslationVersionRepository(conn)
        repo.create_version(
            doc_id,
            label="No-op",
            quality="fast",
            request_type="ingestion",
            translated_text="Same text",
        )
        repo.create_version(
            doc_id,
            label="Real",
            quality="fast",
            request_type="ingestion",
            translated_text="Texte différent",
        )
        versions = repo.list_versions(doc_id)

    assert [v["label"] for v in versions] == ["Real"]


def test_list_versions_keeps_pending_even_without_payload(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        repo.create_version(doc_id, label="Pending", quality="high", request_type="manual")
        versions = repo.list_versions(doc_id)

    assert len(versions) == 1
    assert versions[0]["status"] == "pending"


def test_list_versions_scoped_to_document(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        doc_a = _create_doc(conn)
        doc_b = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        repo.create_version(doc_a, label="A", quality="fast", request_type="manual")
        repo.create_version(doc_b, label="B", quality="fast", request_type="manual")
        versions = repo.list_versions(doc_a)

    assert [v["label"] for v in versions] == ["A"]


# ---------------------------------------------------------------------------
# get_pending_versions
# ---------------------------------------------------------------------------


def test_get_pending_versions_returns_only_pending(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        pending = repo.create_version(
            doc_id, label="Pending", quality="high", request_type="manual"
        )
        repo.create_version(
            doc_id,
            label="Done",
            quality="fast",
            request_type="ingestion",
            translated_text="Done text",
        )
        result = repo.get_pending_versions(doc_id)

    assert len(result) == 1
    assert result[0]["label"] == "Pending"
    assert str(result[0]["id"]) == str(pending["id"])


def test_get_pending_versions_empty_when_none(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        result = repo.get_pending_versions(doc_id)

    assert result == []


# ---------------------------------------------------------------------------
# find_pending_or_running
# ---------------------------------------------------------------------------


def test_find_pending_or_running_matches_pending(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        repo.create_version(doc_id, label="Pending", quality="high", request_type="manual")
        found = repo.find_pending_or_running(doc_id, "en")

    assert found is not None
    assert found["status"] == "pending"


def test_find_pending_or_running_matches_running(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        version = repo.create_version(doc_id, label="Run", quality="high", request_type="manual")
        repo.update_version_status(UUID(str(version["id"])), "running")
        found = repo.find_pending_or_running(doc_id, "en")

    assert found is not None
    assert found["status"] == "running"


def test_find_pending_or_running_ignores_terminal_states(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        version = repo.create_version(doc_id, label="Done", quality="high", request_type="manual")
        repo.update_version_status(UUID(str(version["id"])), "available", translated_text="x")
        found = repo.find_pending_or_running(doc_id, "en")

    assert found is None


def test_find_pending_or_running_filters_by_language(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        repo.create_version(
            doc_id, label="French", quality="high", request_type="manual", target_language="fr"
        )
        found = repo.find_pending_or_running(doc_id, "en")

    assert found is None


# ---------------------------------------------------------------------------
# update_version_status
# ---------------------------------------------------------------------------


def test_update_version_status_running_sets_started_at(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        version = repo.create_version(doc_id, label="Run", quality="high", request_type="manual")
        repo.update_version_status(UUID(str(version["id"])), "running")
        rows = repo.list_versions(doc_id)

    assert rows[0]["status"] == "running"
    assert rows[0]["started_at"] is not None
    assert rows[0]["completed_at"] is None


def test_update_version_status_available_sets_completed_and_text(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        version = repo.create_version(doc_id, label="Run", quality="high", request_type="manual")
        repo.update_version_status(
            UUID(str(version["id"])), "available", translated_text="Translated!"
        )
        rows = repo.list_versions(doc_id)

    assert rows[0]["status"] == "available"
    assert rows[0]["translated_text"] == "Translated!"
    assert rows[0]["completed_at"] is not None


def test_update_version_status_failed_keeps_existing_text(migrated_engine: Engine) -> None:
    """Passing translated_text=None must not wipe a previously stored text."""
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        version = repo.create_version(
            doc_id,
            label="Partial",
            quality="fast",
            request_type="ingestion",
            translated_text="Partial text",
        )
        repo.update_version_status(UUID(str(version["id"])), "failed", error_summary="LLM timeout")
        rows = repo.list_versions(doc_id)

    assert rows[0]["status"] == "failed"
    assert rows[0]["translated_text"] == "Partial text"
    assert rows[0]["error_summary"] == "LLM timeout"


# ---------------------------------------------------------------------------
# metadata and provider (#727)
# ---------------------------------------------------------------------------


def test_create_version_stores_metadata(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn, source_language="he")
        repo = TranslationVersionRepository(conn)
        meta = {
            "provider": "libretranslate_argos",
            "quality_lane": "fast",
            "purpose": "search",
            "source_language": "he",
            "target_language": "en",
            "input_char_count": 20,
            "output_char_count": 18,
            "validation_status": "ok",
            "fallback_used": False,
        }
        repo.create_version(
            doc_id,
            label="Pipeline",
            quality="fast",
            request_type="ingestion",
            translated_text="Hello world",
            metadata=meta,
            provider="libretranslate_argos",
        )
        rows = repo.list_versions(doc_id)

    assert len(rows) == 1
    stored = rows[0]
    assert _parse_metadata(stored["metadata"]) == meta


def test_create_version_metadata_defaults_to_empty_dict(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        repo.create_version(doc_id, label="v1", quality="fast", request_type="manual")
        rows = repo.list_versions(doc_id)

    assert _parse_metadata(rows[0]["metadata"]) == {}


def test_update_version_status_stores_metadata(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        version = repo.create_version(doc_id, label="v1", quality="fast", request_type="manual")
        meta = {
            "provider": "libretranslate_argos",
            "quality_lane": "fast",
            "purpose": "search",
            "validation_status": "ok",
            "fallback_used": False,
        }
        repo.update_version_status(
            UUID(str(version["id"])),
            "available",
            translated_text="Translated",
            metadata=meta,
            provider="libretranslate_argos",
        )
        rows = repo.list_versions(doc_id)

    assert _parse_metadata(rows[0]["metadata"]) == meta


def test_update_version_status_does_not_require_metadata(migrated_engine: Engine) -> None:
    """Calling update_version_status without metadata or provider is safe."""
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        version = repo.create_version(doc_id, label="v1", quality="fast", request_type="manual")
        repo.update_version_status(
            UUID(str(version["id"])), "running", metadata=None, provider=None
        )
        rows = repo.list_versions(doc_id)

    assert rows[0]["status"] == "running"
    assert rows[0]["started_at"] is not None


def test_update_version_status_metadata_coalesce_keeps_existing(migrated_engine: Engine) -> None:
    """Updating a version with metadata replaces existing metadata."""
    with migrated_engine.begin() as conn:
        doc_id = _create_doc(conn)
        repo = TranslationVersionRepository(conn)
        existing_meta = {"provider": "libretranslate_argos", "quality_lane": "fast"}
        version = repo.create_version(
            doc_id,
            label="v1",
            quality="fast",
            request_type="manual",
            metadata=existing_meta,
        )
        new_meta = {
            "provider": "libretranslate_argos",
            "quality_lane": "high",
            "purpose": "display",
        }
        repo.update_version_status(
            UUID(str(version["id"])),
            "running",
            metadata=new_meta,
            provider="libretranslate_argos",
        )
        rows = repo.list_versions(doc_id)

    assert _parse_metadata(rows[0]["metadata"]) == new_meta


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _parse_metadata(value: object) -> dict:
    """Parse a metadata value that may be a JSON string from SQLite."""
    if isinstance(value, str):
        return json.loads(value)  # type: ignore[no-any-return]
    if isinstance(value, dict):
        return value  # type: ignore[return-value]
    if value is None:
        return {}
    return {}
