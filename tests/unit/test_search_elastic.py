from __future__ import annotations

from unittest.mock import MagicMock

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


def test_search_without_group_ids_sends_zero_result_filter() -> None:
    client = ElasticsearchSearchClient(hosts=["http://localhost:9200"])
    mock_es = MagicMock()
    mock_es.search.return_value = {"hits": {"hits": []}}
    client._client = mock_es

    results = client.search("hello", group_ids=[])

    assert results == []
    query = mock_es.search.call_args.kwargs["query"]
    assert query["bool"]["filter"]["terms"]["allowed_group_ids"] == []


def test_admin_search_omits_acl_filter() -> None:
    client = ElasticsearchSearchClient(hosts=["http://localhost:9200"])
    mock_es = MagicMock()
    mock_es.search.return_value = {"hits": {"hits": []}}
    client._client = mock_es

    client.search("hello", group_ids=[], is_admin=True)

    query = mock_es.search.call_args.kwargs["query"]
    assert "filter" not in query["bool"]


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
    should_clauses = query["bool"]["should"]
    assert len(should_clauses) == 2
    full_text_clause = should_clauses[0]["multi_match"]
    assert full_text_clause["query"] == "hello world"
    assert "title^3" in full_text_clause["fields"]
    assert "content_english^2" in full_text_clause["fields"]
    assert "filename^3" in full_text_clause["fields"]
    assert "content_original^2" in full_text_clause["fields"]
    assert "path^2" in full_text_clause["fields"]
    assert "summary" in full_text_clause["fields"]
    assert "tags" in full_text_clause["fields"]


def test_search_includes_autocomplete_fields() -> None:
    """Partial-word matching: the query must include .autocomplete subfields."""
    client = ElasticsearchSearchClient(hosts=["http://localhost:9200"])
    mock_es = MagicMock()
    mock_es.search.return_value = {"hits": {"hits": []}}
    client._client = mock_es

    client.search("trans", group_ids=["group-1"])

    query = mock_es.search.call_args.kwargs["query"]
    should_clauses = query["bool"]["should"]
    autocomplete_fields = should_clauses[1]["multi_match"]["fields"]
    assert any("autocomplete" in f for f in autocomplete_fields)
    assert query["bool"]["minimum_should_match"] == 1


def test_search_prefix_query_covers_all_text_fields() -> None:
    """All searchable text fields must have an autocomplete variant in the query."""
    client = ElasticsearchSearchClient(hosts=["http://localhost:9200"])
    mock_es = MagicMock()
    mock_es.search.return_value = {"hits": {"hits": []}}
    client._client = mock_es

    client.search("transl", group_ids=["group-1"])

    query = mock_es.search.call_args.kwargs["query"]
    autocomplete_clause = query["bool"]["should"][1]["multi_match"]
    field_names = [f.split("^")[0] for f in autocomplete_clause["fields"]]
    assert "title.autocomplete" in field_names
    assert "content_english.autocomplete" in field_names
    assert "filename.autocomplete" in field_names
    assert "content_original.autocomplete" in field_names
    assert "path.autocomplete" in field_names
    assert "summary.autocomplete" in field_names


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
    assert "settings" in call_args.kwargs


def test_create_index_has_edge_ngram_analyzer() -> None:
    """Index settings must define the edge_ngram filter and autocomplete analyzers."""
    client = ElasticsearchSearchClient(hosts=["http://localhost:9200"])
    mock_es = MagicMock()
    mock_es.indices.exists.return_value = False
    client._client = mock_es

    client.create_index_if_not_exists()

    settings = mock_es.indices.create.call_args.kwargs["settings"]
    filters = settings["analysis"]["filter"]
    analyzers = settings["analysis"]["analyzer"]
    assert filters["autocomplete_ngram"]["type"] == "edge_ngram"
    assert "autocomplete_index" in analyzers
    assert "autocomplete_search" in analyzers
    assert "autocomplete_ngram" in analyzers["autocomplete_index"]["filter"]


def test_create_index_edge_ngram_min_gram_is_one() -> None:
    """The edge_ngram filter must use min_gram=1 for single-character prefix search."""
    client = ElasticsearchSearchClient(hosts=["http://localhost:9200"])
    mock_es = MagicMock()
    mock_es.indices.exists.return_value = False
    client._client = mock_es

    client.create_index_if_not_exists()

    settings = mock_es.indices.create.call_args.kwargs["settings"]
    ngram = settings["analysis"]["filter"]["autocomplete_ngram"]
    assert ngram["min_gram"] == 1


def test_create_index_has_autocomplete_subfields() -> None:
    """Searchable text fields must have an .autocomplete multi-field in the mapping."""
    client = ElasticsearchSearchClient(hosts=["http://localhost:9200"])
    mock_es = MagicMock()
    mock_es.indices.exists.return_value = False
    client._client = mock_es

    client.create_index_if_not_exists()

    props = mock_es.indices.create.call_args.kwargs["mappings"]["properties"]
    for field in ("title", "content_english", "summary", "path", "filename", "content_original"):
        assert "autocomplete" in props[field]["fields"], f"{field} missing .autocomplete subfield"
        subfield = props[field]["fields"]["autocomplete"]
        assert subfield["analyzer"] == "autocomplete_index"
        assert subfield["search_analyzer"] == "autocomplete_search"


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
