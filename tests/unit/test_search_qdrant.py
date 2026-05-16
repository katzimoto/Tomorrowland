from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.search.qdrant import QdrantSearchClient

COLLECTION_NAME = "tomorrowland_chunks_384"


def test_upsert_chunks_success() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    client._client = mock_qdrant

    chunks = [
        {
            "chunk_id": "doc-1-0",
            "doc_id": "doc-1",
            "group_id": "group-1",
            "chunk_index": 0,
            "text": "hello",
            "vector": [0.1] * 384,
        },
        {
            "chunk_id": "doc-1-1",
            "doc_id": "doc-1",
            "group_id": "group-1",
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
    assert points[0].id == "doc-1-0"
    assert points[0].payload["doc_id"] == "doc-1"


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

    chunks = [
        {
            "chunk_id": "doc-1-0",
            "doc_id": "doc-1",
            "group_id": "group-1",
            "chunk_index": 0,
            "text": "hello",
            "vector": [0.1] * 768,
        },
    ]

    with pytest.raises(ValueError, match="Vector dimension mismatch"):
        client.upsert_chunks(chunks)

    mock_qdrant.upsert.assert_not_called()


def test_search_vector() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = [
        MagicMock(score=0.95, payload={"doc_id": "doc-1", "text": "hello"}),
        MagicMock(score=0.85, payload={"doc_id": "doc-1", "text": "world"}),
    ]
    client._client = mock_qdrant

    results = client.search(vector=[0.1] * 384, group_ids=["group-1"], limit=10)

    assert len(results) == 2
    assert results[0].doc_id == "doc-1"
    assert results[0].score == 0.95
    assert results[0].chunk_text == "hello"


def test_search_dimension_mismatch() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)

    with pytest.raises(ValueError, match="Vector dimension mismatch"):
        client.search(vector=[0.1] * 768, group_ids=["group-1"], limit=10)


def test_search_without_group_ids_returns_empty() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = []
    client._client = mock_qdrant

    results = client.search(vector=[0.1] * 384, group_ids=[])
    assert results == []


def test_search_respects_limit() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    mock_qdrant.query_points.return_value.points = []
    client._client = mock_qdrant

    client.search(vector=[0.1] * 384, group_ids=["group-1"], limit=25)

    assert mock_qdrant.query_points.call_args.kwargs["limit"] == 25


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


def test_collection_name_includes_dimension() -> None:
    client_384 = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    client_768 = QdrantSearchClient(url="http://localhost:6333", dimension=768)

    assert client_384.collection_name == "tomorrowland_chunks_384"
    assert client_768.collection_name == "tomorrowland_chunks_768"


def test_client_close() -> None:
    client = QdrantSearchClient(url="http://localhost:6333", dimension=384)
    mock_qdrant = MagicMock()
    client._client = mock_qdrant

    client.close()

    mock_qdrant.close.assert_called_once()
