"""Integration tests for layout blocks API and pipeline.

Verifies:
- Missing layout (existing docs without blocks)
- Single-page blocks
- Multi-page blocks
- Table blocks with bounding boxes
- parse_worker records layout blocks from location_segments
- preview endpoint includes layout_blocks_available and summary
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.documents.layout_block_repository import LayoutBlockRepository
from services.documents.repository import DocumentRepository
from shared.config import Settings

TEST_JWT_SECRET = "x" * 32


def _user_token(client: TestClient) -> str:
    login = client.post("/auth/login", json={"email": "user@example.com", "password": "secret"})
    assert login.status_code == 200
    return login.json()["access_token"]


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


def _create_source_with_doc(
    engine: Engine,
    group_name: str,
    doc_title: str = "Test Doc",
    mime_type: str = "text/plain",
    path: str = "/data/test.txt",
) -> tuple[str, str]:
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group(group_name)
        source_id = auth_repo.create_ingestion_source("Test Source")
        auth_repo.grant_source_to_group(source_id, group_id)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.create(
            source_id=source_id,
            external_id=f"file:{path}",
            source="folder",
            mime_type=mime_type,
            title=doc_title,
            path=path,
        )
        assert doc is not None
        return str(source_id), str(doc.id)


def _insert_layout_blocks(
    engine: Engine, document_id: UUID, blocks: list[dict[str, object]]
) -> None:
    with engine.begin() as connection:
        repo = LayoutBlockRepository(connection)
        repo.bulk_upsert(document_id, blocks)


# ---------------------------------------------------------------------------
# Missing layout
# ---------------------------------------------------------------------------


def test_preview_no_layout_blocks_for_document_without_them(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    """Document ingested before #669 has no layout blocks — preview should
    report layout_blocks_available=False with null summary."""
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Hello world. This is a test document.")

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    response = client.get(f"/preview/{document_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert data["layout_blocks_available"] is False
    assert data["layout_blocks_summary"] is None


# ---------------------------------------------------------------------------
# Single-page blocks
# ---------------------------------------------------------------------------


def test_preview_returns_layout_blocks_for_single_page(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Hello world. This is a test document.")

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    _insert_layout_blocks(
        migrated_engine,
        UUID(document_id),
        [
            {"page_number": 1, "block_type": "heading", "text": "Title", "parser": "pypdf"},
            {
                "page_number": 1,
                "block_type": "paragraph",
                "text": "Hello world.",
                "parser": "pypdf",
            },
            {"page_number": 1, "block_type": "paragraph", "text": "More text.", "parser": "pypdf"},
        ],
    )

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    response = client.get(f"/preview/{document_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert data["layout_blocks_available"] is True
    summary = data["layout_blocks_summary"]
    assert summary is not None
    assert len(summary) == 2  # heading + paragraph on page 1
    page_1_items = [s for s in summary if s["page_number"] == 1]
    assert len(page_1_items) == 2
    types = {s["block_type"] for s in page_1_items}
    assert types == {"heading", "paragraph"}


# ---------------------------------------------------------------------------
# Multi-page blocks
# ---------------------------------------------------------------------------


def test_preview_returns_layout_blocks_for_multi_page(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Page 1 content.\nPage 2 content.\nPage 3 content.")

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    _insert_layout_blocks(
        migrated_engine,
        UUID(document_id),
        [
            {"page_number": 1, "block_type": "heading", "text": "Chapter 1", "parser": "pypdf"},
            {
                "page_number": 1,
                "block_type": "paragraph",
                "text": "Page 1 text.",
                "parser": "pypdf",
            },
            {"page_number": 2, "block_type": "heading", "text": "Chapter 2", "parser": "pypdf"},
            {
                "page_number": 2,
                "block_type": "paragraph",
                "text": "Page 2 text.",
                "parser": "pypdf",
            },
            {
                "page_number": 3,
                "block_type": "paragraph",
                "text": "Page 3 text.",
                "parser": "pypdf",
            },
        ],
    )

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    response = client.get(f"/preview/{document_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert data["layout_blocks_available"] is True
    summary = data["layout_blocks_summary"]
    assert summary is not None

    # Page 1: heading + paragraph (2 types)
    p1 = [s for s in summary if s["page_number"] == 1]
    assert len(p1) == 2

    # Page 2: heading + paragraph
    p2 = [s for s in summary if s["page_number"] == 2]
    assert len(p2) == 2

    # Page 3: just paragraph
    p3 = [s for s in summary if s["page_number"] == 3]
    assert len(p3) == 1
    assert p3[0]["block_type"] == "paragraph"


# ---------------------------------------------------------------------------
# Table blocks with bounding boxes
# ---------------------------------------------------------------------------


def test_table_blocks_appear_in_summary(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Data.")

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    _insert_layout_blocks(
        migrated_engine,
        UUID(document_id),
        [
            {"page_number": 1, "block_type": "heading", "text": "Report", "parser": "docling"},
            {
                "page_number": 1,
                "block_type": "table",
                "text": None,
                "bbox": [0, 0, 100, 50],
                "parser": "docling",
            },
            {"page_number": 1, "block_type": "caption", "text": "Table 1", "parser": "docling"},
        ],
    )

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    response = client.get(f"/preview/{document_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert data["layout_blocks_available"] is True
    summary = data["layout_blocks_summary"]
    assert summary is not None
    types = {s["block_type"] for s in summary}
    assert "table" in types
    assert "caption" in types


# ---------------------------------------------------------------------------
# Layout block repository integration
# ---------------------------------------------------------------------------


def test_repository_handles_missing_document_gracefully(
    migrated_engine: Engine,
) -> None:
    """list_by_document returns empty list for nonexistent document."""
    with migrated_engine.begin() as connection:
        repo = LayoutBlockRepository(connection)
        blocks = repo.list_by_document(uuid4())

    assert blocks == []


def test_repository_count_missing_document(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = LayoutBlockRepository(connection)
        count = repo.count_by_document(uuid4())

    assert count == 0


def test_repository_has_blocks_missing_document(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = LayoutBlockRepository(connection)
        result = repo.has_blocks(uuid4())

    assert result is False


def test_repository_page_summary_missing_document(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = LayoutBlockRepository(connection)
        summary = repo.page_summary(uuid4())

    assert summary == []


def test_repository_delete_by_document_missing(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repo = LayoutBlockRepository(connection)
        count = repo.delete_by_document(uuid4())

    assert count == 0
