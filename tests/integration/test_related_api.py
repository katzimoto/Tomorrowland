"""Integration tests for related documents and expertise services."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.models import UserIdentity
from services.auth.repository import AuthRepository
from services.documents.models import DocumentRow
from services.documents.repository import DocumentRepository
from services.related.repository import RelatedRepository
from services.related.service import RelatedService
from services.search.encoder import MockEncoder
from services.search.hybrid import SearchResult
from services.search.qdrant import QdrantSearchClient
from shared.config import Settings
from shared.db import db_uuid

UNUSED_PASSWORD_HASH = "not-used-by-this-test"


def _setup_users(engine: Engine) -> None:
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        auth_repo.create_local_user(
            email="admin@example.com",
            password_hash=UNUSED_PASSWORD_HASH,
            display_name="Admin",
            is_admin=True,
            group_names=["admins"],
        )
        auth_repo.create_local_user(
            email="analyst@example.com",
            password_hash=UNUSED_PASSWORD_HASH,
            display_name="Analyst",
            is_admin=False,
            group_names=["admins"],
        )
        auth_repo.create_local_user(
            email="outsider@example.com",
            password_hash=UNUSED_PASSWORD_HASH,
            display_name="Outsider",
            is_admin=False,
            group_names=["outsiders"],
        )


def _user(engine: Engine, email: str) -> UserIdentity:
    with engine.begin() as connection:
        user = AuthRepository(connection).get_user_by_email(email)
    assert user is not None
    return user


def _create_doc(
    engine: Engine,
    group_name: str,
    path: str,
    title: str,
) -> UUID:
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group(group_name)
        source_id = auth_repo.create_ingestion_source(f"{title} Source")
        auth_repo.grant_source_to_group(source_id, group_id)
        doc_repo = DocumentRepository(connection)
        doc = doc_repo.create(
            source_id=source_id,
            external_id=f"file:{path}",
            source="folder",
            mime_type="text/plain",
            title=title,
            path=path,
        )
        assert doc is not None
        return doc.id


def _doc(engine: Engine, doc_id: UUID) -> DocumentRow:
    with engine.begin() as connection:
        doc = DocumentRepository(connection).get_by_id(doc_id)
    assert doc is not None
    return doc


def test_related_documents_filters_dedupes_excludes_source_and_respects_limit(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)
    source_path = tmp_path / "source.txt"
    source_path.write_text("procurement risk source")
    related_path = tmp_path / "related.txt"
    related_path.write_text("procurement risk related")
    second_path = tmp_path / "second.txt"
    second_path.write_text("procurement second")
    inaccessible_path = tmp_path / "secret.txt"
    inaccessible_path.write_text("secret procurement")

    source_id = _create_doc(migrated_engine, "admins", str(source_path), "Source Doc")
    related_id = _create_doc(migrated_engine, "admins", str(related_path), "Related Doc")
    second_id = _create_doc(migrated_engine, "admins", str(second_path), "Second Doc")
    inaccessible_id = _create_doc(
        migrated_engine, "outsiders", str(inaccessible_path), "Secret Doc"
    )
    source_doc = _doc(migrated_engine, source_id)
    admin_group_ids = [
        str(group_id) for group_id in _user(migrated_engine, "admin@example.com").groups
    ]

    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE system_config SET value = :value WHERE key = 'search.related_docs_limit'"
            ),
            {"value": 1},
        )
        limit = int(
            connection.execute(
                sa.text("SELECT value FROM system_config WHERE key = 'search.related_docs_limit'")
            ).scalar_one()
        )

        mock_qdrant = MagicMock(spec=QdrantSearchClient)
        mock_qdrant.search.return_value = [
            SearchResult(doc_id=str(source_id), score=0.99),
            SearchResult(doc_id=str(related_id), score=0.92),
            SearchResult(doc_id=str(related_id), score=0.88),
            SearchResult(doc_id=str(inaccessible_id), score=0.95),
            SearchResult(doc_id=str(second_id), score=0.5),
        ]
        service = RelatedService(
            repository=RelatedRepository(connection),
            qdrant_client=mock_qdrant,
            encoder=MockEncoder(),
        )
        related = service.related_documents(
            doc=source_doc,
            group_ids=admin_group_ids,
            limit=limit,
        )

    assert related == [{"doc_id": str(related_id), "title": "Related Doc", "score": 0.92}]


def test_expertise_ranks_weighted_signals_and_hides_private_evidence(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)
    doc_path = tmp_path / "procurement.txt"
    doc_path.write_text("procurement risk")
    doc_id = _create_doc(migrated_engine, "admins", str(doc_path), "Procurement Doc")
    other_path = tmp_path / "other.txt"
    other_path.write_text("procurement controls")
    other_doc_id = _create_doc(migrated_engine, "admins", str(other_path), "Controls Doc")
    admin_group_ids = [
        str(group_id) for group_id in _user(migrated_engine, "admin@example.com").groups
    ]

    with migrated_engine.begin() as connection:
        analyst_id = connection.execute(
            sa.text("SELECT id FROM users WHERE email = 'analyst@example.com'")
        ).scalar_one()
        outsider_id = connection.execute(
            sa.text("SELECT id FROM users WHERE email = 'outsider@example.com'")
        ).scalar_one()
        connection.execute(
            sa.text(
                """
                INSERT INTO document_views (id, doc_id, user_id)
                VALUES (:id, :doc_id, :user_id)
                """
            ),
            {"id": uuid4().hex, "doc_id": db_uuid(doc_id), "user_id": analyst_id},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO document_comments (id, doc_id, author_id, body)
                VALUES (:id, :doc_id, :author_id, 'private body must not leak')
                """
            ),
            {"id": uuid4().hex, "doc_id": db_uuid(doc_id), "author_id": analyst_id},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO annotations (id, doc_id, user_id, text, is_private)
                VALUES (:id, :doc_id, :user_id, 'shared evidence text', false)
                """
            ),
            {"id": uuid4().hex, "doc_id": db_uuid(doc_id), "user_id": analyst_id},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO annotations (id, doc_id, user_id, text, is_private)
                VALUES (:id, :doc_id, :user_id, 'private evidence text', true)
                """
            ),
            {"id": uuid4().hex, "doc_id": db_uuid(doc_id), "user_id": outsider_id},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO alert_subscriptions (id, user_id, name, query, enabled)
                VALUES (:id, :user_id, 'Procurement', 'procurement risk', true)
                """
            ),
            {"id": uuid4().hex, "user_id": analyst_id},
        )

        mock_qdrant = MagicMock(spec=QdrantSearchClient)
        mock_qdrant.search.return_value = [
            SearchResult(doc_id=str(doc_id), score=0.97),
            SearchResult(doc_id=str(doc_id), score=0.8),
            SearchResult(doc_id=str(other_doc_id), score=0.7),
        ]
        service = RelatedService(
            repository=RelatedRepository(connection),
            qdrant_client=mock_qdrant,
            encoder=MockEncoder(),
        )
        results = service.expertise(
            topic="procurement",
            group_ids=admin_group_ids,
        )

    assert results[0]["display_name"] == "Analyst"
    assert results[0]["signals"] == {
        "views": 1,
        "comments": 1,
        "annotations": 1,
        "subscriptions": 1,
    }
    assert results[0]["top_docs"][0]["doc_id"] == str(doc_id)
    assert "private body" not in json_like(results)
    assert "private evidence" not in json_like(results)


def test_related_routes_are_registered(migrated_engine: Engine) -> None:
    app = create_app(migrated_engine, Settings(auth_provider="local", jwt_secret="x" * 32))
    paths = {route.path for route in app.routes}

    assert "/documents/{doc_id}/related" in paths
    assert "/expertise" in paths


def test_expertise_rejects_blank_topic_without_testclient(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(migrated_engine, Settings(auth_provider="local", jwt_secret="x" * 32))
    route = next(route for route in app.routes if route.path == "/expertise")

    try:
        route.endpoint(user=_user(migrated_engine, "admin@example.com"), topic="   ")
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("expected blank topic to be rejected")


def json_like(value: object) -> str:
    """Return a compact string representation for leak assertions."""
    return str(value)
