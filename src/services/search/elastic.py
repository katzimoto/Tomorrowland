from __future__ import annotations

from typing import Any

from elasticsearch import Elasticsearch

from services.search.hybrid import SearchResult

INDEX_NAME = "tomorrowland_documents"


class ElasticsearchSearchClient:
    """Thin wrapper around the Elasticsearch client for full-text (BM25) search."""

    def __init__(self, hosts: list[str] | None = None) -> None:
        self._client = Elasticsearch(hosts=hosts or ["http://localhost:9200"])

    def create_index_if_not_exists(self) -> None:
        """Create the document index with mappings if it does not exist."""
        if self._client.indices.exists(index=INDEX_NAME):
            return

        self._client.indices.create(
            index=INDEX_NAME,
            mappings={
                "properties": {
                    "doc_id": {"type": "keyword"},
                    "content_english": {"type": "text"},
                    "title": {"type": "text"},
                    "summary": {"type": "text"},
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
    ) -> list[SearchResult]:
        """BM25 search restricted to *group_ids*."""
        if not group_ids:
            raise ValueError("group_ids must not be empty")

        es_query: dict[str, Any] = {
            "bool": {
                "must": {
                    "multi_match": {
                        "query": query,
                        "fields": ["content_english^2", "title^3", "summary", "tags"],
                    }
                },
                "filter": {"terms": {"allowed_group_ids": group_ids}},
            }
        }

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
