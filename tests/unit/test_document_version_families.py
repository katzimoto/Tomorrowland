from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Engine

from services.documents.repository import DocumentRepository


def test_first_version_creates_family_with_version_number_1(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = DocumentRepository(connection)
        source_id = _create_source(connection)
        doc = repo.create(
            source_id=source_id,
            external_id="doc.txt",
            source="folder",
            mime_type="text/plain",
            sha256="a" * 64,
        )

    assert doc is not None
    assert doc.version_number == 1
    assert doc.is_latest is True
    assert doc.version_family_id is not None


def test_changed_content_creates_version_number_2_in_same_family(migrated_engine: Engine) -> None:
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
    assert v1.version_number == 1
    assert v2.version_number == 2
    assert v1.version_family_id == v2.version_family_id


def test_only_newest_version_is_marked_latest(migrated_engine: Engine) -> None:
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
        _v2 = repo.create(
            source_id=source_id,
            external_id="doc.txt",
            source="folder",
            mime_type="text/plain",
            sha256="b" * 64,
        )

        assert v1 is not None
        v1_refreshed = repo.get_by_id(v1.id)

    assert v1_refreshed is not None
    assert v1_refreshed.is_latest is False
    assert _v2 is not None
    assert _v2.is_latest is True


def test_older_version_reports_has_newer_version(migrated_engine: Engine) -> None:
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
        repo.create(
            source_id=source_id,
            external_id="report.pdf",
            source="folder",
            mime_type="application/pdf",
            sha256="b" * 64,
        )

        assert v1 is not None
        v1_refreshed = repo.get_by_id(v1.id)

    assert v1_refreshed is not None
    assert not v1_refreshed.is_latest  # has_newer_version = not is_latest


def test_latest_version_reports_no_newer_version(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = DocumentRepository(connection)
        source_id = _create_source(connection)
        repo.create(
            source_id=source_id,
            external_id="note.txt",
            source="folder",
            mime_type="text/plain",
            sha256="a" * 64,
        )
        v2 = repo.create(
            source_id=source_id,
            external_id="note.txt",
            source="folder",
            mime_type="text/plain",
            sha256="b" * 64,
        )

    assert v2 is not None
    assert v2.is_latest is True  # no newer version


def test_list_versions_in_family_returns_versions_oldest_first(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = DocumentRepository(connection)
        source_id = _create_source(connection)
        v1 = repo.create(
            source_id=source_id,
            external_id="data.csv",
            source="folder",
            mime_type="text/csv",
            sha256="a" * 64,
        )
        v2 = repo.create(
            source_id=source_id,
            external_id="data.csv",
            source="folder",
            mime_type="text/csv",
            sha256="b" * 64,
        )
        v3 = repo.create(
            source_id=source_id,
            external_id="data.csv",
            source="folder",
            mime_type="text/csv",
            sha256="c" * 64,
        )

        assert v1 is not None
        versions = repo.list_versions_in_family(v1.id)

    assert v2 is not None
    assert v3 is not None
    assert len(versions) == 3
    assert versions[0].version_number == 1
    assert versions[1].version_number == 2
    assert versions[2].version_number == 3
    assert versions[0].id == v1.id
    assert versions[2].id == v3.id


def test_get_latest_in_family_returns_newest_version(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = DocumentRepository(connection)
        source_id = _create_source(connection)
        v1 = repo.create(
            source_id=source_id,
            external_id="file.txt",
            source="folder",
            mime_type="text/plain",
            sha256="a" * 64,
        )
        v2 = repo.create(
            source_id=source_id,
            external_id="file.txt",
            source="folder",
            mime_type="text/plain",
            sha256="b" * 64,
        )

        assert v1 is not None
        latest = repo.get_latest_in_family(v1.id)

    assert v2 is not None
    assert latest is not None
    assert latest.id == v2.id
    assert latest.version_number == 2


def test_unchanged_content_dedup_does_not_create_new_version(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = DocumentRepository(connection)
        source_id = _create_source(connection)
        sha = "d" * 64
        v1 = repo.create(
            source_id=source_id,
            external_id="stable.txt",
            source="folder",
            mime_type="text/plain",
            sha256=sha,
        )
        result = repo.create(
            source_id=source_id,
            external_id="stable.txt",
            source="folder",
            mime_type="text/plain",
            sha256=sha,
        )

        assert v1 is not None
        versions = repo.list_versions_in_family(v1.id)

    assert result is None  # dedup: same sha returns None
    assert len(versions) == 1  # only one version in the family


def test_different_external_ids_belong_to_different_families(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = DocumentRepository(connection)
        source_id = _create_source(connection)
        doc_a = repo.create(
            source_id=source_id,
            external_id="a.txt",
            source="folder",
            mime_type="text/plain",
            sha256="a" * 64,
        )
        doc_b = repo.create(
            source_id=source_id,
            external_id="b.txt",
            source="folder",
            mime_type="text/plain",
            sha256="b" * 64,
        )

    assert doc_a is not None
    assert doc_b is not None
    assert doc_a.version_family_id != doc_b.version_family_id
    assert doc_a.version_number == 1
    assert doc_b.version_number == 1


def test_get_family_current_doc_ids_returns_latest(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = DocumentRepository(connection)
        source_id = _create_source(connection)
        v1 = repo.create(
            source_id=source_id,
            external_id="item.txt",
            source="folder",
            mime_type="text/plain",
            sha256="a" * 64,
        )
        v2 = repo.create(
            source_id=source_id,
            external_id="item.txt",
            source="folder",
            mime_type="text/plain",
            sha256="b" * 64,
        )

        assert v1 is not None and v1.version_family_id is not None
        assert v2 is not None
        family_map = repo.get_family_current_doc_ids([v1.version_family_id])

    assert v1.version_family_id in family_map
    assert family_map[v1.version_family_id] == v2.id


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
