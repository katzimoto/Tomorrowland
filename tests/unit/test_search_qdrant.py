from __future__ import annotations

import uuid
from unittest.mock import MagicMock, call

import pytest

from services.search.qdrant import QdrantSearchClient

COLLECTION_NAME = "tomorrowland_chunks_384"

_MINIMAL_CHUNK = {
    "chunk_id": "doc-1-0",
    "document_id": "doc-1",
    "group_id": ["group-1"],
    "chunk_index": 0,
    "text": "hello",
    "vector": [0.1] * 384,
}


def test_upsert_chunks_success() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    client._client = mock_qdrant

    chunks = [
        {
            **_MINIMAL_CHUNK,
            "chunk_id": "doc-1-0",
            "chunk_index": 0,
            "text": "hello",
            "vector": [0.1] * 384,
        },
        {
            **_MINIMAL_CHUNK,
            "chunk_id": "doc-1-1",
            "chunk_index": 1,
            "text": "world",
            "vector": [0.2] * 384,
        },
    ]

    client.upsert_chunks(chunks)

    mock_qdrant.upsert.assert_called_once()
    call_args = mock_qdrant.upsert.call_args
    assert call_args.kwargs["collection_name"] == COLLECTION_NAME
    points = call_args.kwargs["points"]
    assert len(points) == 2
    assert points[0].id == str(uuid.uuid5(uuid.NAMESPACE_DNS, "doc-1-0"))
    assert points[0].payload["document_id"] == "doc-1"
    assert points[0].payload["chunk_id"] == "doc-1-0"


def test_upsert_chunks_empty_list() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    client._client = mock_qdrant

    client.upsert_chunks([])

    mock_qdrant.upsert.assert_not_called()


def test_upsert_chunks_dimension_mismatch() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    client._client = mock_qdrant

    chunks = [{**_MINIMAL_CHUNK, "vector": [0.1] * 768}]

    with pytest.raises(ValueError, match="Vector dimension mismatch"):
        client.upsert_chunks(chunks)

    mock_qdrant.upsert.assert_not_called()


def test_upsert_chunks_stores_optional_metadata() -> None:
    """source_id, title, source_language, page_number, section_heading are stored."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    client._client = mock_qdrant

    chunk = {
        **_MINIMAL_CHUNK,
        "source_id": "src-42",
        "title": "My Document",
        "source_language": "fr",
        "page_number": 3,
        "section_heading": "Introduction",
    }
    client.upsert_chunks([chunk])

    points = mock_qdrant.upsert.call_args.kwargs["points"]
    payload = points[0].payload
    assert payload["source_id"] == "src-42"
    assert payload["title"] == "My Document"
    assert payload["source_language"] == "fr"
    assert payload["page_number"] == 3
    assert payload["section_heading"] == "Introduction"


def test_upsert_chunks_without_optional_metadata_omits_keys() -> None:
    """Keys absent from the chunk dict are not added to the payload."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    client._client = mock_qdrant

    client.upsert_chunks([_MINIMAL_CHUNK])

    payload = mock_qdrant.upsert.call_args.kwargs["points"][0].payload
    assert "source_id" not in payload
    assert "title" not in payload
    assert "source_language" not in payload


