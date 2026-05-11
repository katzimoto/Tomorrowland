from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.search.elastic import ElasticsearchSearchClient

INDEX_NAME = "tomorrowland_documents"


def test_index_document_success() -> None:
    client = ElasticsearchSearchClient(hosts=["http://localhost:9200"])
    mock_es = MagicMock()
    client._client = mock_es

    doc = {
        "doc_id": "doc-1",
        "content_english": "hello world",
        "title": "Test Doc",
        "summary": "A summary",
        "tags": ["tag1", "tag2"],
        "metadata": {"author": "Alice"},
        "allowed_group_ids": ["group-1"],
    }

    client.index_document("doc-1", doc)

    mock_es.index.assert_called_once()
    call_args = mock_es.index.call_args
    assert call_args.kwargs["index"] == INDEX_NAME
    assert call_args.kwargs["id"] == "doc-1"
    assert call_args.kwargs["document"] == doc


def test_search_bm25() -> None:
    client = ElasticsearchSearchClient(hosts=["http://localhost:9200"])
    mock_es = MagicMock()
    mock_es.search.return_value = {
        "hits": {
            "hits": [
                {"_id": "doc-1", "_score": 1.5, "_source": {"title": "Doc 1"}},
                {"_id": "doc-2", "_score": 1.2, "_source": {"title": "Doc 2"}},
            ]
        }
    }
    client._client = mock_es

    results = client.search("hello world", group_ids=["group-1"], size=10)

    assert len(results) == 2
    assert results[0].doc_id == "doc-1"
    assert results[0].score == 1.5
    assert results[1].doc_id == "doc-2"


def test_search_no_group_ids_raises() -> None:
    client = ElasticsearchSearchClient(hosts=["http://localhost:9200"])

    with pytest.raises(ValueError, match="group_ids must not be empty"):
        client.search("hello", group_ids=[])


def test_search_respects_size() -> None:
    client = ElasticsearchSearchClient(hosts=["http://localhost:9200"])
    mock_es = MagicMock()
    mock_es.search.return_value = {"hits": {"hits": []}}
    client._client = mock_es

    client.search("hello", group_ids=["group-1"], size=25)

    assert mock_es.search.call_args.kwargs["size"] == 25


def test_search_uses_multi_match_query() -> None:
    client = ElasticsearchSearchClient(hosts=["http://localhost:9200"])
    mock_es = MagicMock()
    mock_es.search.return_value = {"hits": {"hits": []}}
    client._client = mock_es

    client.search("hello world", group_ids=["group-1"])

    query = mock_es.search.call_args.kwargs["query"]
    assert "multi_match" in query["bool"]["must"]
    assert query["bool"]["must"]["multi_match"]["query"] == "hello world"


def test_search_filters_by_group_ids() -> None:
    client = ElasticsearchSearchClient(hosts=["http://localhost:9200"])
    mock_es = MagicMock()
    mock_es.search.return_value = {"hits": {"hits": []}}
    client._client = mock_es

    client.search("hello", group_ids=["group-1", "group-2"])

    query = mock_es.search.call_args.kwargs["query"]
    bool_query = query["bool"]
    assert bool_query["filter"]["terms"]["allowed_group_ids"] == ["group-1", "group-2"]


def test_delete_document() -> None:
    client = ElasticsearchSearchClient(hosts=["http://localhost:9200"])
    mock_es = MagicMock()
    client._client = mock_es

    client.delete_document("doc-1")

    mock_es.delete.assert_called_once_with(index=INDEX_NAME, id="doc-1")


def test_create_index_if_not_exists() -> None:
    client = ElasticsearchSearchClient(hosts=["http://localhost:9200"])
    mock_es = MagicMock()
    mock_es.indices.exists.return_value = False
    client._client = mock_es

    client.create_index_if_not_exists()

    mock_es.indices.create.assert_called_once()
    call_args = mock_es.indices.create.call_args
    assert call_args.kwargs["index"] == INDEX_NAME
    assert "mappings" in call_args.kwargs


def test_create_index_already_exists() -> None:
    client = ElasticsearchSearchClient(hosts=["http://localhost:9200"])
    mock_es = MagicMock()
    mock_es.indices.exists.return_value = True
    client._client = mock_es

    client.create_index_if_not_exists()

    mock_es.indices.create.assert_not_called()


def test_client_close() -> None:
    client = ElasticsearchSearchClient(hosts=["http://localhost:9200"])
    mock_es = MagicMock()
    client._client = mock_es

    client.close()

    mock_es.close.assert_called_once()
