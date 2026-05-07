from __future__ import annotations

from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Engine

from services.documents.repository import DocumentRepository


def test_create_document_and_retrieve_by_id(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = DocumentRepository(connection)
        source_id = _create_source(connection)
        doc = repo.create(
            source_id=source_id,
            external_id="file1.txt",
            source="folder",
            path="/data/file1.txt",
            mime_type="text/plain",
            title="File 1",
        )

        fetched = repo.get_by_id(doc.id)

    assert fetched is not None
    assert fetched.id == doc.id
    assert fetched.external_id == "file1.txt"
    assert fetched.status == "pending"


def test_get_by_id_returns_none_for_missing_document(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = DocumentRepository(connection)

        fetched = repo.get_by_id(uuid4())

    assert fetched is None


def test_update_status(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = DocumentRepository(connection)
        source_id = _create_source(connection)
        doc = repo.create(
            source_id=source_id,
            external_id="file2.txt",
            source="folder",
            mime_type="text/plain",
        )
        repo.update_status(doc.id, "indexed")

        fetched = repo.get_by_id(doc.id)

    assert fetched is not None
    assert fetched.status == "indexed"


def test_dedup_prevents_duplicate_ingestion(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = DocumentRepository(connection)
        source_id = _create_source(connection)
        sha256 = "a" * 64

        first = repo.create(
            source_id=source_id,
            external_id="dup.txt",
            source="folder",
            mime_type="text/plain",
            sha256=sha256,
        )
        second = repo.create(
            source_id=source_id,
            external_id="dup.txt",
            source="folder",
            mime_type="text/plain",
            sha256=sha256,
        )

    assert first is not None
    assert second is None


def test_list_by_source(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = DocumentRepository(connection)
        source_id = _create_source(connection)
        repo.create(
            source_id=source_id,
            external_id="a.txt",
            source="folder",
            mime_type="text/plain",
        )
        repo.create(
            source_id=source_id,
            external_id="b.txt",
            source="folder",
            mime_type="text/plain",
        )

        docs = repo.list_by_source(source_id)

    assert len(docs) == 2


# Helpers


def _create_source(connection: sa.Connection) -> UUID:
    source_id = uuid4()
    connection.execute(
        sa.text(
            """
            INSERT INTO ingestion_sources (id, name, type, source_language)
            VALUES (:id, :name, 'folder', 'en')
            """
        ),
        {"id": source_id.hex, "name": "test-source"},
    )
    return source_id