def test_upsert_chunks_delete_existing_calls_delete_first() -> None:
    """delete_existing=True should delete old chunks before upserting."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    client._client = mock_qdrant

    client.upsert_chunks([_MINIMAL_CHUNK], delete_existing=True)

    # delete must be called before upsert
    assert mock_qdrant.delete.called
    assert mock_qdrant.upsert.called
    delete_idx = (
        [
            i
            for i, c in enumerate(mock_qdrant.mock_calls)
            if c
            == call.delete(
                collection_name=COLLECTION_NAME,
                points_selector=mock_qdrant.delete.call_args.kwargs["points_selector"],
            )
        ][0]
        if mock_qdrant.delete.called
        else -1
    )
    upsert_idx = next(i for i, c in enumerate(mock_qdrant.mock_calls) if "upsert" in str(c))
    assert delete_idx < upsert_idx


def test_search_vector() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = [
        MagicMock(
            id="doc-1-0",
            score=0.95,
            payload={"document_id": "doc-1", "chunk_id": "doc-1-0", "text": "hello"},
        ),
        MagicMock(
            id="doc-1-1",
            score=0.85,
            payload={"document_id": "doc-1", "chunk_id": "doc-1-1", "text": "world"},
        ),
    ]
    client._client = mock_qdrant

    results = client.search(vector=[0.1] * 384, group_ids=["group-1"], limit=10)

    assert len(results) == 2
    assert results[0].document_id == "doc-1"
    assert results[0].score == 0.95
    assert results[0].chunk_text == "hello"
    assert results[0].metadata is not None
    assert results[0].metadata["chunk_id"] == "doc-1-0"


def test_search_dimension_mismatch() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)

    with pytest.raises(ValueError, match="Vector dimension mismatch"):
        client.search(vector=[0.1] * 768, group_ids=["group-1"], limit=10)


def test_search_without_group_ids_returns_empty() -> None:
    """Empty group_ids without allow_all must return empty — no data exposure."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    client._client = mock_qdrant

    results = client.search(vector=[0.1] * 384, group_ids=[])

    assert results == []
    mock_qdrant.query_points.assert_not_called()


def test_search_without_group_ids_allow_all_queries_qdrant() -> None:
    """allow_all=True (admin bypass) should send the query without a group filter."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = []
    client._client = mock_qdrant

    client.search(vector=[0.1] * 384, group_ids=[], allow_all=True)

    mock_qdrant.query_points.assert_called_once()
    # No filter at all when allow_all and no document_id
    assert mock_qdrant.query_points.call_args.kwargs["query_filter"] is None


def test_search_respects_limit() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = []
    client._client = mock_qdrant

    client.search(vector=[0.1] * 384, group_ids=["group-1"], limit=25)

    assert mock_qdrant.query_points.call_args.kwargs["limit"] == 25


def test_search_permission_filter_applied() -> None:
    """group_id filter must appear in the Qdrant query when group_ids is set."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = []
    client._client = mock_qdrant

    client.search(vector=[0.1] * 384, group_ids=["grp-a", "grp-b"])

    query_filter = mock_qdrant.query_points.call_args.kwargs["query_filter"]
    assert query_filter is not None
    condition_keys = [c.key for c in query_filter.must]
    assert "group_id" in condition_keys


def test_delete_by_doc_id() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    client._client = mock_qdrant

    client.delete_by_doc_id("doc-1")

    mock_qdrant.delete.assert_called_once()
    call_args = mock_qdrant.delete.call_args
    assert call_args.kwargs["collection_name"] == COLLECTION_NAME


def test_create_collection_if_not_exists() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.collection_exists.return_value = False
    client._client = mock_qdrant

    client.create_collection_if_not_exists()

    mock_qdrant.create_collection.assert_called_once()
    call_args = mock_qdrant.create_collection.call_args
    assert call_args.kwargs["collection_name"] == COLLECTION_NAME
    assert call_args.kwargs["vectors_config"].size == 384


def test_create_collection_already_exists() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.collection_exists.return_value = True
    client._client = mock_qdrant

    client.create_collection_if_not_exists()

    mock_qdrant.create_collection.assert_not_called()


def test_qdrant_client_dimension_aligns_with_encoder() -> None:
    """QdrantSearchClient built from encoder.dimension uses the matching collection."""
    from services.search.encoder import DeterministicTestEncoder

    encoder = DeterministicTestEncoder()
    client = QdrantSearchClient(url="http://localhost:6333", dimension=encoder.dimension)

    assert client.dimension == encoder.dimension
    assert client.collection_name == f"tomorrowland_chunks_{encoder.dimension}"


def test_collection_name_includes_dimension() -> None:
    client_384 = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    client_768 = QdrantSearchClient(url="http://localhost:6333", dimension=768)

    assert client_384.collection_name == "tomorrowland_chunks_384"
    assert client_768.collection_name == "tomorrowland_chunks_768"


