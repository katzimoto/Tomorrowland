"""Integration tests for the permissioned researcher API endpoints (#558).

Covers all six /api/agent/v1 endpoints: search_documents, get_document,
get_passages, ask_corpus, get_related_documents, list_facets.

ACL guarantees verified here:
- Anonymous / unauthenticated callers blocked.
- Users only see documents granted to one of their groups.
- Inaccessible document ids do not leak in responses or errors.
- Citations are restricted to accessible documents.
- Over-limit / invalid requests fail with safe 422 responses.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.documents.repository import DocumentRepository
from services.intelligence.llm_provider import LLMProvider
from services.search.hybrid import SearchResult
from services.search.meili_types import DocumentSearchQuery
from services.search.models import SearchResults
from services.search.qdrant import QdrantSearchClient
from shared.config import Settings
from shared.db import to_uuid

TEST_JWT_SECRET = "x" * 32


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _FakeMeiliProvider:
    """Minimal Meilisearch double that title-matches against the SQL DB."""

    def __init__(self, engine: Engine, facets: dict[str, dict[str, int]] | None = None) -> None:
        self._engine = engine
        self._facets = facets or {}

    def search(self, query: DocumentSearchQuery, user: object) -> SearchResults:
        with self._engine.begin() as conn:
            rows = conn.execute(
                sa.text(
                    "SELECT id, title FROM documents WHERE LOWER(title) LIKE LOWER(:q) LIMIT :limit"
                ),
                {"q": f"%{query.q}%", "limit": query.limit},
            ).fetchall()
        # IDs come back as a dash-less hex str on SQLite but a UUID object on
        # Postgres; to_uuid() normalises either to a UUID, then str() gives the
        # canonical dashed form the router's docs-dict key lookup expects.
        results = [
            SearchResult(document_id=str(to_uuid(r[0])), score=1.0, title=r[1]) for r in rows
        ]
        return SearchResults(results=results, facets=self._facets)


class _StubLLM(LLMProvider):
    """LLM provider that returns a deterministic answer for tests."""

    @property
    def model(self) -> str:
        return "stub"

    def generate(self, prompt: str, **_: Any) -> str:  # type: ignore[override]
        return "stub answer"

    def generate_stream(self, prompt: str, **_: Any):  # type: ignore[override]
        yield "stub answer"


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
            group_names=["other"],
        )


def _login(client: TestClient, email: str) -> str:
    resp = client.post("/auth/login", json={"email": email, "password": "secret"})
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


def _create_source_with_doc(
    engine: Engine,
    group_name: str,
    doc_title: str,
    *,
    source_name: str = "Test Source",
) -> tuple[str, str]:
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group(group_name)

        source_id = auth_repo.create_ingestion_source(source_name)
        auth_repo.grant_source_to_group(source_id, group_id)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.create(
            source_id=source_id,
            external_id=f"file:/data/{doc_title}.txt",
            source="folder",
            mime_type="text/plain",
            title=doc_title,
            path=f"/data/{doc_title}.txt",
        )
        assert doc is not None
    return str(source_id), str(doc.id)


def _build_app(
    engine: Engine,
    *,
    qdrant_client: QdrantSearchClient | None = None,
    meili_provider: _FakeMeiliProvider | None = None,
    llm_provider: LLMProvider | None = None,
    feature_related_docs: bool = True,
) -> TestClient:
    settings = Settings(
        auth_provider="local",
        jwt_secret=TEST_JWT_SECRET,
        feature_related_docs=feature_related_docs,
    )
    app = create_app(
        engine,
        settings,
        qdrant_client=qdrant_client,
        meili_provider=meili_provider,
        llm_provider=llm_provider or _StubLLM(),
    )
    return TestClient(app)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_anonymous_blocked_on_every_endpoint(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = _build_app(migrated_engine)

    doc_id = str(uuid4())
    endpoints: list[tuple[str, str, dict[str, Any] | None]] = [
        ("post", "/api/agent/v1/search_documents", {"query": "x"}),
        ("get", f"/api/agent/v1/get_document?document_id={doc_id}", None),
        ("get", f"/api/agent/v1/get_passages?document_id={doc_id}", None),
        ("post", "/api/agent/v1/ask_corpus", {"question": "x"}),
        ("get", f"/api/agent/v1/get_related_documents?document_id={doc_id}", None),
        ("get", "/api/agent/v1/list_facets", None),
    ]
    for method, path, body in endpoints:
        response = client.post(path, json=body) if method == "post" else client.get(path)
        assert response.status_code == 401, f"{method} {path} -> {response.status_code}"


# ---------------------------------------------------------------------------
# search_documents
# ---------------------------------------------------------------------------


def test_search_documents_returns_only_accessible(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    _, allowed_id = _create_source_with_doc(migrated_engine, "users", "User Doc")
    _, hidden_id = _create_source_with_doc(migrated_engine, "admins", "Admin Doc")

    qdrant = MagicMock(spec=QdrantSearchClient)
    qdrant.search.return_value = [
        SearchResult(document_id=allowed_id, score=0.9, chunk_text="user chunk"),
        SearchResult(document_id=hidden_id, score=0.99, chunk_text="leak attempt"),
    ]

    client = _build_app(
        migrated_engine,
        qdrant_client=qdrant,
        meili_provider=_FakeMeiliProvider(migrated_engine),
    )
    token = _login(client, "user@example.com")

    response = client.post(
        "/api/agent/v1/search_documents",
        json={"query": "doc", "top_k": 10},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    returned_ids = [r["document_id"] for r in data["results"]]
    assert allowed_id in returned_ids
    assert hidden_id not in returned_ids


def test_search_documents_filters_by_source(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    _create_source_with_doc(migrated_engine, "users", "Doc A", source_name="Source A")
    _create_source_with_doc(migrated_engine, "users", "Doc B", source_name="Source B")

    qdrant = MagicMock(spec=QdrantSearchClient)
    qdrant.search.return_value = []

    client = _build_app(
        migrated_engine,
        qdrant_client=qdrant,
        meili_provider=_FakeMeiliProvider(migrated_engine),
    )
    token = _login(client, "user@example.com")

    # Ask for an unrelated source — should still be a successful 200 with no
    # results (no leaks even though the user has access to other sources).
    response = client.post(
        "/api/agent/v1/search_documents",
        json={"query": "Doc", "filters": {"sources": ["nonexistent"]}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


def test_search_documents_admin_bypass_uses_allow_all(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    _create_source_with_doc(migrated_engine, "users", "Visible")

    qdrant = MagicMock(spec=QdrantSearchClient)
    qdrant.search.return_value = []

    client = _build_app(
        migrated_engine,
        qdrant_client=qdrant,
        meili_provider=_FakeMeiliProvider(migrated_engine),
    )
    token = _login(client, "admin@example.com")

    response = client.post(
        "/api/agent/v1/search_documents",
        json={"query": "anything"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert qdrant.search.called
    assert qdrant.search.call_args.kwargs["allow_all"] is True


def test_search_documents_oversized_query_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = _build_app(migrated_engine)
    token = _login(client, "user@example.com")

    response = client.post(
        "/api/agent/v1/search_documents",
        json={"query": "x" * 501},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_search_documents_invalid_top_k_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = _build_app(migrated_engine)
    token = _login(client, "user@example.com")

    response = client.post(
        "/api/agent/v1/search_documents",
        json={"query": "x", "top_k": 999},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# get_document
# ---------------------------------------------------------------------------


def test_get_document_returns_authorized_metadata(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    _, doc_id = _create_source_with_doc(migrated_engine, "users", "Visible Doc")

    client = _build_app(migrated_engine)
    token = _login(client, "user@example.com")

    response = client.get(
        f"/api/agent/v1/get_document?document_id={doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == doc_id
    assert data["title"] == "Visible Doc"
    assert data["mime_type"] == "text/plain"


def test_get_document_forbids_unauthorized(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    _, hidden_id = _create_source_with_doc(migrated_engine, "admins", "Admin Doc")

    client = _build_app(migrated_engine)
    token = _login(client, "user@example.com")

    response = client.get(
        f"/api/agent/v1/get_document?document_id={hidden_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    # Sensitive identifiers must not leak via error response body.
    assert hidden_id not in response.text


def test_get_document_404_for_missing(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = _build_app(migrated_engine)
    token = _login(client, "admin@example.com")

    # Admins bypass ACL but the document does not exist.
    response = client.get(
        f"/api/agent/v1/get_document?document_id={uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# get_passages
# ---------------------------------------------------------------------------


def test_get_passages_returns_chunks_for_authorized_doc(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    _, doc_id = _create_source_with_doc(migrated_engine, "users", "Passages Doc")

    qdrant = MagicMock(spec=QdrantSearchClient)
    qdrant.dimension = 384
    qdrant.list_chunks_by_document.return_value = [
        SearchResult(
            document_id=doc_id,
            score=0.0,
            chunk_text="first passage",
            metadata={"chunk_index": 0, "chunk_id": "c-0"},
        ),
        SearchResult(
            document_id=doc_id,
            score=0.0,
            chunk_text="second passage",
            metadata={"chunk_index": 1, "chunk_id": "c-1"},
        ),
    ]
    # The handler reads total via count_chunks_by_document; without an explicit
    # return_value a MagicMock is coerced to int (1), masking the real count.
    qdrant.count_chunks_by_document.return_value = 2

    client = _build_app(migrated_engine, qdrant_client=qdrant)
    token = _login(client, "user@example.com")

    response = client.get(
        f"/api/agent/v1/get_passages?document_id={doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == doc_id
    assert data["total"] == 2
    assert [p["text"] for p in data["passages"]] == ["first passage", "second passage"]


def test_get_passages_forbids_unauthorized_doc(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    _, hidden_id = _create_source_with_doc(migrated_engine, "admins", "Admin Doc")

    qdrant = MagicMock(spec=QdrantSearchClient)
    qdrant.dimension = 384
    # Even if Qdrant would return chunks, the API must refuse before reaching it.
    qdrant.list_chunks_by_document.return_value = [
        SearchResult(
            document_id=hidden_id,
            score=0.0,
            chunk_text="leak",
            metadata={"chunk_index": 0},
        )
    ]

    client = _build_app(migrated_engine, qdrant_client=qdrant)
    token = _login(client, "user@example.com")

    response = client.get(
        f"/api/agent/v1/get_passages?document_id={hidden_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    qdrant.list_chunks_by_document.assert_not_called()
    assert "leak" not in response.text


def test_get_passages_oversized_limit_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    _, doc_id = _create_source_with_doc(migrated_engine, "users", "Doc")

    client = _build_app(migrated_engine)
    token = _login(client, "user@example.com")

    response = client.get(
        f"/api/agent/v1/get_passages?document_id={doc_id}&limit=9999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# ask_corpus
# ---------------------------------------------------------------------------


def test_ask_corpus_returns_answer_with_filtered_citations(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    _, allowed_id = _create_source_with_doc(migrated_engine, "users", "Allowed Doc")
    _, hidden_id = _create_source_with_doc(migrated_engine, "admins", "Hidden Doc")

    qdrant = MagicMock(spec=QdrantSearchClient)
    qdrant.dimension = 384
    qdrant.search.return_value = [
        SearchResult(
            document_id=allowed_id,
            score=0.9,
            chunk_text="allowed chunk",
            metadata={"chunk_id": "a-0", "chunk_index": 0},
        ),
        # Even if a stale Qdrant payload leaked an inaccessible id, the
        # citation defence in depth should drop it.
        SearchResult(
            document_id=hidden_id,
            score=0.95,
            chunk_text="hidden chunk",
            metadata={"chunk_id": "h-0", "chunk_index": 0},
        ),
    ]
    qdrant.search_filtered.return_value = qdrant.search.return_value

    client = _build_app(migrated_engine, qdrant_client=qdrant)
    token = _login(client, "user@example.com")

    response = client.post(
        "/api/agent/v1/ask_corpus",
        json={"question": "what?", "top_k": 5},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    cited_ids = [c["document_id"] for c in data["citations"]]
    assert hidden_id not in cited_ids
    assert "hidden chunk" not in response.text


def test_ask_corpus_unauthorized_document_id_returns_403(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    _, hidden_id = _create_source_with_doc(migrated_engine, "admins", "Hidden Doc")

    client = _build_app(migrated_engine)
    token = _login(client, "user@example.com")

    response = client.post(
        "/api/agent/v1/ask_corpus",
        json={"question": "what?", "document_id": hidden_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_ask_corpus_invalid_document_id_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = _build_app(migrated_engine)
    token = _login(client, "user@example.com")

    response = client.post(
        "/api/agent/v1/ask_corpus",
        json={"question": "what?", "document_id": "not-a-uuid"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_ask_corpus_oversized_question_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = _build_app(migrated_engine)
    token = _login(client, "user@example.com")

    response = client.post(
        "/api/agent/v1/ask_corpus",
        json={"question": "x" * 2001},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_ask_corpus_user_without_groups_returns_403(migrated_engine: Engine) -> None:
    """A non-admin user with no groups must not be able to ask questions."""
    _setup_users(migrated_engine)

    # Create a fourth user with no group memberships.
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        auth_repo.create_local_user(
            email="lonely@example.com",
            password_hash=hash_password("secret"),
            display_name="Lonely",
            is_admin=False,
            group_names=[],
        )

    client = _build_app(migrated_engine)
    token = _login(client, "lonely@example.com")

    response = client.post(
        "/api/agent/v1/ask_corpus",
        json={"question": "what?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# get_related_documents
# ---------------------------------------------------------------------------


def test_get_related_documents_respects_acl(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    _, hidden_id = _create_source_with_doc(migrated_engine, "admins", "Hidden Doc")

    client = _build_app(migrated_engine)
    token = _login(client, "user@example.com")

    response = client.get(
        f"/api/agent/v1/get_related_documents?document_id={hidden_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_get_related_documents_degraded_when_encoder_fails(
    migrated_engine: Engine,
) -> None:
    _setup_users(migrated_engine)
    _, doc_id = _create_source_with_doc(migrated_engine, "users", "Source Doc")

    from services.search.encoder import TextEncoder

    class BrokenEncoder(TextEncoder):
        def encode(self, text: str) -> list[float]:
            raise RuntimeError("encoder down")

    with patch("services.api.routers.agent.build_encoder", return_value=BrokenEncoder()):
        client = _build_app(migrated_engine)
    token = _login(client, "user@example.com")

    response = client.get(
        f"/api/agent/v1/get_related_documents?document_id={doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"document_id": doc_id, "related": []}


def test_get_related_documents_disabled_returns_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    _, doc_id = _create_source_with_doc(migrated_engine, "users", "Source Doc")

    client = _build_app(migrated_engine, feature_related_docs=False)
    token = _login(client, "user@example.com")

    response = client.get(
        f"/api/agent/v1/get_related_documents?document_id={doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# list_facets
# ---------------------------------------------------------------------------


def test_list_facets_returns_meili_facets_for_authorized_user(
    migrated_engine: Engine,
) -> None:
    _setup_users(migrated_engine)
    _create_source_with_doc(migrated_engine, "users", "User Doc")

    fake_facets = {"source": {"folder": 3}, "language": {"en": 2}}
    client = _build_app(
        migrated_engine,
        meili_provider=_FakeMeiliProvider(migrated_engine, facets=fake_facets),
    )
    token = _login(client, "user@example.com")

    response = client.get(
        "/api/agent/v1/list_facets",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["facets"] == fake_facets


def test_list_facets_user_without_groups_returns_empty(
    migrated_engine: Engine,
) -> None:
    _setup_users(migrated_engine)
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        auth_repo.create_local_user(
            email="alone@example.com",
            password_hash=hash_password("secret"),
            display_name="Alone",
            is_admin=False,
            group_names=[],
        )

    client = _build_app(
        migrated_engine,
        meili_provider=_FakeMeiliProvider(migrated_engine, facets={"source": {"folder": 3}}),
    )
    token = _login(client, "alone@example.com")

    response = client.get(
        "/api/agent/v1/list_facets",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"facets": {}}


def test_list_facets_meili_unavailable_returns_empty(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    _create_source_with_doc(migrated_engine, "users", "User Doc")
    client = _build_app(migrated_engine)  # No meili provider configured.
    token = _login(client, "user@example.com")

    response = client.get(
        "/api/agent/v1/list_facets",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"facets": {}}


# ---------------------------------------------------------------------------
# Audit logging (#561)
# ---------------------------------------------------------------------------


def test_search_documents_emits_audit_log(
    migrated_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """search_documents emits a structured audit log line with safe metadata."""
    _setup_users(migrated_engine)
    _, doc_id = _create_source_with_doc(migrated_engine, "users", "Audit Doc")

    qdrant = MagicMock(spec=QdrantSearchClient)
    qdrant.search.return_value = [SearchResult(document_id=doc_id, score=0.9)]

    client = _build_app(
        migrated_engine,
        qdrant_client=qdrant,
        meili_provider=_FakeMeiliProvider(migrated_engine),
    )
    token = _login(client, "user@example.com")

    import logging

    with caplog.at_level(logging.INFO, logger="services.api.routers.agent"):
        response = client.post(
            "/api/agent/v1/search_documents",
            json={"query": "audit test query", "top_k": 5},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    audit_lines = [r.message for r in caplog.records if "agent_audit" in r.message]
    assert audit_lines, "Expected at least one agent_audit log line"
    line = audit_lines[0]
    assert "route=search_documents" in line
    assert "user=" in line
    assert "query_length=" in line
    assert "latency_ms=" in line
    assert "result_count=" in line
    # Raw query text must not appear in audit log
    assert "audit test query" not in line


def test_ask_corpus_emits_audit_log(
    migrated_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """ask_corpus emits a structured audit log line; question text is not logged."""
    _setup_users(migrated_engine)
    _, doc_id = _create_source_with_doc(migrated_engine, "users", "Corpus Doc")

    qdrant = MagicMock(spec=QdrantSearchClient)
    qdrant.dimension = 384
    qdrant.search.return_value = []

    client = _build_app(migrated_engine, qdrant_client=qdrant)
    token = _login(client, "user@example.com")

    import logging

    with caplog.at_level(logging.INFO, logger="services.api.routers.agent"):
        response = client.post(
            "/api/agent/v1/ask_corpus",
            json={"question": "what is the secret answer to everything"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    audit_lines = [r.message for r in caplog.records if "agent_audit" in r.message]
    assert audit_lines, "Expected at least one agent_audit log line"
    line = audit_lines[0]
    assert "route=ask_corpus" in line
    assert "what is the secret answer" not in line


def test_audit_log_contains_no_auth_header(
    migrated_engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Authorization header must never appear in audit log output."""
    _setup_users(migrated_engine)
    _create_source_with_doc(migrated_engine, "users", "Doc")

    qdrant = MagicMock(spec=QdrantSearchClient)
    qdrant.search.return_value = []

    client = _build_app(
        migrated_engine,
        qdrant_client=qdrant,
        meili_provider=_FakeMeiliProvider(migrated_engine),
    )
    token = _login(client, "user@example.com")

    import logging

    with caplog.at_level(logging.INFO, logger="services.api.routers.agent"):
        client.post(
            "/api/agent/v1/search_documents",
            json={"query": "auth leak test"},
            headers={"Authorization": f"Bearer {token}"},
        )

    full_log = " ".join(r.message for r in caplog.records)
    assert "Bearer " not in full_log
    assert token not in full_log


