"""Unit tests for AnnotationRepository reply methods."""

from __future__ import annotations

from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Engine

from services.annotations.repository import AnnotationRepository
from services.auth.repository import AuthRepository
from services.documents.repository import DocumentRepository
from shared.db import db_uuid, to_uuid


def _create_user(connection: sa.Connection) -> UUID:
    user_id = uuid4()
    connection.execute(
        sa.text("INSERT INTO users (id, email, auth_source) VALUES (:id, :email, 'local')"),
        {"id": db_uuid(user_id), "email": f"{uuid4().hex}@test.com"},
    )
    return user_id


def _create_doc(engine: Engine) -> UUID:
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
            title="Test Doc",
        )
        assert doc is not None
        return doc.id


def _create_annotation(connection: sa.Connection, doc_id: UUID, user_id: UUID) -> UUID:
    repo = AnnotationRepository(connection)
    annotation = repo.create(doc_id, user_id, "Test annotation")
    return to_uuid(annotation["id"])


# ---------------------------------------------------------------------------
# list_replies
# ---------------------------------------------------------------------------


def test_list_replies_empty(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)
        anno_id = _create_annotation(conn, doc_id, user_id)
        repo = AnnotationRepository(conn)
        replies = repo.list_replies(anno_id)
    assert replies == []


def test_list_replies_returns_created(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)
        anno_id = _create_annotation(conn, doc_id, user_id)
        repo = AnnotationRepository(conn)
        repo.create_reply(anno_id, user_id, "reply body")
        replies = repo.list_replies(anno_id)
    assert len(replies) == 1
    assert replies[0]["body"] == "reply body"


def test_list_replies_excludes_deleted(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)
        anno_id = _create_annotation(conn, doc_id, user_id)
        repo = AnnotationRepository(conn)
        reply = repo.create_reply(anno_id, user_id, "living")
        repo.create_reply(anno_id, user_id, "dead")
        # Soft-delete the first reply
        repo.delete_reply(to_uuid(reply["id"]))
        replies = repo.list_replies(anno_id)
    # Create 2, soft-delete 1 → 1 remaining
    assert len(replies) == 1
    assert replies[0]["body"] == "dead"


# ---------------------------------------------------------------------------
# create_reply
# ---------------------------------------------------------------------------


def test_create_reply_persists(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)
        anno_id = _create_annotation(conn, doc_id, user_id)
        repo = AnnotationRepository(conn)
        reply = repo.create_reply(anno_id, user_id, "thoughtful reply")
    assert reply["body"] == "thoughtful reply"
    assert reply["annotation_id"] is not None


# ---------------------------------------------------------------------------
# can_modify_reply
# ---------------------------------------------------------------------------


def test_can_modify_reply_owner(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)
        anno_id = _create_annotation(conn, doc_id, user_id)
        repo = AnnotationRepository(conn)
        reply = repo.create_reply(anno_id, user_id, "mine")
        assert repo.can_modify_reply(to_uuid(reply["id"]), user_id, False)


def test_can_modify_reply_non_owner(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        owner = _create_user(conn)
        other = _create_user(conn)
        anno_id = _create_annotation(conn, doc_id, owner)
        repo = AnnotationRepository(conn)
        reply = repo.create_reply(anno_id, owner, "not yours")
        assert not repo.can_modify_reply(to_uuid(reply["id"]), other, False)


def test_can_modify_reply_admin(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        owner = _create_user(conn)
        admin_id = _create_user(conn)
        anno_id = _create_annotation(conn, doc_id, owner)
        repo = AnnotationRepository(conn)
        reply = repo.create_reply(anno_id, owner, "admin-test")
        assert repo.can_modify_reply(to_uuid(reply["id"]), admin_id, True)


# ---------------------------------------------------------------------------
# reply_count in list_annotations
# ---------------------------------------------------------------------------


def test_list_annotations_includes_reply_count(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)
        anno_id = _create_annotation(conn, doc_id, user_id)
        repo = AnnotationRepository(conn)
        repo.create_reply(anno_id, user_id, "r1")
        repo.create_reply(anno_id, user_id, "r2")
        annotations = repo.list_annotations(doc_id, user_id)
    assert len(annotations) == 1
    assert annotations[0]["reply_count"] == 2
