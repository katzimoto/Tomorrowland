"""Unit tests for UserDocumentTagRepository."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from services.auth.repository import AuthRepository
from services.documents.models import UserDocumentTagCreate
from services.documents.repository import DocumentRepository, UserDocumentTagRepository
from shared.db import db_uuid


def _create_user(connection: sa.Connection) -> UUID:
    user_id = uuid4()
    connection.execute(
        sa.text("INSERT INTO users (id, email, auth_source) VALUES (:id, :email, 'local')"),
        {"id": db_uuid(user_id), "email": f"{uuid4().hex}@test.com"},
    )
    return user_id


def _create_doc(engine: Engine) -> UUID:
    """Create a minimal accessible document. Return its UUID."""
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


# ---------------------------------------------------------------------------
# list_tags
# ---------------------------------------------------------------------------


def test_list_tags_empty(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)
        repo = UserDocumentTagRepository(conn)
        assert repo.list_tags(doc_id, user_id) == []


def test_list_tags_returns_own_private(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)
        repo = UserDocumentTagRepository(conn)
        repo.create_tag(doc_id, user_id, "mytag", is_private=True)
        tags = repo.list_tags(doc_id, user_id)
    assert len(tags) == 1
    assert tags[0].tag == "mytag"
    assert tags[0].is_private is True


def test_list_tags_private_not_visible_to_other_user(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        owner = _create_user(conn)
        other = _create_user(conn)
        repo = UserDocumentTagRepository(conn)
        repo.create_tag(doc_id, owner, "secret", is_private=True)
        tags = repo.list_tags(doc_id, other)
    assert tags == []


def test_list_tags_public_visible_to_other_user(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        owner = _create_user(conn)
        other = _create_user(conn)
        repo = UserDocumentTagRepository(conn)
        repo.create_tag(doc_id, owner, "shared", is_private=False)
        tags = repo.list_tags(doc_id, other)
    assert len(tags) == 1
    assert tags[0].tag == "shared"
    assert tags[0].is_private is False


# ---------------------------------------------------------------------------
# create_tag
# ---------------------------------------------------------------------------


def test_create_tag_returns_model(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)
        repo = UserDocumentTagRepository(conn)
        tag = repo.create_tag(doc_id, user_id, "contract", is_private=True)
    assert tag.tag == "contract"
    assert tag.is_private is True
    assert tag.user_id == user_id
    assert tag.document_id == doc_id


def test_create_tag_duplicate_raises(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)
        repo = UserDocumentTagRepository(conn)
        repo.create_tag(doc_id, user_id, "dup", is_private=True)
        with pytest.raises(ValueError, match="already exists"):
            repo.create_tag(doc_id, user_id, "dup", is_private=True)


def test_create_tag_limit_enforced(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)
        repo = UserDocumentTagRepository(conn)
        for i in range(UserDocumentTagRepository.MAX_TAGS_PER_USER_PER_DOC):
            repo.create_tag(doc_id, user_id, f"tag{i}", is_private=True)
        with pytest.raises(ValueError, match="Maximum"):
            repo.create_tag(doc_id, user_id, "overflow", is_private=True)


# ---------------------------------------------------------------------------
# delete_tag
# ---------------------------------------------------------------------------


def test_delete_tag_owner_succeeds(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)
        repo = UserDocumentTagRepository(conn)
        tag = repo.create_tag(doc_id, user_id, "to-delete", is_private=True)
        result = repo.delete_tag(tag.id, user_id, is_admin=False)
    assert result is True


def test_delete_tag_not_found_returns_false(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)
        repo = UserDocumentTagRepository(conn)
        result = repo.delete_tag(uuid4(), user_id, is_admin=False)
    assert result is False


def test_delete_tag_other_user_raises_permission_error(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        owner = _create_user(conn)
        attacker = _create_user(conn)
        repo = UserDocumentTagRepository(conn)
        tag = repo.create_tag(doc_id, owner, "owned", is_private=True)
        with pytest.raises(PermissionError):
            repo.delete_tag(tag.id, attacker, is_admin=False)


def test_delete_tag_admin_can_delete_any(migrated_engine: Engine) -> None:
    doc_id = _create_doc(migrated_engine)
    with migrated_engine.begin() as conn:
        owner = _create_user(conn)
        admin_id = _create_user(conn)
        repo = UserDocumentTagRepository(conn)
        tag = repo.create_tag(doc_id, owner, "admin-target", is_private=False)
        result = repo.delete_tag(tag.id, admin_id, is_admin=True)
    assert result is True


# ---------------------------------------------------------------------------
# UserDocumentTagCreate validation
# ---------------------------------------------------------------------------


def test_tag_create_strips_whitespace() -> None:
    model = UserDocumentTagCreate(tag="  hello  ")
    assert model.tag == "hello"


def test_tag_create_empty_raises() -> None:
    with pytest.raises(ValueError):
        UserDocumentTagCreate(tag="   ")


def test_tag_create_too_long_raises() -> None:
    with pytest.raises(ValueError):
        UserDocumentTagCreate(tag="x" * 101)


def test_tag_create_default_visibility_is_private() -> None:
    model = UserDocumentTagCreate(tag="test")
    assert model.visibility == "private"