def test_search_with_document_id_filter() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = []
    client._client = mock_qdrant

    client.search(vector=[0.1] * 384, group_ids=["group-1"], document_id="doc-42")

    call_kwargs = mock_qdrant.query_points.call_args.kwargs
    query_filter = call_kwargs["query_filter"]
    assert query_filter is not None
    condition_keys = [c.key for c in query_filter.must]
    assert "group_id" in condition_keys
    assert "document_id" in condition_keys


def test_search_without_group_ids_but_with_document_id() -> None:
    """document_id filter alone is not enough — still need allow_all or group_ids."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = []
    client._client = mock_qdrant

    results = client.search(vector=[0.1] * 384, group_ids=[], document_id="doc-42")

    # No group_ids and no allow_all → safe empty return
    assert results == []
    mock_qdrant.query_points.assert_not_called()


def test_search_admin_with_document_id_filter() -> None:
    """Admin (allow_all=True) + document_id should filter only by document_id."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = []
    client._client = mock_qdrant

    client.search(vector=[0.1] * 384, group_ids=[], document_id="doc-42", allow_all=True)

    call_kwargs = mock_qdrant.query_points.call_args.kwargs
    query_filter = call_kwargs["query_filter"]
    assert query_filter is not None
    condition_keys = [c.key for c in query_filter.must]
    assert "group_id" not in condition_keys
    assert "document_id" in condition_keys


def test_upsert_chunks_calls_create_collection_before_upsert() -> None:
    """upsert_chunks must ensure the collection exists before any write."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.collection_exists.return_value = False
    client._client = mock_qdrant

    client.upsert_chunks([_MINIMAL_CHUNK])

    mock_qdrant.collection_exists.assert_called_once_with(collection_name=COLLECTION_NAME)
    mock_qdrant.create_collection.assert_called_once()
    mock_qdrant.upsert.assert_called_once()


def test_upsert_chunks_delete_existing_ensures_collection_before_delete() -> None:
    """With delete_existing=True, create_collection_if_not_exists must run before delete."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.collection_exists.return_value = True
    client._client = mock_qdrant

    client.upsert_chunks([_MINIMAL_CHUNK], delete_existing=True)

    mock_qdrant.collection_exists.assert_called()
    # collection_exists is called by create_collection_if_not_exists first, then by delete_by_doc_id
    collection_exists_idx = next(
        i for i, c in enumerate(mock_qdrant.mock_calls) if "collection_exists" in str(c)
    )
    delete_idx = next(i for i, c in enumerate(mock_qdrant.mock_calls) if "delete" in str(c))
    assert collection_exists_idx < delete_idx


def test_delete_by_doc_id_is_noop_when_collection_absent() -> None:
    """delete_by_doc_id must not call delete when the collection does not exist."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.collection_exists.return_value = False
    client._client = mock_qdrant

    client.delete_by_doc_id("doc-missing")

    mock_qdrant.delete.assert_not_called()


def test_client_close() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    client._client = mock_qdrant

    client.close()

    mock_qdrant.close.assert_called_once()


def test_search_metadata_includes_extra_payload_fields() -> None:
    """Payload fields source_id, title, source_language, chunk_index appear in result metadata."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = [
        MagicMock(
            id="doc-1-0",
            score=0.9,
            payload={
                "document_id": "doc-1",
                "chunk_id": "doc-1-0",
                "chunk_index": 3,
                "text": "hello",
                "source_id": "src-7",
                "title": "Annual Report",
                "source_language": "de",
            },
        ),
    ]
    client._client = mock_qdrant

    results = client.search(vector=[0.1] * 384, group_ids=["g1"])

    assert results[0].metadata is not None
    assert results[0].metadata["source_id"] == "src-7"
    assert results[0].metadata["title"] == "Annual Report"
    assert results[0].metadata["source_language"] == "de"
    assert results[0].metadata["chunk_index"] == 3


