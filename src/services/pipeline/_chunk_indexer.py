"""Shared Qdrant chunk building and upserting for pipeline workers.

Extracted from ``worker.py:_index_qdrant`` and ``embed_worker.py:handle_message``
to eliminate duplicated chunk dict construction and Qdrant upsert logic.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from sqlalchemy.engine import Connection

from services.documents.layout_block_repository import LayoutBlockRepository
from services.search.encoder import TextEncoder
from services.search.qdrant import QdrantSearchClient
from shared.correlation import get_correlation_id

logger = logging.getLogger(__name__)


def build_and_upsert_qdrant_chunks(
    *,
    document_id: UUID,
    chunk_texts: list[str],
    chunk_meta: list[dict[str, Any]],
    allowed_group_ids: list[str],
    doc_title: str | None,
    encoder: TextEncoder,
    qdrant: QdrantSearchClient,
    connection: Connection,
    source_id: str = "",
    translation_version_id: str = "",
    translation_quality: str = "",
    translation_validation_status: str = "",
    metrics: Any = None,
) -> None:
    """Encode chunks, build Qdrant payloads, resolve layout blocks, and upsert.

    Shared by ``PipelineWorker._index_qdrant`` and ``EmbedConsumer.handle_message``
    to keep chunk dict construction + upsert logic in one place.

    Args:
        document_id: The document being indexed.
        chunk_texts: Raw chunk text strings to encode.
        chunk_meta: Parallel list of metadata dicts, each containing at minimum
            ``suffix``, ``idx``, ``lang``, and ``text_lane``.  May also include
            ``source_lang``, ``page_number``, ``section_heading``.
        allowed_group_ids: ACL group IDs for the chunk payload.
        doc_title: Optional document title for the ``title`` payload field.
        encoder: Text encoder for vectorization.
        qdrant: Qdrant client for upsert.
        connection: DB connection for layout-block repository resolution.
        source_id: Source UUID string for the ``source_id`` payload field.
        translation_version_id: Threaded from translation metadata.
        translation_quality: Threaded from translation metadata.
        translation_validation_status: Threaded from translation metadata.
        metrics: Optional metrics registry for timing observations.
    """
    if not chunk_texts:
        return

    vectors = encoder.encode_documents(chunk_texts)

    qdrant_chunks: list[dict[str, Any]] = []
    for i, meta in enumerate(chunk_meta):
        entry: dict[str, Any] = {
            "chunk_id": f"{document_id}-{meta['suffix']}-{meta['idx']}",
            "document_id": str(document_id),
            "group_id": allowed_group_ids,
            "chunk_index": meta["idx"],
            "text": chunk_texts[i],
            "vector": vectors[i],
            "source_id": source_id,
        }
        if doc_title:
            entry["title"] = doc_title
        lang = meta.get("lang")
        if lang:
            entry["language"] = lang
        entry["text_lane"] = meta["text_lane"]
        source_lang = meta.get("source_lang")
        if source_lang:
            entry["translated_from"] = source_lang
        if translation_version_id and meta["text_lane"] == "translated":
            entry["translation_version_id"] = translation_version_id
            entry["translation_quality"] = translation_quality
            entry["translation_validation_status"] = translation_validation_status
        page_number = meta.get("page_number")
        if page_number is not None:
            entry["page_number"] = page_number
        section_heading = meta.get("section_heading")
        if section_heading is not None:
            entry["section_heading"] = section_heading
        qdrant_chunks.append(entry)

    # Resolve layout_block_id for precise chunk→block linkage.
    from services.rag.layout_hierarchy import resolve_chunk_layout_block_ids

    try:
        layout_repo = LayoutBlockRepository(connection)
        resolve_chunk_layout_block_ids(qdrant_chunks, document_id, layout_repo)
    except Exception:
        logger.debug(
            "layout_block_id resolution skipped for document_id=%s",
            document_id,
        )

    start = time.perf_counter()
    qdrant.upsert_chunks(qdrant_chunks, delete_existing=True)
    if metrics is not None:
        metrics.search_backend_duration_seconds.labels("qdrant", "upsert").observe(
            time.perf_counter() - start
        )
        metrics.search_index_documents.labels("qdrant").inc()

    logger.debug(
        "Qdrant upsert complete document_id=%s chunks=%d correlation=%s",
        document_id,
        len(qdrant_chunks),
        get_correlation_id(),
    )
