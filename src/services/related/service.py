"""Related document and expertise map service."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from services.documents.models import DocumentRow
from services.extraction.registry import ExtractorRegistry
from services.related.repository import RelatedRepository
from services.search.encoder import MockEncoder
from services.search.hybrid import SearchResult
from services.search.qdrant import QdrantSearchClient

RELATED_SEARCH_MULTIPLIER = 4
EXPERTISE_SEARCH_LIMIT = 50
SUBSCRIPTION_MATCH_THRESHOLD = 0.75
SIGNAL_WEIGHTS = {
    "view": 3.0,
    "comment": 2.0,
    "annotation": 2.0,
    "subscription": 1.0,
}


@dataclass
class _ExpertiseAggregate:
    user_id: str
    display_name: str | None
    score: float = 0.0
    view_count: int = 0
    comment_count: int = 0
    annotation_count: int = 0
    subscription_count: int = 0
    docs: dict[str, dict[str, Any]] = field(default_factory=dict)


class RelatedService:
    """Build related document and expertise responses."""

    def __init__(
        self,
        repository: RelatedRepository,
        qdrant_client: QdrantSearchClient,
        encoder: MockEncoder,
        extractor_registry: ExtractorRegistry | None = None,
    ) -> None:
        self._repository = repository
        self._qdrant = qdrant_client
        self._encoder = encoder
        self._extractor = extractor_registry or ExtractorRegistry()

    def related_documents(
        self,
        doc: DocumentRow,
        group_ids: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return related documents for a source document."""
        if doc.path is None:
            return []
        query_text = self._extractor.extract(Path(doc.path), doc.mime_type)
        if not query_text:
            return []

        vector = self._encoder.encode(query_text)
        results = self._qdrant.search(
            vector=vector,
            group_ids=group_ids,
            limit=max(limit * RELATED_SEARCH_MULTIPLIER, limit + 1),
        )
        related = _dedupe_results(
            results,
            exclude_doc_id=str(doc.id),
            limit=max(limit * RELATED_SEARCH_MULTIPLIER, limit + 1),
        )
        metadata = self._repository.document_metadata(
            [result.doc_id for result in related], group_ids
        )
        return [
            {
                "doc_id": result.doc_id,
                "title": metadata.get(result.doc_id, {}).get("title"),
                "score": result.score,
            }
            for result in related
            if result.doc_id in metadata
        ][:limit]

    def expertise(self, topic: str, group_ids: list[str]) -> list[dict[str, Any]]:
        """Return users with activity related to a topic."""
        vector = self._encoder.encode(topic)
        results = self._qdrant.search(
            vector=vector,
            group_ids=group_ids,
            limit=EXPERTISE_SEARCH_LIMIT,
        )
        matching_docs = _dedupe_results(results, exclude_doc_id=None, limit=EXPERTISE_SEARCH_LIMIT)
        doc_ids = [result.doc_id for result in matching_docs]
        doc_scores = {result.doc_id: result.score for result in matching_docs}

        aggregates: dict[str, _ExpertiseAggregate] = {}
        for signal in self._repository.expertise_signals(doc_ids, group_ids):
            user_id = str(signal["user_id"])
            aggregate = aggregates.setdefault(
                user_id,
                _ExpertiseAggregate(
                    user_id=user_id,
                    display_name=signal["display_name"],
                ),
            )
            signal_type = str(signal["signal_type"])
            aggregate.score += SIGNAL_WEIGHTS[signal_type] * doc_scores.get(
                str(signal["doc_id"]), 1.0
            )
            if signal_type == "view":
                aggregate.view_count += 1
            elif signal_type == "comment":
                aggregate.comment_count += 1
            elif signal_type == "annotation":
                aggregate.annotation_count += 1
            doc_id = str(signal["doc_id"])
            aggregate.docs.setdefault(
                doc_id,
                {
                    "doc_id": doc_id,
                    "title": signal["doc_title"],
                    "score": doc_scores.get(doc_id, 0.0),
                },
            )

        topic_vector = self._encoder.encode(topic)
        for subscription in self._repository.active_subscriptions():
            if not self._repository.user_can_access_any(
                UUID(str(subscription["user_id"])), doc_ids, group_ids
            ):
                continue
            subscription_query = str(subscription["query"])
            similarity = _cosine_similarity(topic_vector, self._encoder.encode(subscription_query))
            if not _topics_match(topic, subscription_query, similarity):
                continue
            user_id = str(subscription["user_id"])
            aggregate = aggregates.setdefault(
                user_id,
                _ExpertiseAggregate(
                    user_id=user_id,
                    display_name=subscription["display_name"],
                ),
            )
            aggregate.subscription_count += 1
            aggregate.score += SIGNAL_WEIGHTS["subscription"] * similarity

        return [_expertise_response(aggregate) for aggregate in _rank_aggregates(aggregates)]


def _dedupe_results(
    results: list[SearchResult],
    exclude_doc_id: str | None,
    limit: int,
) -> list[SearchResult]:
    seen: dict[str, SearchResult] = {}
    for result in results:
        if not result.doc_id or result.doc_id == exclude_doc_id:
            continue
        if result.doc_id not in seen or result.score > seen[result.doc_id].score:
            seen[result.doc_id] = result
    return sorted(seen.values(), key=lambda item: (-item.score, item.doc_id))[:limit]


def _rank_aggregates(
    aggregates: dict[str, _ExpertiseAggregate],
) -> list[_ExpertiseAggregate]:
    return sorted(
        aggregates.values(),
        key=lambda item: (-item.score, item.display_name or "", item.user_id),
    )


def _expertise_response(aggregate: _ExpertiseAggregate) -> dict[str, Any]:
    evidence = sorted(
        aggregate.docs.values(),
        key=lambda item: (-float(item["score"]), str(item["doc_id"])),
    )[:5]
    return {
        "user_id": aggregate.user_id,
        "display_name": aggregate.display_name,
        "score": aggregate.score,
        "signals": {
            "views": aggregate.view_count,
            "comments": aggregate.comment_count,
            "annotations": aggregate.annotation_count,
            "subscriptions": aggregate.subscription_count,
        },
        "reason": "Has activity on matching documents",
        "top_docs": evidence,
    }


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _topics_match(topic: str, query: str, similarity: float) -> bool:
    normalized_topic = topic.casefold().strip()
    normalized_query = query.casefold().strip()
    return (
        normalized_topic in normalized_query
        or normalized_query in normalized_topic
        or similarity >= SUBSCRIPTION_MATCH_THRESHOLD
    )
