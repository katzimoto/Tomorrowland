"""Unit tests for PermissionSimulatorService (#717)."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Engine

from services.api.routers.admin.permission_simulator_service import (
    PermissionSimulatorService,
)
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository


def _setup_groups(engine: Engine) -> tuple[AuthRepository, object, object, object]:
    """Create test groups and a repo; return (repo, source_id, doc_id, group_id)."""
    with engine.begin() as connection:
        repo = AuthRepository(connection)
        group_id = repo.ensure_group("test-group")
        source_id = repo.create_ingestion_source("Test Source")
        repo.grant_source_to_group(source_id, group_id)
        doc_id = repo.create_document(source_id)
        return repo, source_id, doc_id, group_id


def _setup_admin(engine: Engine) -> str:
    """Create an admin user and return their user ID string."""
    with engine.begin() as connection:
        repo = AuthRepository(connection)
        admin = repo.create_local_user(
            email="admin@test.com",
            password_hash=hash_password("secret"),
            is_admin=True,
            group_names=["admins"],
        )
        return str(admin.id)


def _setup_regular_user(engine: Engine) -> str:
    """Create a regular user with test-group membership and return their user ID."""
    with engine.begin() as connection:
        repo = AuthRepository(connection)
        user = repo.create_local_user(
            email="user@test.com",
            password_hash=hash_password("secret"),
            is_admin=False,
            group_names=["test-group"],
        )
        return str(user.id)


def _setup_user_no_groups(engine: Engine) -> str:
    """Create a regular user with no groups and return their user ID."""
    with engine.begin() as connection:
        repo = AuthRepository(connection)
        user = repo.create_local_user(
            email="nogroup@test.com",
            password_hash=hash_password("secret"),
            is_admin=False,
            group_names=[],
        )
        return str(user.id)


# ── check_source_access ──────────────────────────────────────────────────


def test_source_access_admin_bypass(migrated_engine: Engine) -> None:
    _setup_groups(migrated_engine)
    admin_id = _setup_admin(migrated_engine)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.check_source_access(
            source_id="00000000-0000-0000-0000-000000000000",
            simulated_user_id=admin_id,
        )

    assert result["verdict"] == "allow"
    assert result["reason_category"] == "admin_bypass"
    assert result["is_admin"] is True
    assert "global bypass" in result["reasoning_path"][0].lower()


def test_source_access_group_membership(migrated_engine: Engine) -> None:
    repo, source_id, _, _ = _setup_groups(migrated_engine)
    user_id = _setup_regular_user(migrated_engine)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.check_source_access(
            source_id=str(source_id),
            simulated_user_id=user_id,
        )

    assert result["verdict"] == "allow"
    assert result["reason_category"] == "group_membership"
    assert result["is_admin"] is False
    assert len(result["matching_groups"]) > 0
    # Effective groups should include at least the test-group
    assert any("test-group" in g for g in result["effective_groups"])


def test_source_access_nested_group_inheritance(migrated_engine: Engine) -> None:
    """User in child group should access source granted to parent group."""
    import sqlalchemy as sa

    from shared.db import db_uuid

    with migrated_engine.begin() as connection:
        repo = AuthRepository(connection)
        parent_id = repo.ensure_group("parent-group")
        child_id = repo.ensure_group("child-group")
        connection.execute(
            sa.text(
                "INSERT INTO group_memberships (parent_group_id, child_group_id) VALUES (:p, :c)"
            ),
            {"p": db_uuid(parent_id), "c": db_uuid(child_id)},
        )

        source_id = repo.create_ingestion_source("Nested Source")
        repo.grant_source_to_group(source_id, parent_id)

        user = repo.create_local_user(
            email="child@test.com",
            password_hash=hash_password("secret"),
            is_admin=False,
            group_names=["child-group"],
        )
        user_id = str(user.id)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.check_source_access(
            source_id=str(source_id),
            simulated_user_id=user_id,
        )

    assert result["verdict"] == "allow"
    assert result["reason_category"] == "group_membership"
    assert any("parent-group" in g for g in result["effective_groups"])


def test_source_access_no_groups(migrated_engine: Engine) -> None:
    repo, source_id, _, _ = _setup_groups(migrated_engine)
    user_id = _setup_user_no_groups(migrated_engine)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.check_source_access(
            source_id=str(source_id),
            simulated_user_id=user_id,
        )

    assert result["verdict"] == "deny"
    assert result["reason_category"] in ("no_group_match", "no_source_permissions")
    assert len(result["matching_groups"]) == 0


def test_source_access_no_source_permissions(migrated_engine: Engine) -> None:
    """Source with no grants should deny non-admin users."""
    with migrated_engine.begin() as connection:
        repo = AuthRepository(connection)
        source_id = repo.create_ingestion_source("Ungranted Source")
        user = repo.create_local_user(
            email="orphan@test.com",
            password_hash=hash_password("secret"),
            group_names=["some-group"],
        )
        user_id = str(user.id)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.check_source_access(
            source_id=str(source_id),
            simulated_user_id=user_id,
        )

    assert result["verdict"] == "deny"
    assert result["reason_category"] == "no_source_permissions"


def test_source_access_invalid_source_id(migrated_engine: Engine) -> None:
    user_id = _setup_regular_user(migrated_engine)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.check_source_access(
            source_id="not-a-uuid",
            simulated_user_id=user_id,
        )

    assert result["verdict"] == "deny"
    assert result["reason_category"] == "invalid_source"


def test_source_access_invalid_user_id(migrated_engine: Engine) -> None:
    _setup_groups(migrated_engine)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.check_source_access(
            source_id="00000000-0000-0000-0000-000000000000",
            simulated_user_id="not-a-uuid",
        )

    assert result["verdict"] == "deny"
    assert result["reason_category"] == "invalid_user"


def test_source_access_by_group_ids(migrated_engine: Engine) -> None:
    """Simulate access using synthetic group IDs instead of a real user."""
    repo, source_id, _, group_id = _setup_groups(migrated_engine)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.check_source_access(
            source_id=str(source_id),
            simulated_group_ids=[str(group_id)],
        )

    assert result["verdict"] == "allow"
    assert result["reason_category"] == "group_membership"


def test_source_access_anonymous_user(migrated_engine: Engine) -> None:
    """No user_id and no group_ids simulates an anonymous user."""
    repo, source_id, _, _ = _setup_groups(migrated_engine)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.check_source_access(source_id=str(source_id))

    assert result["verdict"] == "deny"
    assert result["reason_category"] == "no_group_match"


# ── check_document_access ────────────────────────────────────────────────


def test_document_access_valid_document(migrated_engine: Engine) -> None:
    repo, source_id, doc_id, _ = _setup_groups(migrated_engine)
    user_id = _setup_regular_user(migrated_engine)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.check_document_access(
            document_id=str(doc_id),
            simulated_user_id=user_id,
        )

    assert result["verdict"] == "allow"
    assert result["reason_category"] == "group_membership"
    assert result["document_id"] == str(doc_id)
    assert result["source_id"] == str(source_id)
    # create_document doesn't set a title, so document_title may be None


def test_document_access_not_found(migrated_engine: Engine) -> None:
    user_id = _setup_regular_user(migrated_engine)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.check_document_access(
            document_id=str(uuid4()),
            simulated_user_id=user_id,
        )

    assert result["verdict"] == "deny"
    assert result["reason_category"] == "document_not_found"


def test_document_access_invalid_id(migrated_engine: Engine) -> None:
    user_id = _setup_regular_user(migrated_engine)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.check_document_access(
            document_id="bad-id",
            simulated_user_id=user_id,
        )

    assert result["verdict"] == "deny"
    assert result["reason_category"] == "invalid_document"


# ── simulate_search ──────────────────────────────────────────────────────


def test_simulate_search_admin_user(migrated_engine: Engine) -> None:
    admin_id = _setup_admin(migrated_engine)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.simulate_search(
            "test query",
            simulated_user_id=admin_id,
        )

    assert result["search_filter"] == ""
    assert result["is_admin"] is True
    assert "no acl filter" in result["filter_explanation"][0]["step"].lower()


def test_simulate_search_regular_user(migrated_engine: Engine) -> None:
    _setup_groups(migrated_engine)
    user_id = _setup_regular_user(migrated_engine)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.simulate_search(
            "test query",
            simulated_user_id=user_id,
        )

    assert "allowedGroupIds IN" in result["search_filter"]
    assert result["is_admin"] is False
    assert len(result["effective_group_ids"]) > 0


def test_simulate_search_no_groups(migrated_engine: Engine) -> None:
    user_id = _setup_user_no_groups(migrated_engine)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.simulate_search(
            "test query",
            simulated_user_id=user_id,
        )

    assert result["search_filter"] == "allowedGroupIds IS EMPTY"
    assert len(result["effective_group_ids"]) == 0


def test_simulate_search_invalid_user(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.simulate_search(
            "test query",
            simulated_user_id="bad-id",
        )

    assert result.get("error") == "invalid_user"


def test_simulate_search_by_group_ids(migrated_engine: Engine) -> None:
    repo, _, _, group_id = _setup_groups(migrated_engine)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.simulate_search(
            "test query",
            simulated_group_ids=[str(group_id)],
        )

    assert "allowedGroupIds IN" in result["search_filter"]
    assert len(result["effective_group_ids"]) > 0


# ── audit_full_access ────────────────────────────────────────────────────


def test_audit_with_source_and_document(migrated_engine: Engine) -> None:
    repo, source_id, doc_id, _ = _setup_groups(migrated_engine)
    user_id = _setup_regular_user(migrated_engine)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.audit_full_access(
            simulated_user_id=user_id,
            source_id=str(source_id),
            document_id=str(doc_id),
        )

    assert result["simulated_user"]["email"] == "user@test.com"
    assert len(result["checks"]) == 2
    # Source check
    assert result["checks"][0]["type"] == "source_access"
    assert result["checks"][0]["verdict"] == "allow"
    # Document check
    assert result["checks"][1]["type"] == "document_access"
    assert result["checks"][1]["verdict"] == "allow"


def test_audit_source_only(migrated_engine: Engine) -> None:
    repo, source_id, _, _ = _setup_groups(migrated_engine)
    user_id = _setup_regular_user(migrated_engine)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.audit_full_access(
            simulated_user_id=user_id,
            source_id=str(source_id),
        )

    assert len(result["checks"]) == 1
    assert result["checks"][0]["type"] == "source_access"


def test_audit_document_only(migrated_engine: Engine) -> None:
    repo, _, doc_id, _ = _setup_groups(migrated_engine)
    user_id = _setup_regular_user(migrated_engine)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.audit_full_access(
            simulated_user_id=user_id,
            document_id=str(doc_id),
        )

    assert len(result["checks"]) == 1
    assert result["checks"][0]["type"] == "document_access"


def test_audit_invalid_user(migrated_engine: Engine) -> None:
    repo, source_id, _, _ = _setup_groups(migrated_engine)

    with migrated_engine.begin() as connection:
        service = PermissionSimulatorService(connection)
        result = service.audit_full_access(
            simulated_user_id="bad-id",
            source_id=str(source_id),
        )

    assert result.get("error") == "invalid_user"