def test_list_chunks_by_document_returns_sorted_passages() -> None:
    """Scroll-based listing returns chunks sorted by chunk_index."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.collection_exists.return_value = True
    mock_qdrant.scroll.return_value = (
        [
            MagicMock(
                id="point-2",
                payload={
                    "document_id": "doc-1",
                    "chunk_id": "doc-1-1",
                    "chunk_index": 1,
                    "text": "second",
                    "group_id": ["g1"],
                },
            ),
            MagicMock(
                id="point-1",
                payload={
                    "document_id": "doc-1",
                    "chunk_id": "doc-1-0",
                    "chunk_index": 0,
                    "text": "first",
                    "group_id": ["g1"],
                },
            ),
        ],
        None,
    )
    client._client = mock_qdrant

    results = client.list_chunks_by_document(
        document_id="doc-1",
        group_ids=["g1"],
        limit=10,
        offset=0,
    )

    assert [r.chunk_text for r in results] == ["first", "second"]
    assert results[0].metadata is not None
    assert results[0].metadata["chunk_index"] == 0


def test_list_chunks_by_document_applies_group_filter() -> None:
    """Without admin bypass, listing chunks must include the group_id filter."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.collection_exists.return_value = True
    mock_qdrant.scroll.return_value = ([], None)
    client._client = mock_qdrant

    client.list_chunks_by_document(
        document_id="doc-1",
        group_ids=["g1", "g2"],
        limit=10,
    )

    scroll_filter = mock_qdrant.scroll.call_args.kwargs["scroll_filter"]
    condition_keys = [c.key for c in scroll_filter.must]
    assert "document_id" in condition_keys
    assert "group_id" in condition_keys


def test_list_chunks_by_document_admin_bypass_skips_group_filter() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.collection_exists.return_value = True
    mock_qdrant.scroll.return_value = ([], None)
    client._client = mock_qdrant

    client.list_chunks_by_document(
        document_id="doc-1",
        group_ids=[],
        allow_all=True,
    )

    scroll_filter = mock_qdrant.scroll.call_args.kwargs["scroll_filter"]
    condition_keys = [c.key for c in scroll_filter.must]
    assert "document_id" in condition_keys
    assert "group_id" not in condition_keys


def test_list_chunks_by_document_no_groups_returns_empty() -> None:
    """Empty groups + no admin bypass must short-circuit to empty results."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    client._client = mock_qdrant

    results = client.list_chunks_by_document(document_id="doc-1", group_ids=[])

    assert results == []
    mock_qdrant.scroll.assert_not_called()


def test_list_chunks_by_document_collection_missing_returns_empty() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.collection_exists.return_value = False
    client._client = mock_qdrant

    results = client.list_chunks_by_document(document_id="doc-1", group_ids=["g1"], allow_all=False)

    assert results == []
    mock_qdrant.scroll.assert_not_called()


def test_list_chunks_by_document_offset_pagination() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.collection_exists.return_value = True
    mock_qdrant.scroll.return_value = (
        [
            MagicMock(
                id=f"p-{i}",
                payload={
                    "document_id": "doc-1",
                    "chunk_id": f"doc-1-{i}",
                    "chunk_index": i,
                    "text": f"chunk-{i}",
                    "group_id": ["g1"],
                },
            )
            for i in range(5)
        ],
        None,
    )
    client._client = mock_qdrant

    results = client.list_chunks_by_document(
        document_id="doc-1",
        group_ids=["g1"],
        limit=2,
        offset=2,
    )

    assert [r.chunk_text for r in results] == ["chunk-2", "chunk-3"]


def test_search_metadata_includes_page_number_section_heading() -> None:
    """page_number and section_heading in Qdrant payload must appear in metadata."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = [
        MagicMock(
            id="doc-1-0",
            score=0.92,
            payload={
                "document_id": "doc-1",
                "chunk_id": "doc-1-0",
                "chunk_index": 0,
                "text": "some chunk text",
                "source_id": "src-7",
                "page_number": 5,
                "section_heading": "Results",
            },
        ),
    ]
    client._client = mock_qdrant

    results = client.search(vector=[0.1] * 384, group_ids=["g1"])

    assert results[0].metadata is not None
    assert results[0].metadata["page_number"] == 5
    assert results[0].metadata["section_heading"] == "Results"


