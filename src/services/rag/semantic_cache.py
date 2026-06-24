"""Semantic query-answer cache backed by Qdrant.

Stores past query-answer pairs as vectors in a dedicated Qdrant collection.
On cache lookup, the incoming query is embedded and a cosine-similarity search
returns the closest cached entry.  If the similarity exceeds the configured
threshold, the cached answer is returned immediately, skipping the full
retrieval and generation pipeline.

Key design decisions:
- **Response-level caching** (not retrieval-level): caches the full
  AnswerResponse, giving the highest latency + cost savings (~30-50%).
- **TTL-based invalidation**: cache entries expire after a configurable
  interval (default 24 h).  No event-driven eviction yet.
- **Model-version awareness**: entries are tagged with the embedding model
  name and dimension so a model change won't silently return incompatible
  results.
- **Degraded-only**: cache misses or failures fall through to the normal
  pipeline; the cache is purely an optimisation.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from shared.config import Settings

logger = logging.getLogger(__name__)

CACHE_COLLECTION = "rag_cache"

# Per-collection-name guard so _ensure_collection() only runs once per process
# per collection, avoiding a Qdrant get_collections() call on every request.
_collections_initialised: set[str] = set()


@dataclass
class CachedAnswer:
    """Serialisable cache payload stored as Qdrant point payload."""

    question: str
    answer: str
    model: str
    citations_json: str  # JSON-serialised list of Citation dicts
    trace_json: str  # JSON-serialised RetrievalTrace
    cached_at_ts: float = field(default_factory=time.time)


class SemanticCache:
    """Qdrant-backed semantic cache for RAG query-answer pairs."""

    def __init__(
        self,
        qdrant_client: Any,
        encoder: Any,
        settings: Settings,
    ) -> None:
        global _collections_initialised
        self._qdrant = qdrant_client
        self._encoder = encoder
        self._settings = settings
        self._collection = settings.rag_semantic_cache_collection
        self._threshold = settings.rag_semantic_cache_similarity_threshold
        self._ttl = settings.rag_semantic_cache_ttl_seconds
        self._model_tag = f"{settings.embedding_model}:{encoder.dimension}"
        if self._collection not in _collections_initialised:
            self._ensure_collection()
            _collections_initialised.add(self._collection)

    @property
    def enabled(self) -> bool:
        """Whether caching is active per config."""
        return self._settings.rag_semantic_cache_enabled

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, question: str) -> CachedAnswer | None:
        """Look up a cached answer for *question*.

        Returns None on miss, cache error, or when the best match is below the
        similarity threshold.
        """
        if not self.enabled:
            return None

        try:
            query_vector = self._encoder.encode_query(question)
        except Exception:
            logger.debug("Semantic cache: query embedding failed — skipping cache")
            return None

        try:
            hits = self._qdrant.client.search(
                collection_name=self._collection,
                query_vector=query_vector,
                limit=1,
                with_payload=True,
            )
        except Exception:
            logger.debug("Semantic cache: Qdrant search failed — skipping cache")
            return None

        if not hits or not hits[0].payload:
            return None

        now = time.time()
        score = hits[0].score
        if score < self._threshold:
            return None

        payload = hits[0].payload

        # Skip entries that have exceeded the TTL.
        if now - payload.get("cached_at_ts", 0.0) > self._ttl:
            return None

        # Skip entries produced by a different embedding model — their vectors
        # are not mathematically comparable to the current model's queries.
        if payload.get("embedding_model_tag") != self._model_tag:
            return None

        return CachedAnswer(
            question=payload.get("question", ""),
            answer=payload.get("answer", ""),
            model=payload.get("model", ""),
            citations_json=payload.get("citations_json", "[]"),
            trace_json=payload.get("trace_json", "{}"),
            cached_at_ts=payload.get("cached_at_ts", 0.0),
        )

    def put(
        self,
        question: str,
        answer: str,
        model: str,
        citations_json: str,
        trace_json: str,
    ) -> None:
        """Store a query-answer pair in the cache.

        Silently ignores cache errors (the cache is best-effort).
        """
        if not self.enabled:
            return

        try:
            vector = self._encoder.encode_query(question)
        except Exception:
            logger.debug("Semantic cache: store embedding failed — skipping write")
            return

        # Expire entries older than TTL by setting a payload filter on
        # ``cached_at_ts``.  Qdrant doesn't natively evict by TTL, so we
        # filter at read time in ``get()`` by checking the payload timestamp.
        now = time.time()

        try:
            self._qdrant.client.upsert(
                collection_name=self._collection,
                points=[
                    PointStruct(
                        id=int(hashlib.sha256(question.encode()).hexdigest(), 16) % (2**63),
                        vector=vector,
                        payload={
                            "question": question,
                            "answer": answer,
                            "model": model,
                            "citations_json": citations_json,
                            "trace_json": trace_json,
                            "embedding_model_tag": self._model_tag,
                            "embedding_dimension": self._encoder.dimension,
                            "cached_at_ts": now,
                        },
                    )
                ],
            )
        except Exception:
            logger.debug("Semantic cache: Qdrant upsert failed — skipping write")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_collection(self) -> None:
        """Create the cache collection if it doesn't exist."""
        try:
            collections = self._qdrant.client.get_collections()
            existing = {c.name for c in collections.collections}
            if self._collection in existing:
                return

            self._qdrant.client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=self._encoder.dimension,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(
                "Semantic cache collection '%s' created (dim=%d)",
                self._collection,
                self._encoder.dimension,
            )
        except Exception:
            logger.debug("Semantic cache: collection creation failed")
