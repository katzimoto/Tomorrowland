"""Alert matching service."""

from __future__ import annotations

import math
from typing import Any
from uuid import UUID

from services.alerts.repository import AlertRepository
from services.documents.models import DocumentRow
from services.search.encoder import TextEncoder


class AlertMatcher:
    """Match indexed documents against active subscriptions."""

    def __init__(
        self,
        repository: AlertRepository,
        encoder: TextEncoder,
        default_threshold: float = 0.75,
    ) -> None:
        self._repository = repository
        self._encoder = encoder
        self._default_threshold = default_threshold

    def match_document(self, doc: DocumentRow, content: str) -> int:
        """Create notifications for active subscriptions matching a document."""
        doc_vector = self._encoder.encode(content)
        created = 0
        for subscription in self._repository.active_subscriptions_for_doc(doc.id):
            query_vector = self._encoder.encode(str(subscription["query"]))
            similarity = _cosine_similarity(doc_vector, query_vector)
            threshold = (
                self._default_threshold
                if subscription["similarity_threshold"] is None
                else float(subscription["similarity_threshold"])
            )
            if similarity >= threshold and self._repository.create_notification(
                subscription_id=_row_uuid(subscription, "id"),
                user_id=_row_uuid(subscription, "user_id"),
                doc_id=doc.id,
                similarity=similarity,
            ):
                created += 1
        return created


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    """Return cosine similarity for two vectors."""
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _row_uuid(row: dict[str, Any], key: str) -> UUID:
    return UUID(str(row[key]))
