"""Integration tests for related documents and expertise services."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.models import UserIdentity
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.documents.models import DocumentRow
from services.documents.repository import DocumentRepository
from services.pipeline.jobs import PipelineJobRepository
from services.related.repository import RelatedRepository
from services.related.service import RelatedService
from services.search.encoder import DeterministicTestEncoder
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


def _doc(engine: Engine, document_id: UUID) -> DocumentRow:
    with engine.begin() as connection:
        doc = DocumentRepository(connection).get_by_id(document_id)
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
            ).bindparams(sa.bindparam("value", type_=sa.JSON())),
            {"value": 1},
        )
        limit = int(
            connection.execute(
                sa.text("SELECT value FROM system_config WHERE key = 'search.related_docs_limit'")
            ).scalar_one()
        )

        mock_qdrant = MagicMock(spec=QdrantSearchClient)
        mock_qdrant.search.return_value = [
            SearchResult(document_id=str(source_id), score=0.99),
            SearchResult(document_id=str(related_id), score=0.92),
            SearchResult(document_id=str(related_id), score=0.88),
            SearchResult(document_id=str(inaccessible_id), score=0.95),
            SearchResult(document_id=str(second_id), score=0.5),
        ]
        mock_job_repo = MagicMock(spec=PipelineJobRepository)
        mock_job_repo.get_payload.return_value = {"content_text": "procurement risk source"}
        service = RelatedService(
            repository=RelatedRepository(connection),
            qdrant_client=mock_qdrant,
            encoder=DeterministicTestEncoder(),
            job_repo=mock_job_repo,
        )
        related = service.related_documents(
            doc=source_doc,
            group_ids=admin_group_ids,
            limit=limit,
        )

    assert related == [
        {
            "document_id": str(related_id),
            "title": "Related Doc",
            "score": 0.92,
            "source": "folder",
            "reasons": [
                {"type": "semantic_similarity", "label": "Similar content", "weight": 0.92},
                {"type": "same_source", "label": "Same source", "weight": 0.3},
            ],
            "relation_score": 0.582,
        }
    ]


def test_expertise_ranks_weighted_signals_and_hides_private_evidence(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)
    doc_path = tmp_path / "procurement.txt"
    doc_path.write_text("procurement risk")
    document_id = _create_doc(migrated_engine, "admins", str(doc_path), "Procurement Doc")
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
            sa.text("""
                INSERT INTO document_views (id, document_id, user_id)
                VALUES (:id, :document_id, :user_id)
                """),
            {
                "id": uuid4().hex,
                "document_id": db_uuid(document_id),
                "user_id": analyst_id,
            },
        )
        connection.execute(
            sa.text("""
                INSERT INTO document_comments (id, document_id, author_id, body)
                VALUES (:id, :document_id, :author_id, 'private body must not leak')
                """),
            {
                "id": uuid4().hex,
                "document_id": db_uuid(document_id),
                "author_id": analyst_id,
            },
        )
        connection.execute(
            sa.text("""
                INSERT INTO annotations (id, document_id, user_id, text, is_private)
                VALUES (:id, :document_id, :user_id, 'shared evidence text', false)
                """),
            {
                "id": uuid4().hex,
                "document_id": db_uuid(document_id),
                "user_id": analyst_id,
            },
        )
        connection.execute(
            sa.text("""
                INSERT INTO annotations (id, document_id, user_id, text, is_private)
                VALUES (:id, :document_id, :user_id, 'private evidence text', true)
                """),
            {
                "id": uuid4().hex,
                "document_id": db_uuid(document_id),
                "user_id": outsider_id,
            },
        )
        connection.execute(
            sa.text("""
                INSERT INTO alert_subscriptions (id, user_id, name, query, enabled)
                VALUES (:id, :user_id, 'Procurement', 'procurement risk', true)
                """),
            {"id": uuid4().hex, "user_id": analyst_id},
        )

        mock_qdrant = MagicMock(spec=QdrantSearchClient)
        mock_qdrant.search.return_value = [
            SearchResult(document_id=str(document_id), score=0.97),
            SearchResult(document_id=str(document_id), score=0.8),
            SearchResult(document_id=str(other_doc_id), score=0.7),
        ]
        service = RelatedService(
            repository=RelatedRepository(connection),
            qdrant_client=mock_qdrant,
            encoder=DeterministicTestEncoder(),
            job_repo=MagicMock(spec=PipelineJobRepository),
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
    assert results[0]["top_docs"][0]["document_id"] == str(document_id)
    assert "private body" not in json_like(results)
    assert "private evidence" not in json_like(results)


def test_related_routes_are_registered(migrated_engine: Engine) -> None:
    """The related-docs and expertise endpoints are registered."""
    app = create_app(migrated_engine, Settings(auth_provider="local", jwt_secret="x" * 32))
    client = TestClient(app)
    assert client.get("/documents/00000000-0000-0000-0000-000000000000/related").status_code != 404
    assert client.get("/expertise").status_code != 404


def test_expertise_rejects_blank_topic_without_testclient(
    migrated_engine: Engine,
) -> None:
    _setup_users(migrated_engine)
    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE users SET password_hash = :hash WHERE email = 'admin@example.com'"),
            {"hash": hash_password("test123")},
        )
    app = create_app(migrated_engine, Settings(auth_provider="local", jwt_secret="x" * 32))
    client = TestClient(app)
    login_resp = client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "test123"}
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    resp = client.get(
        "/expertise?topic=%20%20%20",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def json_like(value: object) -> str:
    """Return a compact string representation for leak assertions."""
    return str(value)


def test_expertise_admin_passes_allow_all_to_qdrant(
    migrated_engine: Engine,
) -> None:
    """H2: expertise() with allow_all=True (admin) must forward allow_all=True to Qdrant."""
    with migrated_engine.begin() as connection:
        mock_qdrant = MagicMock(spec=QdrantSearchClient)
        mock_qdrant.search.return_value = []
        service = RelatedService(
            repository=RelatedRepository(connection),
            qdrant_client=mock_qdrant,
            encoder=DeterministicTestEncoder(),
            job_repo=MagicMock(spec=PipelineJobRepository),
        )
        service.expertise(topic="security", group_ids=[], allow_all=True)

    assert mock_qdrant.search.called
    assert mock_qdrant.search.call_args.kwargs.get("allow_all") is True


def test_expertise_subscription_excluded_when_no_group_overlap(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    """H4: subscription user not in any of the requester's groups must not appear in expertise."""
    _setup_users(migrated_engine)

    doc_path = tmp_path / "doc.txt"
    doc_path.write_text("security audit findings")
    document_id = _create_doc(migrated_engine, "admins", str(doc_path), "Audit Doc")

    # outsider subscribes to a matching topic but shares no group with admin requester
    with migrated_engine.begin() as connection:
        outsider_id = connection.execute(
            sa.text("SELECT id FROM users WHERE email = 'outsider@example.com'")
        ).scalar_one()
        connection.execute(
            sa.text(
                "INSERT INTO alert_subscriptions (id, user_id, name, query, enabled)"
                " VALUES (:id, :user_id, 'Security', 'security audit', true)"
            ),
            {"id": uuid4().hex, "user_id": outsider_id},
        )

    admin_group_ids = [str(g) for g in _user(migrated_engine, "admin@example.com").groups]

    with migrated_engine.begin() as connection:
        mock_qdrant = MagicMock(spec=QdrantSearchClient)
        mock_qdrant.search.return_value = [
            SearchResult(document_id=str(document_id), score=0.95),
        ]
        service = RelatedService(
            repository=RelatedRepository(connection),
            qdrant_client=mock_qdrant,
            encoder=DeterministicTestEncoder(),
            job_repo=MagicMock(spec=PipelineJobRepository),
        )
        results = service.expertise(
            topic="security audit",
            group_ids=admin_group_ids,
            allow_all=False,
        )

    result_user_ids = [r["user_id"] for r in results]
    assert str(outsider_id) not in result_user_ids