def test_search_extra_conditions_appended_to_filter() -> None:
    """extra_conditions are merged into the must-filter alongside the group condition."""
    from qdrant_client.models import FieldCondition, MatchAny

    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = []
    client._client = mock_qdrant

    lang_cond = FieldCondition(key="source_language", match=MatchAny(any=["he"]))
    client.search(vector=[0.1] * 384, group_ids=["g1"], extra_conditions=[lang_cond])

    query_filter = mock_qdrant.query_points.call_args.kwargs["query_filter"]
    assert query_filter is not None
    condition_keys = [c.key for c in query_filter.must]
    assert "group_id" in condition_keys
    assert "source_language" in condition_keys


def test_search_extra_conditions_admin_bypass() -> None:
    """extra_conditions still apply even in admin (allow_all) mode."""
    from qdrant_client.models import FieldCondition, MatchAny

    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = []
    client._client = mock_qdrant

    lang_cond = FieldCondition(key="source_language", match=MatchAny(any=["en"]))
    client.search(
        vector=[0.1] * 384,
        group_ids=[],
        allow_all=True,
        extra_conditions=[lang_cond],
    )

    query_filter = mock_qdrant.query_points.call_args.kwargs["query_filter"]
    assert query_filter is not None
    condition_keys = [c.key for c in query_filter.must]
    assert "group_id" not in condition_keys
    assert "source_language" in condition_keys


def test_search_no_extra_conditions_no_change_to_existing_behavior() -> None:
    """Omitting extra_conditions leaves behavior unchanged."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = []
    client._client = mock_qdrant

    client.search(vector=[0.1] * 384, group_ids=["g1"])

    query_filter = mock_qdrant.query_points.call_args.kwargs["query_filter"]
    assert query_filter is not None
    condition_keys = [c.key for c in query_filter.must]
    assert condition_keys == ["group_id"]


def test_search_empty_extra_conditions_list_no_change() -> None:
    """Passing an empty extra_conditions list is identical to omitting it."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = []
    client._client = mock_qdrant

    client.search(vector=[0.1] * 384, group_ids=["g1"], extra_conditions=[])

    query_filter = mock_qdrant.query_points.call_args.kwargs["query_filter"]
    assert query_filter is not None
    condition_keys = [c.key for c in query_filter.must]
    assert condition_keys == ["group_id"]


# ── Language / text-lane metadata preservation (#763) ────────────────────────


def test_upsert_preserves_language_field() -> None:
    """language field passed in a chunk dict must be stored in the Qdrant payload."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    client._client = mock_qdrant

    chunk = {**_MINIMAL_CHUNK, "language": "he"}
    client.upsert_chunks([chunk])

    payload = mock_qdrant.upsert.call_args.kwargs["points"][0].payload
    assert payload["language"] == "he"


def test_upsert_preserves_text_lane_original() -> None:
    """text_lane='original' must be stored in the Qdrant payload."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    client._client = mock_qdrant

    chunk = {**_MINIMAL_CHUNK, "text_lane": "original"}
    client.upsert_chunks([chunk])

    payload = mock_qdrant.upsert.call_args.kwargs["points"][0].payload
    assert payload["text_lane"] == "original"


def test_upsert_preserves_text_lane_translated() -> None:
    """text_lane='translated' must be stored in the Qdrant payload."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    client._client = mock_qdrant

    chunk = {**_MINIMAL_CHUNK, "text_lane": "translated"}
    client.upsert_chunks([chunk])

    payload = mock_qdrant.upsert.call_args.kwargs["points"][0].payload
    assert payload["text_lane"] == "translated"


def test_upsert_preserves_translated_from() -> None:
    """translated_from must be stored when present (source language of a translation)."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    client._client = mock_qdrant

    chunk = {**_MINIMAL_CHUNK, "language": "en", "text_lane": "translated", "translated_from": "he"}
    client.upsert_chunks([chunk])

    payload = mock_qdrant.upsert.call_args.kwargs["points"][0].payload
    assert payload["translated_from"] == "he"
    assert payload["language"] == "en"
    assert payload["text_lane"] == "translated"


