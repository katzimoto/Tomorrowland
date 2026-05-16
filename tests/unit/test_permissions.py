from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy import Engine

from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.permissions.enforcer import (
    assert_doc_access,
    assert_source_access,
    get_allowed_groups,
    require_admin,
)
from shared.db import db_uuid


def test_admin_guard_allows_admin_and_rejects_regular_user(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repository = AuthRepository(connection)
        admin = repository.create_local_user(
            email="admin@example.com",
            password_hash=hash_password("secret"),
            is_admin=True,
        )
        user = repository.create_local_user(
            email="user@example.com",
            password_hash=hash_password("secret"),
            is_admin=False,
        )

    require_admin(admin)
    assert get_allowed_groups(admin) == []
    with pytest.raises(HTTPException) as exc_info:
        require_admin(user)
    assert exc_info.value.status_code == 403


def test_source_and_document_access_follow_source_permissions(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repository = AuthRepository(connection)
        user = repository.create_local_user(
            email="analyst@example.com",
            password_hash=hash_password("secret"),
            group_names=["analysts"],
        )
        source_id = repository.create_ingestion_source("Finance")
        doc_id = repository.create_document(source_id)
        repository.grant_source_to_group(source_id, user.groups[0])

        assert_source_access(source_id, user, repository)
        assert_doc_access(doc_id, user, repository)


def test_document_access_rejects_missing_or_ungranted_documents(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repository = AuthRepository(connection)
        user = repository.create_local_user(
            email="analyst@example.com",
            password_hash=hash_password("secret"),
            group_names=["analysts"],
        )
        source_id = repository.create_ingestion_source("Finance")
        doc_id = repository.create_document(source_id)

        with pytest.raises(HTTPException) as denied:
            assert_doc_access(doc_id, user, repository)
        with pytest.raises(HTTPException) as missing:
            assert_doc_access(uuid4(), user, repository)

    assert denied.value.status_code == 403
    assert missing.value.status_code == 404


# Nested group tests


def _insert_group_membership(connection: object, parent_id: object, child_id: object) -> None:
    connection.execute(  # type: ignore[attr-defined]
        sa.text("INSERT INTO group_memberships (parent_group_id, child_group_id) VALUES (:p, :c)"),
        {"p": db_uuid(parent_id), "c": db_uuid(child_id)},  # type: ignore[arg-type]
    )


def test_user_can_access_source_via_parent_group(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = AuthRepository(connection)
        grandparent_id = repo.ensure_group("grandparent")
        parent_id = repo.ensure_group("parent")
        child_id = repo.ensure_group("child")
        _insert_group_membership(connection, grandparent_id, parent_id)
        _insert_group_membership(connection, parent_id, child_id)

        source_id = repo.create_ingestion_source("nested-source")
        repo.grant_source_to_group(source_id, grandparent_id)

        user_direct = repo.create_local_user(
            "direct@example.com", hash_password("x"), group_names=["parent"]
        )
        user_nested = repo.create_local_user(
            "nested@example.com", hash_password("x"), group_names=["child"]
        )
        user_none = repo.create_local_user("none@example.com", hash_password("x"), group_names=[])

        assert repo.user_can_access_source(user_direct, source_id)
        assert repo.user_can_access_source(user_nested, source_id)
        assert not repo.user_can_access_source(user_none, source_id)


def test_get_effective_group_ids_returns_ancestors(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = AuthRepository(connection)
        gp = repo.ensure_group("gp")
        p = repo.ensure_group("p")
        c = repo.ensure_group("c")
        _insert_group_membership(connection, gp, p)
        _insert_group_membership(connection, p, c)

        effective = set(repo.get_effective_group_ids([c]))
        assert p in effective
        assert gp in effective
        assert c not in effective  # seed not included


def test_get_effective_group_ids_empty_when_no_memberships(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = AuthRepository(connection)
        g = repo.ensure_group("solo")
        assert repo.get_effective_group_ids([g]) == []


def test_cycle_detection_direct_self(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = AuthRepository(connection)
        g = repo.ensure_group("self-ref")
        assert repo._group_would_create_cycle(g, g) is True


def test_cycle_detection_indirect(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = AuthRepository(connection)
        a = repo.ensure_group("a")
        b = repo.ensure_group("b")
        c = repo.ensure_group("c")
        _insert_group_membership(connection, a, b)
        _insert_group_membership(connection, b, c)
        # adding c as parent of a would create a -> b -> c -> a cycle
        assert repo._group_would_create_cycle(c, a) is True


def test_cycle_detection_safe_insertion(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = AuthRepository(connection)
        a = repo.ensure_group("aa")
        b = repo.ensure_group("bb")
        assert repo._group_would_create_cycle(a, b) is False


def test_removing_nested_group_revokes_inherited_access(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = AuthRepository(connection)
        parent_id = repo.ensure_group("p-revoke")
        child_id = repo.ensure_group("c-revoke")
        _insert_group_membership(connection, parent_id, child_id)

        source_id = repo.create_ingestion_source("revoke-source")
        repo.grant_source_to_group(source_id, parent_id)

        user = repo.create_local_user(
            "child-user@example.com", hash_password("x"), group_names=["c-revoke"]
        )
        assert repo.user_can_access_source(user, source_id)

        # Remove the group membership
        connection.execute(
            sa.text(
                "DELETE FROM group_memberships WHERE parent_group_id = :p AND child_group_id = :c"
            ),
            {"p": db_uuid(parent_id), "c": db_uuid(child_id)},
        )
        assert not repo.user_can_access_source(user, source_id)
