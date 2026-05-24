"""Integration tests for D2 MEDIUM ACL hardening items.

Covers:
- M1: /me/activity filtered by current doc-access (stale rows hidden after revocation)
- M3: /documents/{id}/versions per-version ACL (cross-source version family)
- M4: /notifications filtered by current doc-access (stale rows hidden after revocation)
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.documents.repository import DocumentRepository
from shared.config import Settings
from shared.db import db_uuid

TEST_JWT_SECRET = "x" * 32


def _settings() -> Settings:
    return Settings(
        app_env="test",
        auth_provider="local",
        jwt_secret=TEST_JWT_SECRET,
    )


def _token(client: TestClient, email: str) -> str:
    login = client.post("/auth/login", json={"email": email, "password": "secret"})
    assert login.status_code == 200
    return str(login.json()["access_token"])


def _setup_users(engine: Engine) -> None:
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        auth_repo.create_local_user(
            email="admin@example.com",
            password_hash=hash_password("secret"),
            display_name="Admin",
            is_admin=True,
            group_names=["admins"],
        )
        auth_repo.create_local_user(
            email="user@example.com",
            password_hash=hash_password("secret"),
            display_name="User",
            is_admin=False,
            group_names=["users"],
        )


def _create_doc_in_group(engine: Engine, group_name: str) -> tuple[UUID, UUID, UUID]:
    """Create a document in *group_name* and return (doc_id, source_id, group_id)."""
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group(group_name)
        source_id = auth_repo.create_ingestion_source(f"Source for {group_name}")
        auth_repo.grant_source_to_group(source_id, group_id)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.create(
            source_id=source_id,
            external_id=f"file:{uuid4()}",
            source="folder",
            mime_type="text/plain",
            title=f"Doc in {group_name}",
        )
        assert doc is not None
        return doc.id, source_id, group_id


# ---------------------------------------------------------------------------
# M1: /me/activity — stale rows hidden after group-access revocation
# ---------------------------------------------------------------------------


def test_me_activity_hides_docs_from_revoked_group(migrated_engine: Engine) -> None:
    """A document viewed while the user had access should not appear in activity
    after the user's group access to that source is revoked."""
    _setup_users(migrated_engine)

    # Create a document in the "users" group.
    doc_id, source_id, group_id = _create_doc_in_group(migrated_engine, "users")

    client = TestClient(create_app(migrated_engine, _settings()))
    user_token = _token(client, "user@example.com")

    # User previews the document → creates a view row.
    preview_resp = client.get(
        f"/preview/{doc_id}",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert preview_resp.status_code == 200

    # Activity should show the document while access is intact.
    activity = client.get("/me/activity", headers={"Authorization": f"Bearer {user_token}"})
    assert activity.status_code == 200
    doc_ids_before = [item["document_id"] for item in activity.json()]
    assert str(doc_id) in doc_ids_before

    # Revoke group access by removing the source permission for "users".
    with migrated_engine.begin() as conn:
        conn.execute(
            sa.text("DELETE FROM source_permissions WHERE source_id = :sid AND group_id = :gid"),
            {"sid": db_uuid(source_id), "gid": db_uuid(group_id)},
        )

    # Activity must now hide the document (access revoked).
    activity_after = client.get("/me/activity", headers={"Authorization": f"Bearer {user_token}"})
    assert activity_after.status_code == 200
    doc_ids_after = [item["document_id"] for item in activity_after.json()]
    assert str(doc_id) not in doc_ids_after, (
        "Revoked document should not appear in activity after group access is removed"
    )


def test_me_activity_admin_sees_all_regardless_of_groups(migrated_engine: Engine) -> None:
    """Admin users bypass the group filter and see all their viewed documents."""
    _setup_users(migrated_engine)

    doc_id, source_id, group_id = _create_doc_in_group(migrated_engine, "users")

    client = TestClient(create_app(migrated_engine, _settings()))
    admin_token = _token(client, "admin@example.com")

    # Admin previews the document.
    preview_resp = client.get(
        f"/preview/{doc_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert preview_resp.status_code == 200

    # Activity shows the document.
    activity = client.get("/me/activity", headers={"Authorization": f"Bearer {admin_token}"})
    assert activity.status_code == 200
    doc_ids = [item["document_id"] for item in activity.json()]
    assert str(doc_id) in doc_ids

    # Revoke source grant from users group — should not affect admin's activity.
    with migrated_engine.begin() as conn:
        conn.execute(
            sa.text("DELETE FROM source_permissions WHERE source_id = :sid AND group_id = :gid"),
            {"sid": db_uuid(source_id), "gid": db_uuid(group_id)},
        )

    activity_after = client.get("/me/activity", headers={"Authorization": f"Bearer {admin_token}"})
    assert activity_after.status_code == 200
    doc_ids_after = [item["document_id"] for item in activity_after.json()]
    assert str(doc_id) in doc_ids_after, "Admin activity must be unaffected by group revocation"


# ---------------------------------------------------------------------------
# M3: /documents/{id}/versions — per-version ACL
# ---------------------------------------------------------------------------


def test_versions_filters_inaccessible_versions(migrated_engine: Engine) -> None:
    """When a version family spans two sources with different group grants,
    only versions accessible to the caller's groups are returned."""
    _setup_users(migrated_engine)

    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)

        # Source A → accessible to "users"
        users_group = auth_repo.ensure_group("users")
        source_a = auth_repo.create_ingestion_source("Source A")
        auth_repo.grant_source_to_group(source_a, users_group)

        # Source B → accessible only to "admins"
        admins_group = auth_repo.ensure_group("admins")
        source_b = auth_repo.create_ingestion_source("Source B")
        auth_repo.grant_source_to_group(source_b, admins_group)

        family_id = uuid4()
        doc_repo = DocumentRepository(connection)

        # v1 on source A → user can see it
        v1 = doc_repo.create(
            source_id=source_a,
            external_id="v1",
            source="folder",
            mime_type="text/plain",
            title="V1",
        )
        assert v1 is not None

        # Assign version family by direct SQL update (simulating a re-assigned version)
        connection.execute(
            sa.text(
                "UPDATE documents SET version_family_id = :fid, version_number = 1 WHERE id = :id"
            ),
            {"fid": db_uuid(family_id), "id": db_uuid(v1.id)},
        )

        # v2 on source B → user cannot see it (different group grant)
        v2 = doc_repo.create(
            source_id=source_b,
            external_id="v2",
            source="folder",
            mime_type="text/plain",
            title="V2",
        )
        assert v2 is not None
        connection.execute(
            sa.text(
                "UPDATE documents SET version_family_id = :fid, version_number = 2,"
                " is_latest = true WHERE id = :id"
            ),
            {"fid": db_uuid(family_id), "id": db_uuid(v2.id)},
        )
        connection.execute(
            sa.text("UPDATE documents SET is_latest = false WHERE id = :id"),
            {"id": db_uuid(v1.id)},
        )

    client = TestClient(create_app(migrated_engine, _settings()))
    user_token = _token(client, "user@example.com")

    # User calls /documents/v1/versions — should only see v1, not v2
    resp = client.get(
        f"/documents/{v1.id}/versions",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 200
    returned_ids = {item["document_id"] for item in resp.json()}
    assert str(v1.id) in returned_ids, "v1 (accessible source) must appear"
    assert str(v2.id) not in returned_ids, "v2 (inaccessible source) must be filtered out"


def test_versions_admin_sees_all_versions(migrated_engine: Engine) -> None:
    """Admin must see all versions in a family, regardless of source grants."""
    _setup_users(migrated_engine)

    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)

        users_group = auth_repo.ensure_group("users")
        admins_group = auth_repo.ensure_group("admins")

        source_a = auth_repo.create_ingestion_source("SrcA admin test")
        auth_repo.grant_source_to_group(source_a, users_group)

        source_b = auth_repo.create_ingestion_source("SrcB admin test")
        auth_repo.grant_source_to_group(source_b, admins_group)

        family_id = uuid4()
        doc_repo = DocumentRepository(connection)

        v1 = doc_repo.create(
            source_id=source_a,
            external_id="admin-v1",
            source="folder",
            mime_type="text/plain",
            title="Admin V1",
        )
        assert v1 is not None
        connection.execute(
            sa.text(
                "UPDATE documents SET version_family_id = :fid, version_number = 1,"
                " is_latest = false WHERE id = :id"
            ),
            {"fid": db_uuid(family_id), "id": db_uuid(v1.id)},
        )

        v2 = doc_repo.create(
            source_id=source_b,
            external_id="admin-v2",
            source="folder",
            mime_type="text/plain",
            title="Admin V2",
        )
        assert v2 is not None
        connection.execute(
            sa.text(
                "UPDATE documents SET version_family_id = :fid, version_number = 2,"
                " is_latest = true WHERE id = :id"
            ),
            {"fid": db_uuid(family_id), "id": db_uuid(v2.id)},
        )

    client = TestClient(create_app(migrated_engine, _settings()))
    admin_token = _token(client, "admin@example.com")

    resp = client.get(
        f"/documents/{v1.id}/versions",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    returned_ids = {item["document_id"] for item in resp.json()}
    assert str(v1.id) in returned_ids, "Admin must see v1"
    assert str(v2.id) in returned_ids, "Admin must see v2"


# ---------------------------------------------------------------------------
# M4: /notifications — stale rows hidden after group-access revocation
# ---------------------------------------------------------------------------


def test_notifications_hides_docs_from_revoked_group(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    """A notification created while the user had access should not appear after
    the user's group access to that source is revoked."""
    _setup_users(migrated_engine)

    doc_path = tmp_path / "alert_doc.txt"
    doc_path.write_text("procurement alert test")

    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        users_group = auth_repo.ensure_group("users")
        source_id = auth_repo.create_ingestion_source("Alert Src")
        auth_repo.grant_source_to_group(source_id, users_group)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.create(
            source_id=source_id,
            external_id="file:alert_doc.txt",
            source="folder",
            mime_type="text/plain",
            title="Alert Doc",
            path=str(doc_path),
        )
        assert doc is not None
        doc_id = doc.id

    client = TestClient(create_app(migrated_engine, _settings()))
    user_token = _token(client, "user@example.com")

    # Create a subscription
    sub = client.post(
        "/subscriptions",
        json={"name": "Test", "query": "procurement", "similarity_threshold": 0.5},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert sub.status_code == 201

    # Directly insert a notification for the user (simulating alert trigger)
    sub_id = UUID(sub.json()["id"])
    with migrated_engine.begin() as conn:
        user_id_row = conn.execute(
            sa.text("SELECT id FROM users WHERE email = 'user@example.com'")
        ).scalar_one()
        conn.execute(
            sa.text("""
                INSERT INTO alert_notifications
                    (id, subscription_id, user_id, document_id, similarity, read, created_at)
                VALUES
                    (:id, :sub_id, :uid, :doc_id, 0.9, false, CURRENT_TIMESTAMP)
                ON CONFLICT (subscription_id, document_id) DO NOTHING
            """),
            {
                "id": db_uuid(uuid4()),
                "sub_id": db_uuid(sub_id),
                "uid": user_id_row,
                "doc_id": db_uuid(doc_id),
            },
        )

    # Notifications should appear while access is intact.
    notifs_before = client.get("/notifications", headers={"Authorization": f"Bearer {user_token}"})
    assert notifs_before.status_code == 200
    notif_doc_ids = [n["document_id"] for n in notifs_before.json()]
    assert str(doc_id) in notif_doc_ids

    # Revoke group access.
    with migrated_engine.begin() as conn:
        conn.execute(
            sa.text("DELETE FROM source_permissions WHERE source_id = :sid AND group_id = :gid"),
            {"sid": db_uuid(source_id), "gid": db_uuid(users_group)},
        )

    # Notifications must now be empty (stale row for revoked doc hidden).
    notifs_after = client.get("/notifications", headers={"Authorization": f"Bearer {user_token}"})
    assert notifs_after.status_code == 200
    notif_doc_ids_after = [n["document_id"] for n in notifs_after.json()]
    assert str(doc_id) not in notif_doc_ids_after, (
        "Notification for a revoked document must not appear after group access is removed"
    )