def test_upsert_omits_language_text_lane_when_absent() -> None:
    """Chunks without language/text_lane must not add those keys to the payload."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    client._client = mock_qdrant

    client.upsert_chunks([_MINIMAL_CHUNK])

    payload = mock_qdrant.upsert.call_args.kwargs["points"][0].payload
    assert "language" not in payload
    assert "text_lane" not in payload
    assert "translated_from" not in payload


def test_search_result_includes_language_and_text_lane() -> None:
    """language and text_lane stored in Qdrant payload must appear in SearchResult.metadata."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = [
        MagicMock(
            id="doc-1-0",
            score=0.9,
            payload={
                "document_id": "doc-1",
                "chunk_id": "doc-1-orig-0",
                "chunk_index": 0,
                "text": "original text",
                "language": "he",
                "text_lane": "original",
            },
        ),
    ]
    client._client = mock_qdrant

    results = client.search(vector=[0.1] * 384, group_ids=["g1"])

    assert results[0].metadata is not None
    assert results[0].metadata["language"] == "he"
    assert results[0].metadata["text_lane"] == "original"


def test_search_result_includes_translated_from() -> None:
    """translated_from in Qdrant payload must surface in SearchResult.metadata."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = [
        MagicMock(
            id="doc-1-tr-0",
            score=0.88,
            payload={
                "document_id": "doc-1",
                "chunk_id": "doc-1-tr-0",
                "chunk_index": 0,
                "text": "translated text",
                "language": "en",
                "text_lane": "translated",
                "translated_from": "he",
            },
        ),
    ]
    client._client = mock_qdrant

    results = client.search(vector=[0.1] * 384, group_ids=["g1"])

    assert results[0].metadata is not None
    assert results[0].metadata["language"] == "en"
    assert results[0].metadata["text_lane"] == "translated"
    assert results[0].metadata["translated_from"] == "he"


def test_translated_hit_distinguishable_from_original() -> None:
    """Search must return both original and translated hits with distinct text_lane values."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = [
        MagicMock(
            id="doc-1-orig-0",
            score=0.95,
            payload={
                "document_id": "doc-1",
                "chunk_id": "doc-1-orig-0",
                "chunk_index": 0,
                "text": "original text in Hebrew",
                "language": "he",
                "text_lane": "original",
            },
        ),
        MagicMock(
            id="doc-1-tr-0",
            score=0.90,
            payload={
                "document_id": "doc-1",
                "chunk_id": "doc-1-tr-0",
                "chunk_index": 0,
                "text": "translated text in English",
                "language": "en",
                "text_lane": "translated",
                "translated_from": "he",
            },
        ),
    ]
    client._client = mock_qdrant

    results = client.search(vector=[0.1] * 384, group_ids=["g1"])

    lanes = {(r.metadata or {}).get("text_lane") for r in results}
    assert "original" in lanes
    assert "translated" in lanes

    orig = next(r for r in results if (r.metadata or {}).get("text_lane") == "original")
    trans = next(r for r in results if (r.metadata or {}).get("text_lane") == "translated")
    assert orig.metadata["language"] == "he"
    assert trans.metadata["language"] == "en"
    assert trans.metadata["translated_from"] == "he"


def test_search_missing_language_fields_degrade_gracefully() -> None:
    """Legacy payloads without language/text_lane must not break search or raise."""
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = [
        MagicMock(
            id="old-doc-0",
            score=0.80,
            payload={
                "document_id": "old-doc",
                "chunk_id": "old-doc-0",
                "chunk_index": 0,
                "text": "legacy chunk with no language metadata",
            },
        ),
    ]
    client._client = mock_qdrant

    results = client.search(vector=[0.1] * 384, group_ids=["g1"])

    assert len(results) == 1
    assert results[0].metadata is not None
    assert "language" not in results[0].metadata
    assert "text_lane" not in results[0].metadata
    assert "translated_from" not in results[0].metadata
