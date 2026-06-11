"""Integration tests for admin parser API endpoints."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine


@pytest.fixture
def admin_client(migrated_engine: sa.Engine) -> TestClient:
    """Return a TestClient backed by a migrated engine with an admin user seeded."""
    from services.api.main import create_app
    from shared.config import Settings

    app = create_app(migrated_engine, Settings())
    _setup_admin_user(migrated_engine)
    return TestClient(app)


def _setup_admin_user(engine: Engine) -> None:
    """Insert an admin user so login works in tests."""
    from services.auth.passwords import hash_password
    from services.auth.repository import AuthRepository

    with engine.begin() as conn:
        AuthRepository(conn).create_local_user(
            email="admin@example.com",
            password_hash=hash_password("secret"),
            display_name="Admin",
            is_admin=True,
            group_names=["admins"],
        )


def _admin_token(client: TestClient) -> str:
    """Log in as the seeded admin and return a Bearer auth header value."""
    resp = client.post("/auth/login", json={"email": "admin@example.com", "password": "secret"})
    assert resp.status_code == 200, f"admin login failed: {resp.text}"
    return resp.json()["access_token"]


def _admin_headers(client: TestClient) -> dict[str, str]:
    return {"Authorization": f"Bearer {_admin_token(client)}"}


class TestListParsers:
    def test_list_parsers_requires_admin(self, admin_client: TestClient) -> None:
        resp = admin_client.get("/admin/parsers")
        assert resp.status_code == 401

    def test_list_parsers_returns_capabilities(self, admin_client: TestClient) -> None:
        resp = admin_client.get("/admin/parsers", headers=_admin_headers(admin_client))
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        first = data[0]
        assert "parser_name" in first
        assert "parser_version" in first
        assert "supported_mime_types" in first
        assert "quality_tier" in first
        assert "requires_ocr" in first

    def test_get_parser_not_found(self, admin_client: TestClient) -> None:
        resp = admin_client.get("/admin/parsers/nonexistent", headers=_admin_headers(admin_client))
        assert resp.status_code == 404


class TestParserPoliciesCRUD:
    def _parser_name(self, client: TestClient) -> str:
        """Return the first registered parser name from the live registry."""
        resp = client.get("/admin/parsers", headers=_admin_headers(client))
        assert resp.status_code == 200, resp.text
        return resp.json()[0]["parser_name"]

    def _create_policy(self, client: TestClient, source_id: str | None = None, **overrides) -> dict:
        parser_name = self._parser_name(client)
        body = {
            "mime_pattern": "application/pdf",
            "parser_chain": [parser_name],
            "source_id": source_id,
            **overrides,
        }
        resp = client.post("/admin/parser-policies", json=body, headers=_admin_headers(client))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_create_policy_requires_admin(self, admin_client: TestClient) -> None:
        resp = admin_client.post(
            "/admin/parser-policies",
            json={"mime_pattern": "application/pdf", "parser_chain": ["PdfExtractor"]},
        )
        assert resp.status_code == 401

    def test_create_policy_source_not_found(self, admin_client: TestClient) -> None:
        parser_name = self._parser_name(admin_client)
        resp = admin_client.post(
            "/admin/parser-policies",
            json={
                "source_id": "00000000-0000-0000-0000-000000000099",
                "mime_pattern": "application/pdf",
                "parser_chain": [parser_name],
            },
            headers=_admin_headers(admin_client),
        )
        assert resp.status_code == 404

    def test_create_policy_unknown_parser(self, admin_client: TestClient) -> None:
        resp = admin_client.post(
            "/admin/parser-policies",
            json={
                "mime_pattern": "application/pdf",
                "parser_chain": ["nonexistent-parser"],
            },
            headers=_admin_headers(admin_client),
        )
        assert resp.status_code == 422
        assert "Unknown parsers" in resp.json()["detail"]

    def test_create_and_get_policy(self, admin_client: TestClient) -> None:
        parser_name = self._parser_name(admin_client)
        created = self._create_policy(admin_client)
        assert created["mime_pattern"] == "application/pdf"
        assert created["parser_chain"] == [parser_name]
        assert "id" in created

        resp = admin_client.get(
            f"/admin/parser-policies/{created['id']}", headers=_admin_headers(admin_client)
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_list_policies(self, admin_client: TestClient) -> None:
        parser_name = self._parser_name(admin_client)
        self._create_policy(admin_client)
        body = {
            "mime_pattern": "text/plain",
            "parser_chain": [parser_name],
        }
        resp = admin_client.post(
            "/admin/parser-policies", json=body, headers=_admin_headers(admin_client)
        )
        assert resp.status_code == 201, resp.text

        resp = admin_client.get("/admin/parser-policies", headers=_admin_headers(admin_client))
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2

    def test_update_policy(self, admin_client: TestClient) -> None:
        headers = _admin_headers(admin_client)
        all_parsers = admin_client.get("/admin/parsers", headers=headers).json()
        parser_names = [p["parser_name"] for p in all_parsers]
        assert len(parser_names) >= 2, "need at least 2 parsers for update test"

        created = self._create_policy(admin_client)

        resp = admin_client.patch(
            f"/admin/parser-policies/{created['id']}",
            json={"parser_chain": parser_names[:2], "priority": 5},
            headers=_admin_headers(admin_client),
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["parser_chain"] == parser_names[:2]
        assert updated["priority"] == 5

    def test_delete_policy(self, admin_client: TestClient) -> None:
        created = self._create_policy(admin_client)

        resp = admin_client.delete(
            f"/admin/parser-policies/{created['id']}", headers=_admin_headers(admin_client)
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        resp = admin_client.get(
            f"/admin/parser-policies/{created['id']}", headers=_admin_headers(admin_client)
        )
        assert resp.status_code == 404