def test_related_documents_router_uses_transitive_group_expansion(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    """H5: /related expands transitive groups so child-group users reach parent-group docs."""
    # senior group owns source A; junior group is child of senior
    # user is in junior only — Qdrant must be called with senior group in group_ids
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        senior_id = auth_repo.ensure_group("senior")
        junior_id = auth_repo.ensure_group("junior")
        connection.execute(
            sa.text(
                "INSERT INTO group_memberships (parent_group_id, child_group_id) VALUES (:p, :c)"
            ),
            {"p": db_uuid(senior_id), "c": db_uuid(junior_id)},
        )
        # grant junior direct access so assert_doc_access passes
        junior_source_id = auth_repo.create_ingestion_source("Junior Source")
        auth_repo.grant_source_to_group(junior_source_id, junior_id)
        doc_repo = DocumentRepository(connection)
        query_doc = doc_repo.create(
            source_id=junior_source_id,
            external_id="file:/data/query.txt",
            source="folder",
            mime_type="text/plain",
            title="Query Doc",
            path=str(tmp_path / "query.txt"),
        )
        auth_repo.create_local_user(
            email="junior@example.com",
            password_hash=hash_password("secret"),
            display_name="Junior",
            is_admin=False,
            group_names=["junior"],
        )

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = []

    with (
        patch(
            "services.api.routers.documents.build_encoder",
            return_value=DeterministicTestEncoder(),
        ),
        patch("services.api.routers.documents.PipelineJobRepository") as mock_job_repo_cls,
    ):
        mock_job_repo_cls.return_value.get_payload.return_value = {"content_text": "query content"}
        client = TestClient(
            create_app(
                migrated_engine,
                Settings(
                    auth_provider="local",
                    jwt_secret="x" * 32,
                    feature_related_docs=True,
                ),
                qdrant_client=mock_qdrant,
            )
        )
        login = client.post(
            "/auth/login", json={"email": "junior@example.com", "password": "secret"}
        )
        assert login.status_code == 200
        token = login.json()["access_token"]
        client.get(
            f"/documents/{query_doc.id}/related",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert mock_qdrant.search.called
    group_ids_used = mock_qdrant.search.call_args.kwargs.get("group_ids", [])
    assert str(senior_id) in group_ids_used
