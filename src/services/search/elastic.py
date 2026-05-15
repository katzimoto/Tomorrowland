from __future__ import annotations

from typing import Any

from elasticsearch import Elasticsearch

from services.search.hybrid import SearchResult

INDEX_NAME = "tomorrowland_documents"


class ElasticsearchSearchClient:
    """Thin wrapper around the Elasticsearch client for full-text (BM25) search."""

    def __init__(self, hosts: list[str] | None = None) -> None:
        self._client = Elasticsearch(hosts=hosts or ["http://localhost:9200"])
        self.create_index_if_not_exists()

    def create_index_if_not_exists(self) -> None:
        """Create the document index with mappings if it does not exist.

        Note: Analyzer filter settings (e.g. ``min_gram``) are baked in at
        index creation time.  Existing indices must be deleted and recreated
        for this change to take effect.
        """
        if self._client.indices.exists(index=INDEX_NAME):
            return

        self._client.indices.create(
            index=INDEX_NAME,
            settings={
                "analysis": {
                    "filter": {
                        "autocomplete_ngram": {
                            "type": "edge_ngram",
                            "min_gram": 1,  # single-char prefix search ("t" matching "test1")
                            "max_gram": 20,
                        }
                    },
                    "analyzer": {
                        "autocomplete_index": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "autocomplete_ngram"],
                        },
                        "autocomplete_search": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase"],
                        },
                    },
                }
            },
            mappings={
                "properties": {
                    "doc_id": {"type": "keyword"},
                    "path": {
                        "type": "text",
                        "fields": {
                            "autocomplete": {
                                "type": "text",
                                "analyzer": "autocomplete_index",
                                "search_analyzer": "autocomplete_search",
                            }
                        },
                    },
                    "filename": {
                        "type": "text",
                        "fields": {
                            "autocomplete": {
                                "type": "text",
                                "analyzer": "autocomplete_index",
                                "search_analyzer": "autocomplete_search",
                            }
                        },
                    },
                    "content_original": {
                        "type": "text",
                        "fields": {
                            "autocomplete": {
                                "type": "text",
                                "analyzer": "autocomplete_index",
                                "search_analyzer": "autocomplete_search",
                            }
                        },
                    },
                    "content_english": {
                        "type": "text",
                        "fields": {
                            "autocomplete": {
                                "type": "text",
                                "analyzer": "autocomplete_index",
                                "search_analyzer": "autocomplete_search",
                            }
                        },
                    },
                    "title": {
                        "type": "text",
                        "fields": {
                            "autocomplete": {
                                "type": "text",
                                "analyzer": "autocomplete_index",
                                "search_analyzer": "autocomplete_search",
                            }
                        },
                    },
                    "summary": {
                        "type": "text",
                        "fields": {
                            "autocomplete": {
                                "type": "text",
                                "analyzer": "autocomplete_index",
                                "search_analyzer": "autocomplete_search",
                            }
                        },
                    },
                    "tags": {"type": "keyword"},
                    "entities": {"type": "keyword"},
                    "metadata": {"type": "object"},
                    "allowed_group_ids": {"type": "keyword"},
                }
            },
        )

    def index_document(self, doc_id: str, document: dict[str, Any]) -> None:
        """Index or update a document by *doc_id*."""
        self._client.index(index=INDEX_NAME, id=doc_id, document=document)

    def delete_document(self, doc_id: str) -> None:
        """Remove a document from the index."""
        self._client.delete(index=INDEX_NAME, id=doc_id)

    def update_document_field(
        self,
        doc_id: str,
        field: str,
        value: Any,
    ) -> None:
        """Update a single field of an existing document (partial update)."""
        self._client.update(
            index=INDEX_NAME,
            id=doc_id,
            doc={field: value},
        )

    def close(self) -> None:
        """Close the underlying Elasticsearch client."""
        self._client.close()

    def search(
        self,
        query: str,
        group_ids: list[str],
        size: int = 50,
        *,
        is_admin: bool = False,
    ) -> list[SearchResult]:
        """BM25 search with an explicit server-side permission filter.

        Admin callers set *is_admin=True* to bypass the permission filter.
        Non-admin callers always get an ACL filter, even when *group_ids* is
        empty, so a groupless user cannot accidentally see every document if a
        caller forgets an earlier route-level guard.
        """
        es_query: dict[str, Any] = {
            "bool": {
                "should": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": [
                                "title^3",
                                "filename^3",
                                "path^2",
                                "content_english^2",
                                "content_original^2",
                                "summary",
                                "tags",
                            ],
                            "type": "best_fields",
                        }
                    },
                    {
                        "multi_match": {
                            "query": query,
                            "fields": [
                                "title.autocomplete^1.5",
                                "filename.autocomplete^2",
                                "path.autocomplete",
                                "content_english.autocomplete",
                                "content_original.autocomplete",
                                "summary.autocomplete^0.5",
                            ],
                            "type": "best_fields",
                        }
                    },
                ],
                "minimum_should_match": 1,
            }
        }
        if not is_admin:
            es_query["bool"]["filter"] = {"terms": {"allowed_group_ids": group_ids}}

        response = self._client.search(index=INDEX_NAME, query=es_query, size=size)
        hits = response["hits"]["hits"]

        results: list[SearchResult] = []
        for hit in hits:
            source = hit.get("_source", {})
            results.append(
                SearchResult(
                    doc_id=hit["_id"],
                    score=float(hit["_score"]),
                    title=source.get("title"),
                    metadata=source.get("metadata"),
                )
            )

        return results
