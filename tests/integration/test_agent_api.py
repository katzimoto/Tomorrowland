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
                sa.text("SELECT id, title FROM documents WHERE title LIKE :q LIMIT :limit"),
                {"q": f"%{query.q}%", "limit": query.limit},
            ).fetchall()
        results = [SearchResult(document_id=str(r[0]), score=1.0, title=r[1]) for r in rows]
        return SearchResults(results=results, facets=self._facets)


class _StubLLM(LLMProvider):
    """LLM provider that returns a deterministic answer for tests."""

    def __init__(self) -> None:
        self.model = "stub"

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
# Pyright/test bookkeeping — keep pytest available even if no fixture used.
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.usefixtures()
