from __future__ import annotations

from uuid import uuid4

import pytest
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
