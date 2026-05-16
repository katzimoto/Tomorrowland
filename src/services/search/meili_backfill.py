from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from services.chunking.splitter import chunk_text
from services.search.meili_provider import MeilisearchSearchProvider
from services.search.meili_types import ChunkMetadata, SearchChunkRecord
from shared.config import Settings
from shared.db import db_uuid, to_uuid

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 100
_DOC_PAGE_SIZE = 50


@dataclass
class BackfillSummary:
    documents_scanned: int = 0
    chunks_skipped: int = 0
    chunks_indexed: int = 0
    documents_failed: int = 0
    documents_skipped_no_translation: int = 0
    is_dry_run: bool = False


class BackfillService:
    def __init__(
        self,
        engine: Engine,
        provider: MeilisearchSearchProvider,
        *,
        batch_size: int = _DEFAULT_BATCH_SIZE,
        dry_run: bool = False,
    ) -> None:
        self._engine = engine
        self._provider = provider
        self._batch_size = batch_size
        self._dry_run = dry_run

    def run(self) -> BackfillSummary:
        summary = BackfillSummary(is_dry_run=self._dry_run)
        offset = 0

        while True:
            with self._engine.connect() as conn:
                rows = self._fetch_indexed_documents(conn, offset)

            if not rows:
                break

            for row in rows:
                summary.documents_scanned += 1
                try:
                    self._process_document(row, summary)
                except Exception:
                    logger.exception("Backfill failed for doc_id=%s", row["id"])
                    summary.documents_failed += 1

            offset += _DOC_PAGE_SIZE

        return summary

    def _fetch_indexed_documents(self, conn: Connection, offset: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            sa.text(
                """
                SELECT id, source_id, source, path, mime_type, title,
                       source_language, target_language
                FROM documents
                WHERE status = 'indexed'
                ORDER BY id
                LIMIT :limit OFFSET :offset
                """
            ),
            {"limit": _DOC_PAGE_SIZE, "offset": offset},
        ).mappings()
        return [dict(row) for row in rows]

    def _process_document(
        self,
        doc_row: dict[str, Any],
        summary: BackfillSummary,
    ) -> None:
        doc_id = to_uuid(doc_row["id"])

        translated = self._fetch_translated_text(doc_id)
        if translated is None:
            summary.documents_skipped_no_translation += 1
            return

        chunks = chunk_text(translated)
        if not chunks:
            return

        group_ids = self._fetch_source_group_ids(to_uuid(doc_row["source_id"]))

        records = [
            SearchChunkRecord.from_parts(
                document_id=str(doc_id),
                chunk_index=idx,
                title=doc_row.get("title") or "",
                content=chunk_text_content,
                allowed_group_ids=group_ids,
                metadata=ChunkMetadata(
                    source=doc_row.get("source"),
                    mime_type=doc_row.get("mime_type"),
                    file_name=Path(doc_row["path"]).name if doc_row.get("path") else None,
                    language=doc_row.get("source_language"),
                ),
                position_kwargs={},
            )
            for idx, chunk_text_content in enumerate(chunks)
        ]

        existing = self._provider.existing_chunk_checksums(str(doc_id), shadow=True)

        to_index: list[SearchChunkRecord] = []
        for record in records:
            if existing.get(record.id) == record.content_checksum:
                summary.chunks_skipped += 1
            else:
                to_index.append(record)

        if not to_index:
            return

        if not self._dry_run:
            for i in range(0, len(to_index), self._batch_size):
                batch = to_index[i : i + self._batch_size]
                self._provider.index_batch(batch, shadow=True)

        summary.chunks_indexed += len(to_index)

    def _fetch_translated_text(self, doc_id: UUID) -> str | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    """
                    SELECT translated_text
                    FROM document_translation_versions
                    WHERE doc_id = :doc_id
                      AND status = 'available'
                    ORDER BY version_number DESC
                    LIMIT 1
                    """
                ),
                {"doc_id": db_uuid(doc_id)},
            ).one_or_none()
        return row[0] if row else None

    def _fetch_source_group_ids(self, source_id: UUID) -> list[str]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                sa.text(
                    """
                    SELECT group_id
                    FROM source_permissions
                    WHERE source_id = :source_id
                    ORDER BY group_id
                    """
                ),
                {"source_id": db_uuid(source_id)},
            ).scalars()
            return [str(to_uuid(r)) for r in rows]


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Idempotent Meilisearch backfill/reindex command.\n\n"
        "Populates the shadow Meilisearch index from canonical document data.\n"
        "Skips unchanged chunks by checksum comparison. Safe to re-run."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=_DEFAULT_BATCH_SIZE,
        help=f"Number of chunks per Meilisearch batch (default: {_DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and report what would be done without writing to Meilisearch",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    return parser


_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level), format=_LOG_FORMAT)

    settings = Settings()
    engine = sa.create_engine(settings.postgres_url)

    from meilisearch import Client

    meili_url = getattr(settings, "meilisearch_url", "http://meilisearch:7700")
    meili_key = getattr(settings, "meilisearch_master_key", "")
    meili_client = Client(meili_url, meili_key)
    provider = MeilisearchSearchProvider(meili_client)

    service = BackfillService(
        engine,
        provider,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )

    start = time.perf_counter()
    summary = service.run()
    elapsed = time.perf_counter() - start

    _log_summary(summary, elapsed)

    if summary.documents_failed > 0:
        sys.exit(1)


def _log_summary(summary: BackfillSummary, elapsed_seconds: float) -> None:
    logger.info(
        "Backfill summary: "
        "documents_scanned=%d "
        "skipped_no_translation=%d "
        "chunks_skipped=%d "
        "chunks_indexed=%d "
        "documents_failed=%d "
        "dry_run=%s "
        "elapsed_seconds=%.2f",
        summary.documents_scanned,
        summary.documents_skipped_no_translation,
        summary.chunks_skipped,
        summary.chunks_indexed,
        summary.documents_failed,
        "yes" if summary.is_dry_run else "no",
        elapsed_seconds,
    )


if __name__ == "__main__":
    main()
