"""Integration tests for the document comments API."""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.jwt import JwtService
from services.auth.models import UserIdentity
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.documents.repository import DocumentRepository

TEST_JWT_SECRET = "x" * 32


def _admin_token(client: TestClient) -> str:
    login = client.post("/auth/login", json={"email": "admin@example.com", "password": "secret"})
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


def _create_doc(
    engine: Engine,
    group_name: str,
    doc_title: str = "Comment Test Doc",
) -> UUID:
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group(group_name)
        source_id = auth_repo.create_ingestion_source("Comment Source")
        auth_repo.grant_source_to_group(source_id, group_id)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.create(
            source_id=source_id,
            external_id="file:/data/test.txt",
            source="folder",
            mime_type="text/plain",
            title=doc_title,
            path="/data/test.txt",
        )
        assert doc is not None
        return doc.id


def test_list_comments_empty(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    resp = client.get(
        f"/documents/{doc_id}/comments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["doc_id"] == str(doc_id)
    assert data["comments"] == []
    assert data["total"] == 0


def test_create_comment(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{doc_id}/comments",
        json={"body": "First comment"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["body"] == "First comment"
    assert data["doc_id"] == str(doc_id)

    # Verify list shows it
    resp = client.get(
        f"/documents/{doc_id}/comments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["comments"][0]["body"] == "First comment"


def test_update_comment(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{doc_id}/comments",
        json={"body": "Original"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    comment_id = resp.json()["id"]

    resp = client.patch(
        f"/documents/{doc_id}/comments/{comment_id}",
        json={"body": "Updated body"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["body"] == "Updated body"
    assert data["edited_at"] is not None


def test_delete_comment(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{doc_id}/comments",
        json={"body": "To delete"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    comment_id = resp.json()["id"]

    resp = client.delete(
        f"/documents/{doc_id}/comments/{comment_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    # Verify list is empty
    resp = client.get(
        f"/documents/{doc_id}/comments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_cannot_edit_others_comment(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    admin_token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{doc_id}/comments",
        json={"body": "Admin comment"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    comment_id = resp.json()["id"]

    # Create another user in admins group
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group("admins")
        auth_repo.create_local_user(
            email="user2@example.com",
            password_hash=hash_password("secret"),
            display_name="User Two",
            is_admin=False,
            group_names=["admins"],
        )
        row = (
            connection.execute(
                sa.text("SELECT id FROM users WHERE email = :email"),
                {"email": "user2@example.com"},
            )
            .mappings()
            .first()
        )
    assert row is not None
    user2_id = UUID(str(row["id"]))

    # Generate token for user2
    jwt = JwtService(secret=app.state.settings.jwt_secret)
    user2_identity = UserIdentity(
        id=user2_id,
        email="user2@example.com",
        display_name="User Two",
        auth_source="local",
        is_admin=False,
        groups=[group_id],
    )
    user2_token = jwt.encode(user2_identity)

    resp = client.patch(
        f"/documents/{doc_id}/comments/{comment_id}",
        json={"body": "Edited by user2"},
        headers={"Authorization": f"Bearer {user2_token}"},
    )
    assert resp.status_code == 403


def test_pagination(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    # Create 3 comments
    for i in range(3):
        resp = client.post(
            f"/documents/{doc_id}/comments",
            json={"body": f"Comment {i}"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

    # Pagination
    resp = client.get(
        f"/documents/{doc_id}/comments?limit=1&skip=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["comments"]) == 1
    assert data["total"] == 3


def test_sort_oldest(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    for i in range(3):
        resp = client.post(
            f"/documents/{doc_id}/comments",
            json={"body": f"Comment {i}"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

    resp = client.get(
        f"/documents/{doc_id}/comments?sort=oldest",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["comments"][0]["body"] == "Comment 0"


def test_admin_can_edit_others_comment(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    admin_token = _admin_token(client)

    # Create doc and comment as admin first
    doc_id = _create_doc(migrated_engine, "admins")
    resp = client.post(
        f"/documents/{doc_id}/comments",
        json={"body": "Admin comment"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201

    # Create a regular user in admins group
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group("admins")
        auth_repo.create_local_user(
            email="regular@example.com",
            password_hash=hash_password("secret"),
            display_name="Regular",
            is_admin=False,
            group_names=["admins"],
        )
        row = (
            connection.execute(
                sa.text("SELECT id FROM users WHERE email = :email"),
                {"email": "regular@example.com"},
            )
            .mappings()
            .first()
        )
    assert row is not None
    regular_id = UUID(str(row["id"]))

    jwt = JwtService(secret=app.state.settings.jwt_secret)
    regular_identity = UserIdentity(
        id=regular_id,
        email="regular@example.com",
        display_name="Regular",
        auth_source="local",
        is_admin=False,
        groups=[group_id],
    )
    regular_token = jwt.encode(regular_identity)

    # Regular user creates a comment
    resp = client.post(
        f"/documents/{doc_id}/comments",
        json={"body": "Regular comment"},
        headers={"Authorization": f"Bearer {regular_token}"},
    )
    assert resp.status_code == 201
    regular_comment_id = resp.json()["id"]

    # Admin edits regular user's comment
    resp = client.patch(
        f"/documents/{doc_id}/comments/{regular_comment_id}",
        json={"body": "Edited by admin"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["body"] == "Edited by admin"


def test_empty_body_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{doc_id}/comments",
        json={"body": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_edit_deleted_comment_returns_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{doc_id}/comments",
        json={"body": "To delete"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    comment_id = resp.json()["id"]

    # Soft delete
    resp = client.delete(
        f"/documents/{doc_id}/comments/{comment_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    # Try to edit deleted comment
    resp = client.patch(
        f"/documents/{doc_id}/comments/{comment_id}",
        json={"body": "Should fail"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_delete_deleted_comment_returns_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{doc_id}/comments",
        json={"body": "To delete twice"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    comment_id = resp.json()["id"]

    # Soft delete
    resp = client.delete(
        f"/documents/{doc_id}/comments/{comment_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    # Try to delete again
    resp = client.delete(
        f"/documents/{doc_id}/comments/{comment_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_cannot_comment_on_inaccessible_doc(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)

    # Create a doc only accessible to "admins" group
    doc_id = _create_doc(migrated_engine, "admins")

    # Log in as regular user in "users" group
    login = client.post("/auth/login", json={"email": "user@example.com", "password": "secret"})
    assert login.status_code == 200
    user_token = str(login.json()["access_token"])

    resp = client.post(
        f"/documents/{doc_id}/comments",
        json={"body": "Should fail"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# can_edit / can_delete field tests
# ---------------------------------------------------------------------------


def _setup_non_owner(engine: Engine) -> tuple[UUID, str]:
    """Create a non-admin user in the admins group and return (user_id, jwt_token)."""
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group("admins")
        auth_repo.create_local_user(
            email="other@example.com",
            password_hash=hash_password("secret"),
            display_name="Other User",
            is_admin=False,
            group_names=["admins"],
        )
        row = (
            connection.execute(
                sa.text("SELECT id FROM users WHERE email = :email"),
                {"email": "other@example.com"},
            )
            .mappings()
            .first()
        )
    assert row is not None
    other_id = UUID(str(row["id"]))

    app = create_app(engine)
    jwt = JwtService(secret=app.state.settings.jwt_secret)
    identity = UserIdentity(
        id=other_id,
        email="other@example.com",
        display_name="Other User",
        auth_source="local",
        is_admin=False,
        groups=[group_id],
    )
    return other_id, jwt.encode(identity)


def test_create_comment_returns_can_edit_can_delete_for_owner(migrated_engine: Engine) -> None:
    """Comment creator receives can_edit=true and can_delete=true."""
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    resp = client.post(
        f"/documents/{doc_id}/comments",
        json={"body": "My comment"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["can_edit"] is True
    assert data["can_delete"] is True


def test_list_comments_owner_gets_can_edit_can_delete(migrated_engine: Engine) -> None:
    """Owner sees can_edit=true and can_delete=true in the list response."""
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")
    client.post(
        f"/documents/{doc_id}/comments",
        json={"body": "Owner comment"},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.get(
        f"/documents/{doc_id}/comments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    comments = resp.json()["comments"]
    assert len(comments) == 1
    assert comments[0]["can_edit"] is True
    assert comments[0]["can_delete"] is True


def test_list_comments_non_owner_gets_false_flags(migrated_engine: Engine) -> None:
    """Non-owner, non-admin user sees can_edit=false and can_delete=false."""
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    admin_token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")
    client.post(
        f"/documents/{doc_id}/comments",
        json={"body": "Admin comment"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    _, other_token = _setup_non_owner(migrated_engine)

    resp = client.get(
        f"/documents/{doc_id}/comments",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert resp.status_code == 200
    comments = resp.json()["comments"]
    assert len(comments) == 1
    assert comments[0]["can_edit"] is False
    assert comments[0]["can_delete"] is False


def test_update_comment_returns_can_edit_can_delete(migrated_engine: Engine) -> None:
    """PATCH response includes can_edit=true and can_delete=true for the editor."""
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    admin_token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")
    create_resp = client.post(
        f"/documents/{doc_id}/comments",
        json={"body": "Original"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create_resp.status_code == 201
    comment_id = create_resp.json()["id"]

    patch_resp = client.patch(
        f"/documents/{doc_id}/comments/{comment_id}",
        json={"body": "Updated"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["can_edit"] is True
    assert data["can_delete"] is True


def test_admin_gets_can_edit_can_delete_on_others_comment(migrated_engine: Engine) -> None:
    """Admin always gets can_edit=true and can_delete=true regardless of authorship."""
    _setup_users(migrated_engine)
    app = create_app(migrated_engine)
    client = TestClient(app)
    admin_token = _admin_token(client)

    doc_id = _create_doc(migrated_engine, "admins")

    _, other_token = _setup_non_owner(migrated_engine)

    # Non-owner creates a comment
    create_resp = client.post(
        f"/documents/{doc_id}/comments",
        json={"body": "Non-owner comment"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert create_resp.status_code == 201

    # Admin lists and should see can_edit=true, can_delete=true
    resp = client.get(
        f"/documents/{doc_id}/comments",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    comments = resp.json()["comments"]
    assert len(comments) == 1
    assert comments[0]["can_edit"] is True
    assert comments[0]["can_delete"] is True