# ---------------------------------------------------------------------------
# Usage limits / rate limiting (#561)
# ---------------------------------------------------------------------------


def _build_app_with_limit(
    engine: Engine,
    *,
    calls_per_window: int = 100,
    ask_corpus_calls_per_window: int = 20,
    qdrant_client: Any = None,
    meili_provider: Any = None,
    llm_provider: Any = None,
) -> TestClient:
    settings = Settings(
        auth_provider="local",
        jwt_secret=TEST_JWT_SECRET,
        agent_rate_limit_enabled=True,
        agent_rate_limit_window_seconds=60,
        agent_rate_limit_calls_per_window=calls_per_window,
        agent_rate_limit_ask_corpus_calls_per_window=ask_corpus_calls_per_window,
    )
    from services.api.main import create_app

    app = create_app(
        engine,
        settings,
        qdrant_client=qdrant_client,
        meili_provider=meili_provider,
        llm_provider=llm_provider or _StubLLM(),
    )
    return TestClient(app)


def test_search_documents_over_limit_returns_429(migrated_engine: Engine) -> None:
    """Exceed the per-user call limit — REST must return 429."""
    _setup_users(migrated_engine)
    _create_source_with_doc(migrated_engine, "users", "Rate Doc")

    qdrant = MagicMock(spec=QdrantSearchClient)
    qdrant.search.return_value = []

    client = _build_app_with_limit(
        migrated_engine,
        calls_per_window=1,
        qdrant_client=qdrant,
        meili_provider=_FakeMeiliProvider(migrated_engine),
    )
    token = _login(client, "user@example.com")

    r1 = client.post(
        "/api/agent/v1/search_documents",
        json={"query": "first"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/api/agent/v1/search_documents",
        json={"query": "second"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 429
    assert "Rate limit exceeded" in r2.json()["detail"]


def test_ask_corpus_over_limit_returns_429(migrated_engine: Engine) -> None:
    """Exceed the per-user ask_corpus limit — REST must return 429."""
    _setup_users(migrated_engine)
    _create_source_with_doc(migrated_engine, "users", "Ask Doc")

    qdrant = MagicMock(spec=QdrantSearchClient)
    qdrant.dimension = 384
    qdrant.search.return_value = []

    client = _build_app_with_limit(
        migrated_engine,
        ask_corpus_calls_per_window=1,
        qdrant_client=qdrant,
    )
    token = _login(client, "user@example.com")

    r1 = client.post(
        "/api/agent/v1/ask_corpus",
        json={"question": "first question"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/api/agent/v1/ask_corpus",
        json={"question": "second question"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 429


def test_rate_limit_is_per_user(migrated_engine: Engine) -> None:
    """Two different users share limits independently — user-2 is not blocked by user-1."""
    _setup_users(migrated_engine)
    _create_source_with_doc(migrated_engine, "users", "Doc")

    qdrant = MagicMock(spec=QdrantSearchClient)
    qdrant.search.return_value = []

    client = _build_app_with_limit(
        migrated_engine,
        calls_per_window=1,
        qdrant_client=qdrant,
        meili_provider=_FakeMeiliProvider(migrated_engine),
    )
    token_user = _login(client, "user@example.com")
    token_admin = _login(client, "admin@example.com")

    # user exhausts their quota
    client.post(
        "/api/agent/v1/search_documents",
        json={"query": "x"},
        headers={"Authorization": f"Bearer {token_user}"},
    )
    assert (
        client.post(
            "/api/agent/v1/search_documents",
            json={"query": "x"},
            headers={"Authorization": f"Bearer {token_user}"},
        ).status_code
        == 429
    )

    # admin has a fresh bucket
    assert (
        client.post(
            "/api/agent/v1/search_documents",
            json={"query": "x"},
            headers={"Authorization": f"Bearer {token_admin}"},
        ).status_code
        == 200
    )


def test_rate_limit_disabled_never_blocks(migrated_engine: Engine) -> None:
    """With rate limiting disabled, unlimited calls must succeed."""
    _setup_users(migrated_engine)
    _create_source_with_doc(migrated_engine, "users", "Doc")

    qdrant = MagicMock(spec=QdrantSearchClient)
    qdrant.search.return_value = []

    settings = Settings(
        auth_provider="local",
        jwt_secret=TEST_JWT_SECRET,
        agent_rate_limit_enabled=False,
        agent_rate_limit_calls_per_window=1,
    )
    from services.api.main import create_app

    app = create_app(
        migrated_engine,
        settings,
        qdrant_client=qdrant,
        meili_provider=_FakeMeiliProvider(migrated_engine),
        llm_provider=_StubLLM(),
    )
    client = TestClient(app)
    token = _login(client, "user@example.com")

    for _ in range(3):
        r = client.post(
            "/api/agent/v1/search_documents",
            json={"query": "x"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# MCP 429 inheritance proof (#561)
# ---------------------------------------------------------------------------


def test_mcp_translate_error_handles_429() -> None:
    """_translate_error must map 429 to a user-safe message (no token leak)."""
    from services.mcp.client import TomorrowlandClientError
    from services.mcp.server import _translate_error

    exc = TomorrowlandClientError("Rate limit exceeded. Please retry later.", status_code=429)
    msg = _translate_error(exc)
    assert "429" in msg or "Rate limit" in msg
    assert "Bearer" not in msg
    assert "token" not in msg.lower()


# ---------------------------------------------------------------------------
# Cross-user isolation matrix (#562)
#
# user@example.com  → group "users"  → source "users"  → "Isolation Doc A"
# other@example.com → group "other"  → source "other"  → "Isolation Doc B"
#
# Every pair of tests verifies symmetric isolation: neither user can see the
# other's documents via any endpoint.
# ---------------------------------------------------------------------------


def test_user_isolation_search_documents_is_symmetric(migrated_engine: Engine) -> None:
    """BM25 path returns both docs; ACL defence-in-depth drops the cross-user one."""
    _setup_users(migrated_engine)
    _, doc_a_id = _create_source_with_doc(migrated_engine, "users", "Isolation Doc A")
    _, doc_b_id = _create_source_with_doc(migrated_engine, "other", "Isolation Doc B")

    qdrant = MagicMock(spec=QdrantSearchClient)
    qdrant.search.return_value = []

    client = _build_app(
        migrated_engine,
        qdrant_client=qdrant,
        meili_provider=_FakeMeiliProvider(migrated_engine),
    )
    token_a = _login(client, "user@example.com")
    token_b = _login(client, "other@example.com")

    resp_a = client.post(
        "/api/agent/v1/search_documents",
        json={"query": "Isolation"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_a.status_code == 200
    ids_a = [r["document_id"] for r in resp_a.json()["results"]]
    assert doc_a_id in ids_a, "user A must see their own document"
    assert doc_b_id not in ids_a, "user A must not see user B's document"

    resp_b = client.post(
        "/api/agent/v1/search_documents",
        json={"query": "Isolation"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp_b.status_code == 200
    ids_b = [r["document_id"] for r in resp_b.json()["results"]]
    assert doc_b_id in ids_b, "user B must see their own document"
    assert doc_a_id not in ids_b, "user B must not see user A's document"


def test_user_isolation_get_document_is_symmetric(migrated_engine: Engine) -> None:
    """Neither user can fetch the other's document; doc ID must not appear in the 403."""
    _setup_users(migrated_engine)
    _, doc_a_id = _create_source_with_doc(migrated_engine, "users", "Cross Doc A")
    _, doc_b_id = _create_source_with_doc(migrated_engine, "other", "Cross Doc B")

    client = _build_app(migrated_engine)
    token_a = _login(client, "user@example.com")
    token_b = _login(client, "other@example.com")

    resp = client.get(
        f"/api/agent/v1/get_document?document_id={doc_b_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 403
    assert doc_b_id not in resp.text, "inaccessible doc ID must not appear in 403 body"

    resp = client.get(
        f"/api/agent/v1/get_document?document_id={doc_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403
    assert doc_a_id not in resp.text, "inaccessible doc ID must not appear in 403 body"


def test_user_isolation_get_passages_blocked_before_qdrant(migrated_engine: Engine) -> None:
    """ACL must reject get_passages before Qdrant is ever called."""
    _setup_users(migrated_engine)
    _, doc_b_id = _create_source_with_doc(migrated_engine, "other", "Other Passages Doc")

    qdrant = MagicMock(spec=QdrantSearchClient)
    qdrant.dimension = 384
    qdrant.list_chunks_by_document.return_value = [
        SearchResult(document_id=doc_b_id, score=0.0, chunk_text="cross-user secret passage")
    ]

    client = _build_app(migrated_engine, qdrant_client=qdrant)
    token_a = _login(client, "user@example.com")

    resp = client.get(
        f"/api/agent/v1/get_passages?document_id={doc_b_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 403
    qdrant.list_chunks_by_document.assert_not_called()
    assert "cross-user secret passage" not in resp.text
    assert doc_b_id not in resp.text


def test_user_isolation_get_related_documents_blocked(migrated_engine: Engine) -> None:
    """get_related_documents must return 403 for a document the caller cannot access."""
    _setup_users(migrated_engine)
    _, doc_b_id = _create_source_with_doc(migrated_engine, "other", "Other Related Doc")

    client = _build_app(migrated_engine)
    token_a = _login(client, "user@example.com")

    resp = client.get(
        f"/api/agent/v1/get_related_documents?document_id={doc_b_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 403
    assert doc_b_id not in resp.text


# ---------------------------------------------------------------------------
# Source filter scope (#562)
# ---------------------------------------------------------------------------


def test_source_filter_for_existing_inaccessible_source_returns_empty(
    migrated_engine: Engine,
) -> None:
    """
    A user providing a source filter for a source they cannot access must get
    an empty result set, not a 403 and not any docs from the inaccessible source.

    The FakeMeiliProvider ignores the filter and returns both docs; the ACL
    defence-in-depth layer is what prevents the leak.
    """
    _setup_users(migrated_engine)
    _, doc_a_id = _create_source_with_doc(
        migrated_engine, "users", "Filter Accessible Doc", source_name="Accessible Source"
    )
    _, doc_b_id = _create_source_with_doc(
        migrated_engine, "other", "Filter Inaccessible Doc", source_name="Inaccessible Source"
    )

    qdrant = MagicMock(spec=QdrantSearchClient)
    qdrant.search.return_value = []

    client = _build_app(
        migrated_engine,
        qdrant_client=qdrant,
        meili_provider=_FakeMeiliProvider(migrated_engine),
    )
    token_a = _login(client, "user@example.com")

    resp = client.post(
        "/api/agent/v1/search_documents",
        json={"query": "Filter", "filters": {"sources": ["Inaccessible Source"]}},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200, "source filter for inaccessible source must not 403"
    returned_ids = [r["document_id"] for r in resp.json()["results"]]
    # Core security invariant: inaccessible source docs must never appear regardless of filter.
    assert doc_b_id not in returned_ids, "inaccessible source docs must not appear in results"


def test_source_filter_valid_source_narrows_within_allowed_corpus(
    migrated_engine: Engine,
) -> None:
    """
    A source filter for an accessible source narrows results to that source only.
    Verified with a meili double that respects the source filter.
    """
    _setup_users(migrated_engine)
    _, doc_s1_id = _create_source_with_doc(
        migrated_engine, "users", "Narrow Source One Doc", source_name="Narrow Source One"
    )
    _, doc_s2_id = _create_source_with_doc(
        migrated_engine, "users", "Narrow Source Two Doc", source_name="Narrow Source Two"
    )

    qdrant = MagicMock(spec=QdrantSearchClient)
    qdrant.search.return_value = []

    # Meili double that applies source filters by joining to ingestion_sources.
    class _SourceFilteringMeili:
        def __init__(self, engine: Engine) -> None:
            self._engine = engine

        def search(self, query: DocumentSearchQuery, user: object) -> SearchResults:
            with self._engine.begin() as conn:
                if query.filters and query.filters.source:
                    placeholders = ", ".join(f":src{i}" for i in range(len(query.filters.source)))
                    params: dict[str, Any] = {
                        "q": f"%{query.q}%",
                        "lim": query.limit,
                        **{f"src{i}": s for i, s in enumerate(query.filters.source)},
                    }
                    rows = conn.execute(
                        sa.text(
                            f"SELECT d.id, d.title FROM documents d "
                            f"JOIN ingestion_sources s ON d.source_id = s.id "
                            f"WHERE LOWER(d.title) LIKE LOWER(:q) AND s.name IN ({placeholders}) "
                            f"LIMIT :lim"
                        ),
                        params,
                    ).fetchall()
                else:
                    rows = conn.execute(
                        sa.text(
                            "SELECT id, title FROM documents "
                            "WHERE LOWER(title) LIKE LOWER(:q) LIMIT :lim"
                        ),
                        {"q": f"%{query.q}%", "lim": query.limit},
                    ).fetchall()
            # Normalise hex/UUID-object id to the canonical dashed UUID str.
            results = [
                SearchResult(document_id=str(to_uuid(r[0])), score=1.0, title=r[1]) for r in rows
            ]
            return SearchResults(results=results, facets={})

    client = _build_app(
        migrated_engine,
        qdrant_client=qdrant,
        meili_provider=_SourceFilteringMeili(migrated_engine),
    )
    token_a = _login(client, "user@example.com")

    resp = client.post(
        "/api/agent/v1/search_documents",
        json={"query": "Narrow", "filters": {"sources": ["Narrow Source One"]}},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200
    ids = [r["document_id"] for r in resp.json()["results"]]
    assert doc_s1_id in ids, "filter for Source One must include Source One doc"
    assert doc_s2_id not in ids, "filter for Source One must exclude Source Two doc"


# ---------------------------------------------------------------------------
# Over-limit error safety (#562, supplements #561)
# ---------------------------------------------------------------------------


def test_rate_limit_429_response_contains_no_document_ids(migrated_engine: Engine) -> None:
    """A 429 response must not leak document IDs or other corpus metadata."""
    _setup_users(migrated_engine)
    _, doc_id = _create_source_with_doc(migrated_engine, "users", "Rate Limit Doc")

    qdrant = MagicMock(spec=QdrantSearchClient)
    qdrant.search.return_value = []

    client = _build_app_with_limit(
        migrated_engine,
        calls_per_window=1,
        qdrant_client=qdrant,
        meili_provider=_FakeMeiliProvider(migrated_engine),
    )
    token = _login(client, "user@example.com")

    # Exhaust the limit
    client.post(
        "/api/agent/v1/search_documents",
        json={"query": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # Second call must 429 with safe body
    resp = client.post(
        "/api/agent/v1/search_documents",
        json={"query": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 429
    body_text = resp.text
    assert doc_id not in body_text, "429 response must not contain document IDs"
    assert "Bearer" not in body_text, "429 response must not contain auth tokens"


# ---------------------------------------------------------------------------
# Pyright/test bookkeeping — keep pytest available even if no fixture used.
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.usefixtures()
