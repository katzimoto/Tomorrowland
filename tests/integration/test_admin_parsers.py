"""Integration tests for admin parser API endpoints."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from shared.db import db_uuid


@pytest.fixture
def admin_client(migrated_engine: sa.Engine) -> TestClient:
    """Return a TestClient with admin auth and the migrated engine."""
    from services.api.main import create_app
    from shared.config import Settings

    app = create_app(migrated_engine, Settings())
    return TestClient(app)


def _admin_headers() -> dict[str, str]:
    """Return headers with an admin JWT token."""
    from datetime import UTC, datetime, timedelta

    import jwt

    from shared.config import Settings

    settings = Settings()
    now = datetime.now(UTC)
    payload = {
        "sub": "test-admin",
        "group_ids": ["admins"],
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _ensure_admins_group(connection) -> None:
    connection.execute(
        sa.text("INSERT INTO groups (id, name) VALUES (:id, :name) ON CONFLICT DO NOTHING"),
        {
            "id": db_uuid("00000000-0000-0000-0000-000000000001"),
            "name": "admins",
        },
    )


class TestListParsers:
    def test_list_parsers_requires_admin(self, admin_client: TestClient) -> None:
        resp = admin_client.get("/admin/parsers")
        assert resp.status_code == 401

    def test_list_parsers_returns_capabilities(self, admin_client: TestClient) -> None:
        with admin_client.app.state.engine.begin() as conn:
            _ensure_admins_group(conn)

        resp = admin_client.get("/admin/parsers", headers=_admin_headers())
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
        with admin_client.app.state.engine.begin() as conn:
            _ensure_admins_group(conn)

        resp = admin_client.get("/admin/parsers/nonexistent", headers=_admin_headers())
        assert resp.status_code == 404


class TestParserPoliciesCRUD:
    def _create_policy(self, client: TestClient, source_id: str | None = None, **overrides) -> dict:
        body = {
            "mime_pattern": "application/pdf",
            "parser_chain": ["pypdf"],
            "source_id": source_id,
            **overrides,
        }
        resp = client.post("/admin/parser-policies", json=body, headers=_admin_headers())
        assert resp.status_code == 201, resp.text
        return resp.json()

    def test_create_policy_requires_admin(self, admin_client: TestClient) -> None:
        resp = admin_client.post(
            "/admin/parser-policies",
            json={"mime_pattern": "application/pdf", "parser_chain": ["pypdf"]},
        )
        assert resp.status_code == 401

    def test_create_policy_source_not_found(self, admin_client: TestClient) -> None:
        with admin_client.app.state.engine.begin() as conn:
            _ensure_admins_group(conn)

        resp = admin_client.post(
            "/admin/parser-policies",
            json={
                "source_id": "00000000-0000-0000-0000-000000000099",
                "mime_pattern": "application/pdf",
                "parser_chain": ["pypdf"],
            },
            headers=_admin_headers(),
        )
        assert resp.status_code == 404

    def test_create_policy_unknown_parser(self, admin_client: TestClient) -> None:
        with admin_client.app.state.engine.begin() as conn:
            _ensure_admins_group(conn)

        resp = admin_client.post(
            "/admin/parser-policies",
            json={
                "mime_pattern": "application/pdf",
                "parser_chain": ["nonexistent-parser"],
            },
            headers=_admin_headers(),
        )
        assert resp.status_code == 422
        assert "Unknown parsers" in resp.json()["detail"]

    def test_create_and_get_policy(self, admin_client: TestClient) -> None:
        with admin_client.app.state.engine.begin() as conn:
            _ensure_admins_group(conn)

        created = self._create_policy(admin_client)
        assert created["mime_pattern"] == "application/pdf"
        assert created["parser_chain"] == ["pypdf"]
        assert "id" in created

        resp = admin_client.get(f"/admin/parser-policies/{created['id']}", headers=_admin_headers())
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_list_policies(self, admin_client: TestClient) -> None:
        with admin_client.app.state.engine.begin() as conn:
            _ensure_admins_group(conn)

        self._create_policy(admin_client)
        self._create_policy(admin_client, mime_pattern="text/plain", parser_chain=["plain"])

        resp = admin_client.get("/admin/parser-policies", headers=_admin_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2

    def test_update_policy(self, admin_client: TestClient) -> None:
        with admin_client.app.state.engine.begin() as conn:
            _ensure_admins_group(conn)

        created = self._create_policy(admin_client)

        resp = admin_client.patch(
            f"/admin/parser-policies/{created['id']}",
            json={"parser_chain": ["pypdf", "generic"], "priority": 5},
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["parser_chain"] == ["pypdf", "generic"]
        assert updated["priority"] == 5

    def test_delete_policy(self, admin_client: TestClient) -> None:
        with admin_client.app.state.engine.begin() as conn:
            _ensure_admins_group(conn)

        created = self._create_policy(admin_client)

        resp = admin_client.delete(
            f"/admin/parser-policies/{created['id']}", headers=_admin_headers()
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        resp = admin_client.get(f"/admin/parser-policies/{created['id']}", headers=_admin_headers())
        assert resp.status_code == 404
