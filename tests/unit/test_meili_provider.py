from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from services.search.meili_provider import MeilisearchSearchProvider, _build_user_filter
from services.search.meili_settings import INDEX_NAME, SHADOW_INDEX_NAME
from services.search.meili_types import (
    ChunkMetadata,
    DocumentSearchFilters,
    DocumentSearchQuery,
    SearchChunkRecord,
)
from services.search.models import SearchResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_G1 = str(uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001"))


def _admin() -> MagicMock:
    u = MagicMock()
    u.is_admin = True
    u.groups = []
    return u


def _user_with_groups(*ids: str) -> MagicMock:
    u = MagicMock()
    u.is_admin = False
    u.groups = [uuid.UUID(g) if "-" in g else uuid.UUID(int=int(g)) for g in ids]
    return u


def _no_group_user() -> MagicMock:
    u = MagicMock()
    u.is_admin = False
    u.groups = []
    return u


def _mock_task(uid: int = 1) -> MagicMock:
    t = MagicMock()
    t.task_uid = uid
    return t


def _provider() -> tuple[MagicMock, MeilisearchSearchProvider]:
    client = MagicMock()
    client.index.return_value.add_documents.return_value = _mock_task()
    client.index.return_value.update_documents.return_value = _mock_task()
    client.index.return_value.delete_document.return_value = _mock_task()
    client.index.return_value.delete_documents_by_filter.return_value = _mock_task()
    client.swap_indexes.return_value = _mock_task()
    return client, MeilisearchSearchProvider(client)


def _chunk(content: str = "hello", groups: list[str] | None = None) -> SearchChunkRecord:
    return SearchChunkRecord.from_parts(
        document_id="doc-1",
        chunk_index=0,
        title="Title",
        content=content,
        allowed_group_ids=groups or [_G1],
    )


def _query(**kwargs) -> DocumentSearchQuery:  # type: ignore[no-untyped-def]
    defaults: dict = {
        "q": "test",
        "language": "auto",
        "filters": DocumentSearchFilters(),
        "sort": "relevance",
        "limit": 20,
        "offset": 0,
    }
    defaults.update(kwargs)
    return DocumentSearchQuery(**defaults)


# ---------------------------------------------------------------------------
# index / index_batch
# ---------------------------------------------------------------------------


def test_index_calls_add_documents_on_live_index() -> None:
    client, provider = _provider()
    chunk = _chunk()
    task_uid = provider.index(chunk)

    client.index.assert_called_with(INDEX_NAME)
    client.index().add_documents.assert_called_once()
    assert task_uid == "1"


def test_index_shadow_calls_add_documents_on_shadow_index() -> None:
    client, provider = _provider()
    provider.index(_chunk(), shadow=True)
    client.index.assert_called_with(SHADOW_INDEX_NAME)


def test_index_batch_sends_all_documents() -> None:
    client, provider = _provider()
    chunks = [_chunk("a"), _chunk("b")]
    provider.index_batch(chunks)

    docs_sent = client.index().add_documents.call_args[0][0]
    assert len(docs_sent) == 2


def test_index_batch_shadow_targets_shadow_index() -> None:
    client, provider = _provider()
    provider.index_batch([_chunk()], shadow=True)
    client.index.assert_called_with(SHADOW_INDEX_NAME)


# ---------------------------------------------------------------------------
# patch_translations
# ---------------------------------------------------------------------------


def test_patch_translations_uses_update_not_add() -> None:
    client, provider = _provider()
    provider.patch_translations("doc_x_chunk_0000", {"content_en": "hello"})
    client.index().update_documents.assert_called_once()
    client.index().add_documents.assert_not_called()


def test_patch_translations_includes_id_and_fields() -> None:
    client, provider = _provider()
    provider.patch_translations("doc_x_chunk_0000", {"content_en": "hi", "title_en": "T"})
    payload = client.index().update_documents.call_args[0][0][0]
    assert payload["id"] == "doc_x_chunk_0000"
    assert payload["content_en"] == "hi"
    assert payload["title_en"] == "T"


def test_patch_translations_skips_none_values() -> None:
    client, provider = _provider()
    provider.patch_translations("id", {"content_en": "hi", "content_he": None})
    payload = client.index().update_documents.call_args[0][0][0]
    assert "content_he" not in payload


# ---------------------------------------------------------------------------
# remove / remove_by_document_id
# ---------------------------------------------------------------------------


def test_remove_calls_delete_document() -> None:
    client, provider = _provider()
    provider.remove("doc_x_chunk_0000")
    client.index().delete_document.assert_called_once_with("doc_x_chunk_0000")


def test_remove_by_document_id_uses_filter_delete() -> None:
    client, provider = _provider()
    provider.remove_by_document_id("doc-abc")
    client.index().delete_documents_by_filter.assert_called_once()
    filter_arg = client.index().delete_documents_by_filter.call_args[0][0]
    assert "doc-abc" in filter_arg
    assert "document_id" in filter_arg


def test_remove_by_document_id_escapes_value() -> None:
    """A document_id containing a quote/backslash must be backslash-escaped
    in the filter expression.
    """
    client, provider = _provider()
    provider.remove_by_document_id('doc-"weird"')
    filter_arg = client.index().delete_documents_by_filter.call_args[0][0]
    assert filter_arg == 'document_id = "doc-\\"weird\\""'


# ---------------------------------------------------------------------------
# search — ACL short-circuit
# ---------------------------------------------------------------------------


def test_search_short_circuits_for_groupless_user() -> None:
    client, provider = _provider()
    response = provider.search(_query(), _no_group_user())

    client.index().search.assert_not_called()
    assert len(response.results) == 0


def test_search_queries_meilisearch_for_admin() -> None:
    client, provider = _provider()
    client.index.return_value.search.return_value = {
        "hits": [],
        "nbHits": 0,
        "estimatedTotalHits": 0,
        "processingTimeMs": 1,
    }
    provider.search(_query(), _admin())
    client.index().search.assert_called_once()


def test_search_queries_meilisearch_for_user_with_groups() -> None:
    client, provider = _provider()
    client.index.return_value.search.return_value = {
        "hits": [],
        "nbHits": 0,
        "estimatedTotalHits": 0,
        "processingTimeMs": 1,
    }
    provider.search(_query(), _user_with_groups(_G1))
    client.index().search.assert_called_once()


def test_search_includes_acl_filter_for_non_admin() -> None:
    client, provider = _provider()
    client.index.return_value.search.return_value = {
        "hits": [],
        "nbHits": 0,
        "estimatedTotalHits": 0,
        "processingTimeMs": 1,
    }
    provider.search(_query(), _user_with_groups(_G1))
    _, kwargs = client.index().search.call_args
    params = client.index().search.call_args[0][1]
    assert "filter" in params
    assert _G1 in params["filter"]


def test_search_no_filter_for_admin() -> None:
    client, provider = _provider()
    client.index.return_value.search.return_value = {
        "hits": [],
        "nbHits": 0,
        "estimatedTotalHits": 0,
        "processingTimeMs": 1,
    }
    provider.search(_query(), _admin())
    params = client.index().search.call_args[0][1]
    assert "filter" not in params


def test_search_maps_hits_to_results() -> None:
    client, provider = _provider()
    client.index.return_value.search.return_value = {
        "hits": [
            {
                "id": "doc_doc1_chunk_0000",
                "document_id": "doc1",
                "chunk_index": 0,
                "title": "My Doc",
                "content": "some text",
                "position": {"chunk_index": 0},
                "metadata": {"source": "upload"},
                "_rankingScore": 0.9,
            }
        ],
        "nbHits": 1,
        "estimatedTotalHits": 1,
        "processingTimeMs": 5,
    }
    response = provider.search(_query(), _admin())
    assert len(response.results) == 1
    assert response.results[0].document_id == "doc1"
    assert response.results[0].title == "My Doc"
    assert response.results[0].score == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# _build_user_filter
# ---------------------------------------------------------------------------


def test_build_user_filter_empty_returns_empty_string() -> None:
    assert _build_user_filter(DocumentSearchFilters()) == ""


def test_build_user_filter_single_field() -> None:
    f = DocumentSearchFilters(source=["upload"])
    result = _build_user_filter(f)
    assert 'metadata.source IN ["upload"]' in result


def test_build_user_filter_multiple_values() -> None:
    f = DocumentSearchFilters(source=["upload", "local"])
    result = _build_user_filter(f)
    assert '"upload"' in result
    assert '"local"' in result


def test_build_user_filter_date_gte() -> None:
    # 2024-01-01T00:00:00Z == 1704067200 epoch seconds. Meilisearch range
    # filters operate on numbers, so the bound is emitted against the numeric
    # _ts mirror field rather than the ISO string.
    f = DocumentSearchFilters(created_after="2024-01-01T00:00:00Z")
    result = _build_user_filter(f)
    assert "metadata.created_at_ts >= 1704067200" in result


def test_build_user_filter_date_before_bare_date_is_inclusive_of_whole_day() -> None:
    # A bare date upper bound covers the entire calendar day: midnight epoch
    # (1704067200) plus 86399 seconds == 1704153599 (23:59:59 on 2024-01-01).
    f = DocumentSearchFilters(created_before="2024-01-01")
    result = _build_user_filter(f)
    assert "metadata.created_at_ts <= 1704153599" in result


def test_build_user_filter_date_before_explicit_datetime_exact() -> None:
    f = DocumentSearchFilters(created_before="2024-01-01T00:00:00Z")
    result = _build_user_filter(f)
    assert "metadata.created_at_ts <= 1704067200" in result


def test_build_user_filter_invalid_date_ignored() -> None:
    f = DocumentSearchFilters(created_after="not-a-date")
    assert _build_user_filter(f) == ""


def test_chunk_metadata_derives_epoch_timestamps() -> None:
    meta = ChunkMetadata(created_at="2024-01-01T00:00:00Z", updated_at="2024-01-01")
    assert meta.created_at_ts == 1704067200
    assert meta.updated_at_ts == 1704067200
    # No imported_at provided -> no derived epoch.
    assert meta.imported_at_ts is None


def test_chunk_metadata_invalid_timestamp_leaves_epoch_none() -> None:
    meta = ChunkMetadata(created_at="not-a-date")
    assert meta.created_at_ts is None


def test_chunk_metadata_explicit_epoch_not_overwritten() -> None:
    meta = ChunkMetadata(created_at="2024-01-01T00:00:00Z", created_at_ts=999)
    assert meta.created_at_ts == 999


def test_build_user_filter_multiple_fields_joined_with_and() -> None:
    f = DocumentSearchFilters(source=["upload"], language=["he"])
    result = _build_user_filter(f)
    assert " AND " in result


# ---------------------------------------------------------------------------
# swap_indexes / health_check
# ---------------------------------------------------------------------------


def test_swap_indexes_calls_client() -> None:
    client, provider = _provider()
    provider.swap_indexes()
    client.swap_indexes.assert_called_once_with([{"indexes": [INDEX_NAME, SHADOW_INDEX_NAME]}])


def test_health_check_returns_ok_true_on_success() -> None:
    client, provider = _provider()
    result = provider.health_check()
    assert result["ok"] is True
    assert "latency_ms" in result


def test_health_check_returns_ok_false_on_exception() -> None:
    client, provider = _provider()
    client.health.side_effect = ConnectionError("unreachable")
    result = provider.health_check()
    assert result["ok"] is False
    assert result["error"] is not None


# ---------------------------------------------------------------------------
# search_rag — source_ids filter
# ---------------------------------------------------------------------------


def _search_rag_hit(doc_id: str = "doc-1", source_id: str | None = None) -> dict:
    meta: dict = {"language": "en"}
    if source_id is not None:
        meta["source_id"] = source_id
    return {
        "id": f"doc_{doc_id}_chunk_0000",
        "document_id": doc_id,
        "chunk_index": 0,
        "title": "Title",
        "content": "hello",
        "heading": None,
        "position": {"chunk_index": 0},
        "metadata": meta,
        "_rankingScore": 0.9,
    }


def test_search_rag_passes_source_ids_filter() -> None:
    client, provider = _provider()
    client.index.return_value.search.return_value = {
        "hits": [
            _search_rag_hit("doc-1", source_id="src-a"),
            _search_rag_hit("doc-2", source_id="src-b"),
        ],
        "nbHits": 2,
        "estimatedTotalHits": 2,
        "processingTimeMs": 1,
    }
    provider.search_rag(
        text="hello",
        group_ids=["g1"],
        source_ids=["src-a"],
    )
    call_args = client.index().search.call_args
    params = call_args[0][1]
    assert "filter" in params
    assert 'metadata.source_id IN ["src-a"]' in params["filter"]


def test_search_rag_source_ids_filter_does_not_replace_acl_filter() -> None:
    """source_ids filter must be ANDed with ACL filter, not replace it."""
    client, provider = _provider()
    client.index.return_value.search.return_value = {
        "hits": [],
        "nbHits": 0,
        "estimatedTotalHits": 0,
        "processingTimeMs": 1,
    }
    provider.search_rag(
        text="hello",
        group_ids=["g1"],
        source_ids=["src-a"],
    )
    params = client.index().search.call_args[0][1]
    assert "allowed_group_ids" in params["filter"]
    assert 'metadata.source_id IN ["src-a"]' in params["filter"]


def test_search_rag_source_ids_maps_source_id_in_metadata() -> None:
    client, provider = _provider()
    client.index.return_value.search.return_value = {
        "hits": [_search_rag_hit("doc-1", source_id="src-a")],
        "nbHits": 1,
        "estimatedTotalHits": 1,
        "processingTimeMs": 1,
    }
    results = provider.search_rag(
        text="hello",
        group_ids=["g1"],
        source_ids=["src-a"],
    )
    assert len(results) == 1
    assert results[0].metadata.get("source_id") == "src-a"


def test_search_rag_metadata_passes_source_ids_filter() -> None:
    client, provider = _provider()
    client.index.return_value.search.return_value = {
        "hits": [_search_rag_hit("doc-1", source_id="src-a")],
        "nbHits": 1,
        "estimatedTotalHits": 1,
        "processingTimeMs": 1,
    }
    provider.search_rag_metadata(
        text="hello",
        group_ids=["g1"],
        source_ids=["src-a"],
    )
    call_args = client.index().search.call_args
    assert 'metadata.source_id IN ["src-a"]' in call_args[0][1]["filter"]


def test_search_rag_translated_passes_source_ids_filter() -> None:
    client, provider = _provider()
    client.index.return_value.search.return_value = {
        "hits": [_search_rag_hit("doc-1", source_id="src-a")],
        "nbHits": 1,
        "estimatedTotalHits": 1,
        "processingTimeMs": 1,
    }
    provider.search_rag_translated(
        text="hello",
        group_ids=["g1"],
        source_ids=["src-a"],
    )
    call_args = client.index().search.call_args
    assert 'metadata.source_id IN ["src-a"]' in call_args[0][1]["filter"]


def test_search_rag_source_ids_escapes_value() -> None:
    """A source_id containing a quote/backslash must be backslash-escaped."""
    client, provider = _provider()
    client.index.return_value.search.return_value = {
        "hits": [],
        "nbHits": 0,
        "estimatedTotalHits": 0,
        "processingTimeMs": 1,
    }
    provider.search_rag(
        text="hello",
        group_ids=["g1"],
        source_ids=['src-"x"'],
    )
    params = client.index().search.call_args[0][1]
    assert 'metadata.source_id IN ["src-\\"x\\""]' in params["filter"]


# ---------------------------------------------------------------------------
# _apply_scope_to_bm25 — source scope post-filter
# ---------------------------------------------------------------------------


def test_apply_scope_to_bm25_source_included() -> None:
    from services.rag.service import RagService

    results = [
        SearchResult(document_id="d1", score=0.9, metadata={"source_id": "src-a"}),
        SearchResult(document_id="d2", score=0.8, metadata={"source_id": "src-b"}),
        SearchResult(document_id="d3", score=0.7, metadata={"source_id": "src-a"}),
    ]
    from services.chat.models import ChatScope

    scope = ChatScope(scope_type="source", scope_ids=["src-a"])
    filtered = RagService._apply_scope_to_bm25(results, scope)
    assert len(filtered) == 2
    assert filtered[0].document_id == "d1"
    assert filtered[1].document_id == "d3"


def test_apply_scope_to_bm25_source_excludes_missing_source_id() -> None:
    """Stale records without source_id must be excluded for source scope."""
    from services.rag.service import RagService

    results = [
        SearchResult(document_id="d1", score=0.9, metadata={"source_id": "src-a"}),
        SearchResult(document_id="d2", score=0.8, metadata={"source_id": None}),
        SearchResult(document_id="d3", score=0.7, metadata={}),
    ]
    from services.chat.models import ChatScope

    scope = ChatScope(scope_type="source", scope_ids=["src-a"])
    filtered = RagService._apply_scope_to_bm25(results, scope)
    assert len(filtered) == 1
    assert filtered[0].document_id == "d1"


def test_apply_scope_to_bm25_source_excludes_unmatched() -> None:
    from services.rag.service import RagService

    results = [
        SearchResult(document_id="d1", score=0.9, metadata={"source_id": "src-a"}),
    ]
    from services.chat.models import ChatScope

    scope = ChatScope(scope_type="source", scope_ids=["src-b"])
    filtered = RagService._apply_scope_to_bm25(results, scope)
    assert len(filtered) == 0


def test_apply_scope_to_bm25_keeps_all_accessible_accessible() -> None:
    """all_accessible_documents scope must not filter BM25 results."""
    from services.rag.service import RagService

    results = [
        SearchResult(document_id="d1", score=0.9, metadata={}),
        SearchResult(document_id="d2", score=0.8, metadata={}),
    ]
    from services.chat.models import ChatScope

    scope = ChatScope(scope_type="all_accessible_documents", scope_ids=[])
    filtered = RagService._apply_scope_to_bm25(results, scope)
    assert len(filtered) == 2
