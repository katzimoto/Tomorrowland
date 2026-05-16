"""Tests for latest-version-only filtering in search results.

The filtering logic in the search route uses DocumentRepository.list_by_ids
to determine which doc IDs are non-latest, then removes them from merged
results. These tests verify the data layer that the filter relies on.
"""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Engine

from services.documents.repository import DocumentRepository


def test_list_by_ids_returns_is_latest_false_for_older_version(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = DocumentRepository(connection)
        source_id = _create_source(connection)
        v1 = repo.create(
            source_id=source_id,
            external_id="report.pdf",
            source="folder",
            mime_type="application/pdf",
            sha256="a" * 64,
        )
        _v2 = repo.create(
            source_id=source_id,
            external_id="report.pdf",
            source="folder",
            mime_type="application/pdf",
            sha256="b" * 64,
        )

        assert v1 is not None
        rows = repo.list_by_ids([v1.id])

    assert len(rows) == 1
    assert rows[0].id == v1.id
    assert rows[0].is_latest is False


def test_list_by_ids_returns_is_latest_true_for_current_version(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = DocumentRepository(connection)
        source_id = _create_source(connection)
        v1 = repo.create(
            source_id=source_id,
            external_id="report.pdf",
            source="folder",
            mime_type="application/pdf",
            sha256="a" * 64,
        )
        v2 = repo.create(
            source_id=source_id,
            external_id="report.pdf",
            source="folder",
            mime_type="application/pdf",
            sha256="b" * 64,
        )

        assert v1 is not None
        assert v2 is not None
        rows = repo.list_by_ids([v2.id])

    assert len(rows) == 1
    assert rows[0].id == v2.id
    assert rows[0].is_latest is True


def test_filter_non_latest_set_excludes_older_versions(migrated_engine: Engine) -> None:
    """Simulate what the search route does: build non_latest set, filter merged list."""
    with migrated_engine.begin() as connection:
        repo = DocumentRepository(connection)
        source_id = _create_source(connection)
        v1 = repo.create(
            source_id=source_id,
            external_id="doc.txt",
            source="folder",
            mime_type="text/plain",
            sha256="a" * 64,
        )
        v2 = repo.create(
            source_id=source_id,
            external_id="doc.txt",
            source="folder",
            mime_type="text/plain",
            sha256="b" * 64,
        )

        assert v1 is not None
        assert v2 is not None

        # Simulate merged search results containing both versions
        fake_merged_ids = [v1.id, v2.id]
        rows = repo.list_by_ids(fake_merged_ids)
        non_latest = {str(doc.id) for doc in rows if not doc.is_latest}

    # v1 should be excluded, v2 should be kept
    filtered = [doc_id for doc_id in fake_merged_ids if str(doc_id) not in non_latest]
    assert len(filtered) == 1
    assert filtered[0] == v2.id


def test_filter_non_latest_set_includes_all_when_single_version(migrated_engine: Engine) -> None:
    """When there is only one version, it is latest and should not be filtered."""
    with migrated_engine.begin() as connection:
        repo = DocumentRepository(connection)
        source_id = _create_source(connection)
        v1 = repo.create(
            source_id=source_id,
            external_id="only.txt",
            source="folder",
            mime_type="text/plain",
            sha256="a" * 64,
        )

        assert v1 is not None
        rows = repo.list_by_ids([v1.id])
        non_latest = {str(doc.id) for doc in rows if not doc.is_latest}

    filtered = [v1.id] if str(v1.id) not in non_latest else []
    assert len(filtered) == 1


def test_filter_preserves_unknown_doc_ids(migrated_engine: Engine) -> None:
    """Doc IDs not in the DB (e.g. from ES but not yet enriched) are kept."""
    phantom_id = uuid4()

    with migrated_engine.begin() as connection:
        repo = DocumentRepository(connection)
        rows = repo.list_by_ids([phantom_id])
        non_latest = {str(doc.id) for doc in rows if not doc.is_latest}

    # phantom_id is unknown → not in non_latest → kept
    assert str(phantom_id) not in non_latest


def test_include_older_versions_false_excludes_old_with_multiple_docs(
    migrated_engine: Engine,
) -> None:
    """With multiple version families, only latest of each is kept."""
    with migrated_engine.begin() as connection:
        repo = DocumentRepository(connection)
        source_id = _create_source(connection)

        a1 = repo.create(
            source_id=source_id,
            external_id="a.pdf",
            source="folder",
            mime_type="application/pdf",
            sha256="a1" * 32,
        )
        a2 = repo.create(
            source_id=source_id,
            external_id="a.pdf",
            source="folder",
            mime_type="application/pdf",
            sha256="a2" * 32,
        )
        b1 = repo.create(
            source_id=source_id,
            external_id="b.pdf",
            source="folder",
            mime_type="application/pdf",
            sha256="b1" * 32,
        )

        assert a1 is not None and a2 is not None and b1 is not None

        all_ids = [a1.id, a2.id, b1.id]
        rows = repo.list_by_ids(all_ids)
        non_latest = {str(doc.id) for doc in rows if not doc.is_latest}

    filtered = [i for i in all_ids if str(i) not in non_latest]
    assert len(filtered) == 2
    assert a1.id not in filtered  # older version, excluded
    assert a2.id in filtered  # latest of family a
    assert b1.id in filtered  # only version of family b, is latest


# Helpers


def _create_source(connection: sa.Connection) -> object:
    source_id = uuid4()
    connection.execute(
        sa.text(
            """
            INSERT INTO ingestion_sources (id, name, type, source_language)
            VALUES (:id, :name, 'folder', 'en')
            """
        ),
        {"id": source_id.hex, "name": f"test-source-{source_id.hex[:8]}"},
    )
    return source_id
