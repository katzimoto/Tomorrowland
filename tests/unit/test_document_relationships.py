"""Unit tests for DocumentRelationshipRepository."""

from __future__ import annotations

from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Engine

from services.auth.repository import AuthRepository
from services.documents.repository import (
    DocumentRelationshipRepository,
    DocumentRepository,
)
from shared.db import db_uuid


def _create_user(connection: sa.Connection) -> UUID:
    user_id = uuid4()
    connection.execute(
        sa.text("INSERT INTO users (id, email, auth_source) VALUES (:id, :email, 'local')"),
        {"id": db_uuid(user_id), "email": f"{uuid4().hex}@test.com"},
    )
    return user_id


def _create_doc(engine: Engine, title: str = "Test Doc") -> UUID:
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group(f"grp-{uuid4().hex[:6]}")
        source_id = auth_repo.create_ingestion_source(f"src-{uuid4().hex[:6]}")
        auth_repo.grant_source_to_group(source_id, group_id)
        doc_repo = DocumentRepository(connection)
        doc = doc_repo.create(
            source_id=source_id,
            external_id=f"file-{uuid4().hex}",
            source="folder",
            mime_type="text/plain",
            title=title,
        )
        assert doc is not None
        return doc.id


# ---------------------------------------------------------------------------
# create_relationship
# ---------------------------------------------------------------------------


def test_create_relationship(migrated_engine: Engine) -> None:
    parent_id = _create_doc(migrated_engine, "Parent Doc")
    child_id = _create_doc(migrated_engine, "Child Doc")
    with migrated_engine.begin() as conn:
        repo = DocumentRelationshipRepository(conn)
        repo.create_relationship(parent_id, child_id, "archive_child", "folder/report.pdf")
    # Should not raise


def test_create_relationship_idempotent(migrated_engine: Engine) -> None:
    parent_id = _create_doc(migrated_engine)
    child_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        repo = DocumentRelationshipRepository(conn)
        repo.create_relationship(parent_id, child_id, "archive_child")
        repo.create_relationship(parent_id, child_id, "archive_child")


# ---------------------------------------------------------------------------
# get_relationships
# ---------------------------------------------------------------------------


def test_get_relationships_empty(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        repo = DocumentRelationshipRepository(conn)
        rels = repo.get_relationships(doc_id)
    assert rels == []


def test_get_relationships_child_direction(migrated_engine: Engine) -> None:
    parent_id = _create_doc(migrated_engine, "Zip File")
    child_id = _create_doc(migrated_engine, "Nested CSV")
    with migrated_engine.begin() as conn:
        repo = DocumentRelationshipRepository(conn)
        repo.create_relationship(parent_id, child_id, "archive_child", "data.csv")
        # Looking from the parent's perspective → child
        rels = repo.get_relationships(parent_id)
    assert len(rels) == 1
    assert rels[0]["direction"] == "child"
    assert rels[0]["relationship_type"] == "archive_child"
    assert rels[0]["other_document_id"] == str(child_id)
    assert rels[0]["title"] == "Nested CSV"


def test_get_relationships_parent_direction(migrated_engine: Engine) -> None:
    parent_id = _create_doc(migrated_engine, "Eml File")
    child_id = _create_doc(migrated_engine, "Attachment")
    with migrated_engine.begin() as conn:
        repo = DocumentRelationshipRepository(conn)
        repo.create_relationship(parent_id, child_id, "email_attachment", "image.png")
        # Looking from the child's perspective → parent
        rels = repo.get_relationships(child_id)
    assert len(rels) == 1
    assert rels[0]["direction"] == "parent"
    assert rels[0]["other_document_id"] == str(parent_id)
    assert rels[0]["title"] == "Eml File"


def test_get_relationships_both_directions(migrated_engine: Engine) -> None:
    parent_id = _create_doc(migrated_engine, "Outer")
    child_id = _create_doc(migrated_engine, "Inner")
    another_parent = _create_doc(migrated_engine, "Another Parent")
    with migrated_engine.begin() as conn:
        repo = DocumentRelationshipRepository(conn)
        repo.create_relationship(parent_id, child_id, "archive_child")
        repo.create_relationship(another_parent, child_id, "archive_child")
        # The "Inner" doc should see both parents
        rels = repo.get_relationships(child_id)
    assert len(rels) == 2
    assert all(r["direction"] == "parent" for r in rels)
