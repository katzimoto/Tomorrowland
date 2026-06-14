"""Security and audit integration tests for the evidence pack API (#676 / #679).

These tests prove the permission-first guarantees:
- packs are owner-scoped (cross-user access is blocked),
- items can only be added for documents the caller can access,
- revoked/inaccessible document text is hidden on read and export,
- every mutation writes an audit_log row,
- error responses never echo stored excerpt text.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

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
LEAK_CANARY = "TOP-SECRET-EXCERPT-DO-NOT-LEAK"


def _settings(**overrides: object) -> Settings:
    return Settings(
        app_env="test",
        auth_provider="local",
        jwt_secret=TEST_JWT_SECRET,
        feature_meilisearch_search=False,
        feature_meilisearch_shadow_index=False,
        **overrides,
    )


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
        auth_repo.create_local_user(
            email="other@example.com",
            password_hash=hash_password("secret"),
            display_name="Other",
            is_admin=False,
            group_names=["others"],
        )
        auth_repo.ensure_group("users")
        auth_repo.ensure_group("admins")
        auth_repo.ensure_group("others")


def _token(client: TestClient, email: str) -> str:
    login = client.post("/auth/login", json={"email": email, "password": "secret"})
    assert login.status_code == 200, login.text
    return str(login.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_source_with_doc(engine: Engine, group_name: str) -> tuple[str, str]:
    """Create a source granted to *group_name* with one document. Returns (source_id, doc_id)."""
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group(group_name)
        source_id = auth_repo.create_ingestion_source("Test Source")
        auth_repo.grant_source_to_group(source_id, group_id)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.create(
            source_id=source_id,
            external_id=f"file:/data/{uuid4().hex}.txt",
            source="folder",
            mime_type="text/plain",
            title="Test Doc",
            path="/data/test.txt",
        )
        assert doc is not None
        return str(source_id), str(doc.id)


def _revoke_group_from_source(engine: Engine, source_id: str, group_name: str) -> None:
    """Remove a source→group grant, simulating access revocation."""
    with engine.begin() as connection:
        group_id = AuthRepository(connection).ensure_group(group_name)
        connection.execute(
            sa.text("DELETE FROM source_permissions WHERE source_id = :sid AND group_id = :gid"),
            {"sid": db_uuid(source_id), "gid": db_uuid(group_id)},
        )


def _audit_rows(engine: Engine, action: str | None = None) -> list[dict[str, Any]]:
    with engine.begin() as connection:
        sql = "SELECT user_id, action, resource_type, resource_id, details FROM audit_log"
        params: dict[str, Any] = {}
        if action is not None:
            sql += " WHERE action = :action"
            params["action"] = action
        rows = connection.execute(sa.text(sql), params).mappings().all()
    result: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        details = record.get("details")
        record["details"] = json.loads(details) if isinstance(details, str) else (details or {})
        result.append(record)
    return result


def _make_client(engine: Engine) -> TestClient:
    _setup_users(engine)
    return TestClient(create_app(engine, _settings()))


def _create_pack(client: TestClient, token: str, **body: Any) -> dict[str, Any]:
    payload = {"title": "My Pack", **body}
    resp = client.post("/evidence-packs", json=payload, headers=_auth(token))
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


# ---------------------------------------------------------------------------
# Create / validation
# ---------------------------------------------------------------------------


def test_create_pack_returns_owner_scoped_pack(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")

    pack = _create_pack(
        client,
        token,
        title="Investigation",
        description="notes",
        created_from="search",
        metadata={"k": "v"},
    )
    assert pack["title"] == "Investigation"
    assert pack["created_from"] == "search"
    assert pack["metadata"] == {"k": "v"}
    assert pack["owner_user_id"]  # owner recorded


def test_create_pack_unauthenticated_401(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    resp = client.post("/evidence-packs", json={"title": "x"})
    assert resp.status_code == 401


def test_create_pack_invalid_created_from_422(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    resp = client.post(
        "/evidence-packs",
        json={"title": "x", "created_from": "bogus"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_create_pack_missing_title_422(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    token = _token(client, "user@example.com")
    resp = client.post("/evidence-packs", json={"description": "x"}, headers=_auth(token))
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Cross-user isolation
# ---------------------------------------------------------------------------


def test_list_packs_only_returns_own(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    other = _token(client, "other@example.com")

    _create_pack(client, user, title="U1")
    _create_pack(client, user, title="U2")
    _create_pack(client, other, title="O1")

    user_list = client.get("/evidence-packs", headers=_auth(user)).json()["items"]
    other_list = client.get("/evidence-packs", headers=_auth(other)).json()["items"]
    assert {p["title"] for p in user_list} == {"U1", "U2"}
    assert {p["title"] for p in other_list} == {"O1"}


def test_get_pack_cross_user_returns_404(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    other = _token(client, "other@example.com")
    pack = _create_pack(client, user, title="private")

    resp = client.get(f"/evidence-packs/{pack['id']}", headers=_auth(other))
    assert resp.status_code == 404


def test_admin_non_owner_cannot_read_pack(migrated_engine: Engine) -> None:
    # Packs are strictly owner-scoped: even an admin who does not own the pack
    # must not read it.
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    admin = _token(client, "admin@example.com")
    pack = _create_pack(client, user, title="private")

    resp = client.get(f"/evidence-packs/{pack['id']}", headers=_auth(admin))
    assert resp.status_code == 404


def test_update_pack_cross_user_404(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    other = _token(client, "other@example.com")
    pack = _create_pack(client, user, title="private")

    resp = client.patch(
        f"/evidence-packs/{pack['id']}",
        json={"title": "hacked"},
        headers=_auth(other),
    )
    assert resp.status_code == 404


def test_delete_pack_cross_user_404(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    other = _token(client, "other@example.com")
    pack = _create_pack(client, user, title="private")

    resp = client.delete(f"/evidence-packs/{pack['id']}", headers=_auth(other))
    assert resp.status_code == 404
    # Pack still exists for the owner.
    assert client.get(f"/evidence-packs/{pack['id']}", headers=_auth(user)).status_code == 200


# ---------------------------------------------------------------------------
# Update / delete happy paths
# ---------------------------------------------------------------------------


def test_update_pack_changes_fields(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    pack = _create_pack(client, user, title="old")

    resp = client.patch(
        f"/evidence-packs/{pack['id']}",
        json={"title": "new", "description": "desc"},
        headers=_auth(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "new"
    assert body["description"] == "desc"


def test_delete_pack_removes_it(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    pack = _create_pack(client, user, title="temp")

    assert client.delete(f"/evidence-packs/{pack['id']}", headers=_auth(user)).status_code == 204
    assert client.get(f"/evidence-packs/{pack['id']}", headers=_auth(user)).status_code == 404


# ---------------------------------------------------------------------------
# Items — permission enforcement
# ---------------------------------------------------------------------------


def test_add_item_with_access_succeeds(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    _, doc_id = _create_source_with_doc(migrated_engine, "users")
    pack = _create_pack(client, user, title="p")

    resp = client.post(
        f"/evidence-packs/{pack['id']}/items",
        json={"document_id": doc_id, "item_type": "passage", "text_excerpt": "hello"},
        headers=_auth(user),
    )
    assert resp.status_code == 201, resp.text
    item = resp.json()
    assert item["document_id"] == doc_id
    assert item["text_excerpt"] == "hello"


def test_add_item_without_access_returns_403_no_leak(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    # Document lives in an admins-only source — the regular user has no access.
    _, doc_id = _create_source_with_doc(migrated_engine, "admins")
    pack = _create_pack(client, user, title="p")

    resp = client.post(
        f"/evidence-packs/{pack['id']}/items",
        json={"document_id": doc_id, "item_type": "passage", "text_excerpt": LEAK_CANARY},
        headers=_auth(user),
    )
    assert resp.status_code == 403
    # The rejected excerpt must not be echoed back in the error response.
    assert LEAK_CANARY not in resp.text


def test_add_item_unknown_document_returns_404(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    pack = _create_pack(client, user, title="p")

    resp = client.post(
        f"/evidence-packs/{pack['id']}/items",
        json={"document_id": str(uuid4()), "item_type": "note", "text_excerpt": "x"},
        headers=_auth(user),
    )
    assert resp.status_code == 404


def test_add_item_to_cross_user_pack_returns_404(migrated_engine: Engine) -> None:
    # Even with document access, a non-owner cannot add to someone else's pack.
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    other = _token(client, "other@example.com")
    pack = _create_pack(client, user, title="p")
    # Doc the *other* user can access.
    _, doc_id = _create_source_with_doc(migrated_engine, "others")

    resp = client.post(
        f"/evidence-packs/{pack['id']}/items",
        json={"document_id": doc_id, "item_type": "passage", "text_excerpt": "x"},
        headers=_auth(other),
    )
    assert resp.status_code == 404


def test_add_item_invalid_type_422(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    _, doc_id = _create_source_with_doc(migrated_engine, "users")
    pack = _create_pack(client, user, title="p")

    resp = client.post(
        f"/evidence-packs/{pack['id']}/items",
        json={"document_id": doc_id, "item_type": "invalid", "text_excerpt": "x"},
        headers=_auth(user),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Items — from citation payload
# ---------------------------------------------------------------------------


def test_add_item_from_citation_succeeds(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    _, doc_id = _create_source_with_doc(migrated_engine, "users")
    pack = _create_pack(client, user, title="p")

    resp = client.post(
        f"/evidence-packs/{pack['id']}/items/from-citation",
        json={
            "document_id": doc_id,
            "chunk_text": "cited passage",
            "citation_id": "cit-1",
            "chunk_id": "chunk-1",
            "page_number": 3,
            "section_heading": "Intro",
        },
        headers=_auth(user),
    )
    assert resp.status_code == 201, resp.text
    item = resp.json()
    assert item["item_type"] == "citation"
    assert item["text_excerpt"] == "cited passage"
    assert item["citation_id"] == "cit-1"
    assert item["chunk_id"] == "chunk-1"
    assert item["page_number"] == 3


def test_add_item_from_citation_without_access_403(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    _, doc_id = _create_source_with_doc(migrated_engine, "admins")
    pack = _create_pack(client, user, title="p")

    resp = client.post(
        f"/evidence-packs/{pack['id']}/items/from-citation",
        json={"document_id": doc_id, "chunk_text": LEAK_CANARY},
        headers=_auth(user),
    )
    assert resp.status_code == 403
    assert LEAK_CANARY not in resp.text


# ---------------------------------------------------------------------------
# Revoked / inaccessible documents are hidden on read and export
# ---------------------------------------------------------------------------


def test_revoked_document_item_hidden_on_read(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    source_id, doc_id = _create_source_with_doc(migrated_engine, "users")
    pack = _create_pack(client, user, title="p")

    add = client.post(
        f"/evidence-packs/{pack['id']}/items",
        json={"document_id": doc_id, "item_type": "passage", "text_excerpt": LEAK_CANARY},
        headers=_auth(user),
    )
    assert add.status_code == 201
    # Item is visible while access holds.
    detail = client.get(f"/evidence-packs/{pack['id']}", headers=_auth(user)).json()
    assert len(detail["items"]) == 1

    # Revoke the user's access to the document's source.
    _revoke_group_from_source(migrated_engine, source_id, "users")

    detail_after = client.get(f"/evidence-packs/{pack['id']}", headers=_auth(user)).json()
    assert detail_after["items"] == []
    # Excerpt text must not leak anywhere in the response.
    assert LEAK_CANARY not in json.dumps(detail_after)


def test_export_excludes_inaccessible_items(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    source_a, doc_a = _create_source_with_doc(migrated_engine, "users")
    _source_b, doc_b = _create_source_with_doc(migrated_engine, "users")
    pack = _create_pack(client, user, title="p")

    client.post(
        f"/evidence-packs/{pack['id']}/items",
        json={"document_id": doc_a, "item_type": "passage", "text_excerpt": "KEEP-ME"},
        headers=_auth(user),
    )
    client.post(
        f"/evidence-packs/{pack['id']}/items",
        json={"document_id": doc_b, "item_type": "passage", "text_excerpt": LEAK_CANARY},
        headers=_auth(user),
    )

    # Revoke access to source A's document only.
    _revoke_group_from_source(migrated_engine, source_a, "users")

    json_export = client.get(
        f"/evidence-packs/{pack['id']}/export?format=json", headers=_auth(user)
    )
    assert json_export.status_code == 200
    docs = {i["document_id"] for i in json_export.json()["items"]}
    assert docs == {doc_b}
    assert "KEEP-ME" not in json_export.text

    md_export = client.get(
        f"/evidence-packs/{pack['id']}/export?format=markdown", headers=_auth(user)
    )
    assert md_export.status_code == 200
    assert LEAK_CANARY in md_export.text  # accessible item present
    assert "KEEP-ME" not in md_export.text  # revoked item excluded


# ---------------------------------------------------------------------------
# Item removal
# ---------------------------------------------------------------------------


def test_remove_item_succeeds(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    _, doc_id = _create_source_with_doc(migrated_engine, "users")
    pack = _create_pack(client, user, title="p")
    item = client.post(
        f"/evidence-packs/{pack['id']}/items",
        json={"document_id": doc_id, "item_type": "passage", "text_excerpt": "x"},
        headers=_auth(user),
    ).json()

    resp = client.delete(f"/evidence-packs/{pack['id']}/items/{item['id']}", headers=_auth(user))
    assert resp.status_code == 204
    detail = client.get(f"/evidence-packs/{pack['id']}", headers=_auth(user)).json()
    assert detail["items"] == []


def test_remove_item_cross_user_404(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    other = _token(client, "other@example.com")
    _, doc_id = _create_source_with_doc(migrated_engine, "users")
    pack = _create_pack(client, user, title="p")
    item = client.post(
        f"/evidence-packs/{pack['id']}/items",
        json={"document_id": doc_id, "item_type": "passage", "text_excerpt": "x"},
        headers=_auth(user),
    ).json()

    resp = client.delete(f"/evidence-packs/{pack['id']}/items/{item['id']}", headers=_auth(other))
    assert resp.status_code == 404


def test_remove_unknown_item_404(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    pack = _create_pack(client, user, title="p")

    resp = client.delete(f"/evidence-packs/{pack['id']}/items/{uuid4()}", headers=_auth(user))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


def test_create_update_delete_are_audited(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    pack = _create_pack(client, user, title="p")
    client.patch(f"/evidence-packs/{pack['id']}", json={"title": "p2"}, headers=_auth(user))
    client.delete(f"/evidence-packs/{pack['id']}", headers=_auth(user))

    actions = {
        r["action"] for r in _audit_rows(migrated_engine) if r["resource_type"] == "evidence_pack"
    }
    assert {"create", "update", "delete"} <= actions


def test_item_add_and_remove_are_audited_with_document_id(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")
    _, doc_id = _create_source_with_doc(migrated_engine, "users")
    pack = _create_pack(client, user, title="p")
    item = client.post(
        f"/evidence-packs/{pack['id']}/items",
        json={"document_id": doc_id, "item_type": "passage", "text_excerpt": "x"},
        headers=_auth(user),
    ).json()
    client.delete(f"/evidence-packs/{pack['id']}/items/{item['id']}", headers=_auth(user))

    add_rows = _audit_rows(migrated_engine, action="item_add")
    remove_rows = _audit_rows(migrated_engine, action="item_remove")
    assert len(add_rows) == 1
    assert len(remove_rows) == 1
    assert add_rows[0]["details"]["document_id"] == doc_id
    assert add_rows[0]["details"]["item_id"] == item["id"]
    assert remove_rows[0]["details"]["document_id"] == doc_id


def test_audit_entry_includes_actor_resource_and_correlation_id(migrated_engine: Engine) -> None:
    client = _make_client(migrated_engine)
    user = _token(client, "user@example.com")

    resp = client.post(
        "/evidence-packs",
        json={"title": "p"},
        headers={**_auth(user), "X-Request-ID": "req-correlation-123"},
    )
    pack_id = resp.json()["id"]

    rows = _audit_rows(migrated_engine, action="create")
    assert len(rows) == 1
    row = rows[0]
    assert row["resource_type"] == "evidence_pack"
    assert row["resource_id"] == pack_id  # pack id
    assert row["user_id"] is not None  # actor
    assert row["details"]["request_id"] == "req-correlation-123"  # correlation id
