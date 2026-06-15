"""Slow worker for high-quality translation enrichment."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from services.alerts.service import AlertMatcher
from services.chunking.splitter import chunk_text
from services.documents.layout_block_repository import LayoutBlockRepository
from services.documents.repository import (
    DocumentRepository,
    TranslationVersionRepository,
)
from services.intelligence.worker import IntelligenceWorker
from services.pipeline.jobs import PipelineJobRepository
from services.search.encoder import TextEncoder
from services.search.meili_provider import MeilisearchSearchProvider
from services.search.meili_types import ChunkMetadata, SearchChunkRecord
from services.search.qdrant import QdrantSearchClient
from services.translation.client import _safe_str, build_translation_metadata
from services.translation.libretranslate_provider import LibreTranslateArgosProvider
from services.translation.provider import TranslationProvider
from services.translation.qe_scorer import QEScorer, build_qe_scorer
from services.translation.segment_pipeline import run_segment_pipeline
from shared.correlation import get_correlation_id
from shared.metrics import MetricsRegistry

logger = logging.getLogger(__name__)

_ALLOWED_JOB_TYPES = ["enrich_document"]


def _build_enrich_metadata(
    *,
    translator: TranslationProvider | None,
    source_language: str | None,
    target_language: str,
    input_text: str,
    output_text: str,
    fallback_used: bool = False,
    fallback_reason: str | None = None,
    # Segment-aware validation fields (#728)
    segment_count: int = 0,
    failed_segment_count: int = 0,
    placeholder_mismatch_count: int = 0,
    number_date_mismatch_count: int = 0,
    length_ratio_outlier_count: int = 0,
    warnings: list[str] | None = None,
    pipeline_validation_status: str | None = None,
) -> dict[str, Any]:
    """Build translation metadata for high-lane enrichment (#727, #728)."""
    provider = (_safe_str(translator.name) if translator else None) or "libretranslate_argos"
    provider_version = _safe_str(translator.version) if translator else None
    model_family = _safe_str(translator.model_family) if translator else None
    # Pipeline status takes precedence over fallback-derived status (#728)
    validation_status = (
        pipeline_validation_status
        if pipeline_validation_status is not None
        else ("warning" if fallback_used else "ok")
    )
    return build_translation_metadata(
        provider=provider,
        provider_version=provider_version,
        model_family=model_family,
        quality_lane="high",
        purpose="display",
        source_language=source_language,
        target_language=target_language,
        input_text=input_text,
        output_text=output_text,
        segment_count=segment_count,
        validation_status=validation_status,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        failed_segment_count=failed_segment_count,
        placeholder_mismatch_count=placeholder_mismatch_count,
        number_date_mismatch_count=number_date_mismatch_count,
        length_ratio_outlier_count=length_ratio_outlier_count,
        warnings=warnings,
    )


class EnrichmentSubtaskError(RuntimeError):
    """Raised when alert matching or intelligence fails after indexing succeeds.

    The document remains indexed; only the job is marked for retry/dead-letter.
    """


class SlowWorker:
    """Re-translate, re-chunk, and re-index documents with pending_high quality."""

    def __init__(
        self,
        document_repository: DocumentRepository,
        translator: TranslationProvider,
        encoder: TextEncoder,
        qdrant_client: QdrantSearchClient,
        version_repository: TranslationVersionRepository | None = None,
        meili_provider: MeilisearchSearchProvider | None = None,
        intelligence_worker: IntelligenceWorker | None = None,
        alert_matcher: AlertMatcher | None = None,
        layout_repository: LayoutBlockRepository | None = None,
        high_provider: TranslationProvider | None = None,
        qe_scorer: QEScorer | None = None,
    ) -> None:
        self._doc_repo = document_repository
        self._translator = translator
        self._high_provider = high_provider
        self._encoder = encoder
        self._qdrant = qdrant_client
        self._meili = meili_provider
        self._intelligence = intelligence_worker
        self._version_repo = version_repository
        self._alert_matcher = alert_matcher
        self._layout_repo = layout_repository
        self._qe_scorer = qe_scorer

    def _resolve_translator(self, source_lang: str | None, target_lang: str) -> TranslationProvider:
        """Return the best available translator for a language pair.

        When *high_provider* is configured and declares support for the
        pair (via capabilities), use it; otherwise fall back to the
        baseline :attr:`_translator`.
        """
        if self._high_provider is not None and source_lang is not None:
            caps = self._high_provider.capabilities
            high_pairs = caps.get("language_pairs", [])
            if any(
                p.get("source") == source_lang and p.get("target") == target_lang
                for p in high_pairs
            ):
                return self._high_provider
        return self._translator

    def process_document(self, document_id: UUID, content_text: str = "") -> None:
        """Run the enrichment pipeline for a single document.

        Args:
            document_id: Document to enrich.
            content_text: Pre-extracted text from the parse stage payload.
                Must be supplied by the caller; this worker does not call the
                extractor directly.

        On success the document translation_quality is set to ``"high"`` and
        status to ``"indexed"``. On any unhandled exception the version status
        is set to ``"failed"`` and the error is logged (enrichment is
        best-effort).
        """
        try:
            self._run(document_id, content_text=content_text)
        except Exception as exc:
            logger.exception(
                "Slow worker failed for document_id=%s correlation=%s",
                document_id,
                get_correlation_id(),
            )
            # EnrichmentSubtaskError: indexing already succeeded; do not mark
            # the document failed. The job will be retried/dead-lettered by the
            # caller, but the document remains searchable.
            if not isinstance(exc, EnrichmentSubtaskError) and self._version_repo is None:
                self._doc_repo.update_status(document_id, "failed")
            raise

    def _run(self, document_id: UUID, content_text: str = "") -> None:
        doc = self._doc_repo.get_by_id(document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")

        # If version repository is available, process pending versions
        if self._version_repo is not None:
            self._run_versioned(doc, content_text=content_text)
            return

        # Legacy path: process document directly
        self._run_legacy(doc, content_text=content_text)

    def _run_versioned(self, doc: Any, content_text: str = "") -> None:
        """Process the oldest pending version for a document."""
        if self._version_repo is None:
            raise RuntimeError("version_repo required for _run_versioned")
        pending = self._version_repo.get_pending_versions(doc.id)
        if not pending:
            # Fallback to legacy behavior if no pending versions exist
            self._run_legacy(doc, content_text=content_text)
            return

        version = pending[0]
        version_id = UUID(str(version["id"]))

        try:
            self._version_repo.update_version_status(version_id, "running")

            # 1. Use pre-extracted text from the parse stage payload
            text = content_text

            # 2. Translate to the document's configured target language
            #    Use segment-aware pipeline when layout blocks are available (#728)
            source_lang = doc.source_language
            target_lang = doc.target_language or "en"

            # Load layout blocks for segment-aware translation
            layout_blocks: list[dict[str, Any]] | None = None
            if self._layout_repo is not None:
                try:
                    layout_blocks_raw = self._layout_repo.list_by_document(doc.id)
                    if layout_blocks_raw:
                        layout_blocks = [
                            {"text": block.text, "block_type": block.block_type}
                            for block in layout_blocks_raw
                            if block.text
                        ]
                except Exception:
                    logger.debug(
                        "Could not load layout blocks for document_id=%s",
                        doc.id,
                    )

            # Resolve translator (high provider or baseline) and route accordingly
            _active = self._resolve_translator(source_lang, target_lang)
            translated, validation = run_segment_pipeline(
                text,
                translate_fn=_active.translate,
                source_lang=source_lang,
                target_lang=target_lang,
                layout_blocks=layout_blocks,
            )
            _seg_count = validation.segment_count
            _seg_failed = validation.failed_segment_count
            _ph_mismatch = validation.placeholder_mismatch_count
            _num_date = validation.number_date_mismatch_count
            _len_outlier = validation.length_ratio_outlier_count
            _warnings = validation.warnings if validation.warnings else None
            _pipeline_status: str | None = validation.validation_status

            # 3. No-op guard: translation returned the same text (document already
            #    in the target language, or LibreTranslate failed auto-detect).
            #    Mark failed so the tab doesn't appear and quality stays unchanged.
            _is_no_op = bool(text) and translated == text
            if _is_no_op or not translated:
                reason = (
                    "Document already in target language or LibreTranslate returned unchanged text"
                    if _is_no_op
                    else "LibreTranslate returned empty translation"
                )
                logger.info(
                    "Slow worker no-op for document_id=%s version_id=%s: %s",
                    doc.id,
                    version_id,
                    reason,
                )
                _meta = _build_enrich_metadata(
                    translator=_active,
                    source_language=source_lang,
                    target_language=target_lang,
                    input_text=text,
                    output_text=translated,
                    fallback_used=True,
                    fallback_reason=reason,
                    segment_count=_seg_count,
                    failed_segment_count=_seg_failed,
                    placeholder_mismatch_count=_ph_mismatch,
                    number_date_mismatch_count=_num_date,
                    length_ratio_outlier_count=_len_outlier,
                    warnings=_warnings,
                    pipeline_validation_status=_pipeline_status,
                )
                self._version_repo.update_version_status(
                    version_id,
                    "failed",
                    error_summary=reason,
                    metadata=_meta,
                    provider=_meta.get("provider"),
                )
                # Bump translation_quality to "high" so enrichment stops
                # retrying this document.  The document already has a "fast"
                # translation and the enrichment attempt proved no further
                # improvement is possible.
                self._doc_repo.update_translation_quality(doc.id, "high")
                return

            # 4. Store translated text on version with metadata (#727, #728)
            _version_id_str = str(version_id)
            _meta = _build_enrich_metadata(
                translator=_active,
                source_language=source_lang,
                target_language=target_lang,
                input_text=text,
                output_text=translated,
                fallback_used=False,
                segment_count=_seg_count,
                failed_segment_count=_seg_failed,
                placeholder_mismatch_count=_ph_mismatch,
                number_date_mismatch_count=_num_date,
                length_ratio_outlier_count=_len_outlier,
                warnings=_warnings,
                pipeline_validation_status=_pipeline_status,
            )

            # 4a. Run offline quality estimation when configured (#733).
            #     When QE results are available, store them in the metadata
            #     and surface validation_status for translation-version-aware
            #     retrieval (#734).
            #     Runs after metadata is assembled so QE results can be
            #     merged in.  Failures never affect translation availability.
            if self._qe_scorer is not None and self._qe_scorer.enabled:
                try:
                    qe_result = self._qe_scorer.score(
                        source_text=text,
                        translated_text=translated,
                        source_lang=source_lang,
                        target_lang=target_lang,
                    )
                    if qe_result.get("status") not in ("disabled", None):
                        _meta["quality_estimation"] = qe_result
                except Exception:
                    logger.warning(
                        "QE scoring failed for document_id=%s version_id=%s",
                        doc.id,
                        version_id,
                        exc_info=True,
                    )
                    _meta["quality_estimation"] = {"status": "failed"}

            self._version_repo.update_version_status(
                version_id,
                "available",
                translated_text=translated,
                metadata=_meta,
                provider=_meta.get("provider"),
            )

            # 5. Chunk and index (reuse legacy indexing).
            #    Pass translation version metadata so indexed chunks carry
            #    version awareness for downstream retrieval (#734).
            _vs_raw = _meta.get("validation_status")
            _vs = str(_vs_raw) if _vs_raw in ("ok", "warning", "failed") else "ok"
            self._index_document(
                doc,
                translated,
                original=text,
                translation_version_id=_version_id_str,
                translation_quality=str(version.get("quality", "fast")),
                translation_validation_status=_vs,
            )

            # 6. Update document summary quality
            self._doc_repo.update_translation_quality(doc.id, "high")

        except Exception as exc:
            if isinstance(exc, EnrichmentSubtaskError):
                raise  # version already marked available; job retried/dead-lettered above
            # Build fallback metadata for the failure case (#727)
            source_lang = doc.source_language
            target_lang = doc.target_language or "en"
            _meta = _build_enrich_metadata(
                translator=self._translator,
                source_language=source_lang,
                target_language=target_lang,
                input_text=content_text,
                output_text="",
                fallback_used=True,
                fallback_reason=str(exc)[:500],
            )
            self._version_repo.update_version_status(
                version_id,
                "failed",
                error_summary="Translation failed",
                metadata=_meta,
                provider=_meta.get("provider"),
            )
            raise

    def _run_legacy(self, doc: Any, content_text: str = "") -> None:
        """Legacy non-versioned enrichment path."""
        # 1. Use pre-extracted text from the parse stage payload
        text = content_text

        # 2. Translate to the document's configured target language
        #    Use segment-aware pipeline (#728)
        source_lang = doc.source_language
        target_lang = doc.target_language or "en"

        # Load layout blocks for segment-aware translation
        layout_blocks: list[dict[str, Any]] | None = None
        if self._layout_repo is not None:
            try:
                layout_blocks_raw = self._layout_repo.list_by_document(doc.id)
                if layout_blocks_raw:
                    layout_blocks = [
                        {"text": block.text, "block_type": block.block_type}
                        for block in layout_blocks_raw
                        if block.text
                    ]
            except Exception:
                logger.debug(
                    "Could not load layout blocks for document_id=%s",
                    doc.id,
                )

        _active = self._resolve_translator(source_lang, target_lang)
        translated, _validation = run_segment_pipeline(
            text,
            translate_fn=_active.translate,
            source_lang=source_lang,
            target_lang=target_lang,
            layout_blocks=layout_blocks,
        )

        # 3. Chunk and index
        self._index_document(doc, translated, original=text)

        # 4. Update quality only — indexing status transitions happen in
        #    index_worker.py/worker.py after successful vector/keyword insert.
        self._doc_repo.update_translation_quality(doc.id, "high")

    def _index_document(
        self,
        doc: Any,
        translated: str,
        original: str = "",
        *,
        translation_version_id: str = "",
        translation_quality: str = "fast",
        translation_validation_status: str = "ok",
    ) -> None:
        """Chunk, embed, and index a document (both original and translated).

        When *translation_version_id* is provided, each translated chunk
        carries the version identity so downstream retrieval can surface
        which translation version produced the match (#734).
        """
        document_id = doc.id
        allowed_group_ids = [
            str(group_id) for group_id in self._doc_repo.source_group_ids(doc.source_id)
        ]

        # Chunk both original and translated text separately so Meilisearch records
        # pair original chunk text (content) with its translated chunk (content_en).
        original_chunks = (
            list(chunk_text(original, language=doc.source_language)) if original else []
        )
        translated_chunks = list(chunk_text(translated, language=doc.target_language))

        # Index chunks in Meilisearch when configured
        if self._meili is not None:
            try:
                pair_count = min(len(original_chunks), len(translated_chunks))
                meili_records = [
                    SearchChunkRecord.from_parts(
                        document_id=str(document_id),
                        chunk_index=idx,
                        title=doc.title or "",
                        content=orig_chunk,
                        allowed_group_ids=allowed_group_ids,
                        metadata=ChunkMetadata(
                            source_id=str(doc.source_id),
                            source=doc.source,
                            mime_type=doc.mime_type,
                            file_name=Path(doc.path).name if doc.path else None,
                            language=doc.source_language,
                        ),
                        content_en=tran_chunk if translated != original else None,
                    )
                    for idx, (orig_chunk, tran_chunk) in enumerate(
                        zip(
                            original_chunks[:pair_count],
                            translated_chunks[:pair_count],
                            strict=False,
                        )
                    )
                ]
                for idx in range(pair_count, len(original_chunks)):
                    meili_records.append(
                        SearchChunkRecord.from_parts(
                            document_id=str(document_id),
                            chunk_index=idx,
                            title=doc.title or "",
                            content=original_chunks[idx],
                            allowed_group_ids=allowed_group_ids,
                            metadata=ChunkMetadata(
                                source_id=str(doc.source_id),
                                source=doc.source,
                                mime_type=doc.mime_type,
                                file_name=Path(doc.path).name if doc.path else None,
                                language=doc.source_language,
                            ),
                            content_en=None,
                        )
                    )
                if meili_records:
                    self._meili.index_batch(meili_records)
            except Exception as exc:
                logger.error(
                    "Meilisearch indexing failed during enrichment for "
                    "document_id=%s error_type=%s correlation=%s",
                    document_id,
                    exc.__class__.__name__,
                    get_correlation_id(),
                )

        # Build Qdrant points for both original and translated chunks.
        # Batch-encode all chunks in a single call to reduce Ollama round-trips.
        try:
            qdrant_chunks: list[dict[str, Any]] = []

            # Collect all chunk texts
            all_chunk_texts: list[str] = []
            all_chunk_meta: list[dict[str, Any]] = []

            for idx, chunk_text_content in enumerate(original_chunks):
                all_chunk_texts.append(chunk_text_content)
                all_chunk_meta.append(
                    {
                        "lang": doc.source_language,
                        "suffix": "orig",
                        "idx": idx,
                        "is_translated": False,
                    }
                )

            for idx, chunk_text_content in enumerate(translated_chunks):
                all_chunk_texts.append(chunk_text_content)
                all_chunk_meta.append(
                    {
                        "lang": doc.target_language,
                        "suffix": "tr",
                        "idx": idx,
                        "is_translated": True,
                    }
                )

            # Batch-encode all chunks in a single call
            vectors = self._encoder.encode_batch(all_chunk_texts)

            for i, meta in enumerate(all_chunk_meta):
                entry: dict[str, Any] = {
                    "chunk_id": f"{document_id}-{meta['suffix']}-{meta['idx']}",
                    "document_id": str(document_id),
                    "group_id": allowed_group_ids,
                    "chunk_index": meta["idx"],
                    "text": all_chunk_texts[i],
                    "vector": vectors[i],
                    "source_id": str(doc.source_id),
                }
                if doc.title:
                    entry["title"] = doc.title
                if meta["lang"]:
                    entry["language"] = meta["lang"]
                if meta["is_translated"]:
                    entry["text_lane"] = "translated"
                    if doc.source_language:
                        entry["translated_from"] = doc.source_language
                    if translation_version_id:
                        entry["translation_version_id"] = translation_version_id
                        entry["translation_quality"] = translation_quality
                        entry["translation_validation_status"] = translation_validation_status
                else:
                    entry["text_lane"] = "original"
                qdrant_chunks.append(entry)

            if qdrant_chunks:
                self._qdrant.upsert_chunks(qdrant_chunks, delete_existing=True)
        except Exception as exc:
            logger.error(
                "Vector indexing failed during enrichment for "
                "document_id=%s error_type=%s correlation=%s",
                document_id,
                exc.__class__.__name__,
                get_correlation_id(),
            )

        # Alert matching and intelligence run after indexing. Failures are
        # collected and surfaced as EnrichmentSubtaskError so the job is
        # retried/dead-lettered rather than silently marked succeeded. Both
        # steps always run so a single failure doesn't skip the other.
        _subtask_error: Exception | None = None

        if self._alert_matcher is not None:
            try:
                self._alert_matcher.match_document(doc, translated)
            except Exception as exc:
                logger.exception(
                    "Alert matching failed during enrichment for document_id=%s correlation=%s",
                    document_id,
                    get_correlation_id(),
                )
                _subtask_error = exc

        if self._intelligence is not None:
            try:
                results = self._intelligence.process_document(doc.id, translated)
                if results.get("succeeded", 0) == 0:
                    logger.warning(
                        "All intelligence tasks failed for document_id=%s correlation=%s",
                        document_id,
                        get_correlation_id(),
                    )
            except Exception as exc:
                logger.exception(
                    "Intelligence failed during enrichment for document_id=%s correlation=%s",
                    document_id,
                    get_correlation_id(),
                )
                if _subtask_error is None:
                    _subtask_error = exc

        if _subtask_error is not None:
            raise EnrichmentSubtaskError(
                f"Enrichment subtask failed for document_id={document_id}"
            ) from _subtask_error


def run_enrich_once(
    job_repo: PipelineJobRepository,
    worker: SlowWorker,
    worker_id: str = "enrich-worker",
    metrics: MetricsRegistry | None = None,
) -> bool:
    """Claim one ``enrich_document`` job and process it.

    Args:
        job_repo: Queue repository for claiming and updating jobs.
        worker: SlowWorker instance for document enrichment.
        worker_id: Identifier stamped on claimed jobs (for stale-lock tracking).
        metrics: Optional metrics registry; pass ``None`` to disable instrumentation.

    Returns:
        ``True`` if a job was claimed and processed, ``False`` if none available.
    """
    claimed = job_repo.claim_next(worker_id, job_types=_ALLOWED_JOB_TYPES)
    if claimed is None:
        return False

    job_id: UUID = claimed["id"]
    document_id: UUID = claimed["document_id"]
    job_type: str = claimed["job_type"]
    attempts: int = claimed["attempts"]
    max_attempts: int = claimed["max_attempts"]

    if metrics is not None:
        metrics.pipeline_jobs_claimed_total.labels(worker_type="enrich", job_type=job_type).inc()

    job_repo.mark_running_stage(job_id, "enrich")

    # Load pre-extracted text from the parse stage payload so the slow worker
    # does not need to call the extractor directly.
    payload = job_repo.get_payload(document_id)
    content_text = (payload.get("content_text", "") if payload else None) or ""

    start = time.monotonic()
    try:
        worker.process_document(document_id, content_text=content_text)
    except Exception as exc:
        elapsed = time.monotonic() - start
        error_type = type(exc).__name__
        if attempts < max_attempts:
            job_repo.mark_retry(job_id, exc, stage="enrich")
            job_repo.commit()
            if metrics is not None:
                metrics.pipeline_jobs_retried_total.labels(
                    worker_type="enrich", job_type=job_type
                ).inc()
                metrics.pipeline_job_duration_seconds.labels(
                    worker_type="enrich",
                    job_type=job_type,
                    stage="enrich",
                    outcome="retried",
                ).observe(elapsed)
            logger.info(
                "enrich job retried: worker_id=%s job_type=%s job_id=%s "
                "attempt=%d max_attempts=%d error_type=%s",
                worker_id,
                job_type,
                job_id,
                attempts,
                max_attempts,
                error_type,
            )
        else:
            job_repo.mark_dead_letter(job_id, exc)
            job_repo.commit()
            if metrics is not None:
                metrics.pipeline_jobs_dead_lettered_total.labels(
                    worker_type="enrich", job_type=job_type
                ).inc()
                metrics.pipeline_job_duration_seconds.labels(
                    worker_type="enrich",
                    job_type=job_type,
                    stage="enrich",
                    outcome="dead_lettered",
                ).observe(elapsed)
            logger.warning(
                "enrich job dead-lettered: worker_id=%s job_type=%s job_id=%s "
                "attempts=%d error_type=%s",
                worker_id,
                job_type,
                job_id,
                attempts,
                error_type,
            )
        return True

    elapsed = time.monotonic() - start
    job_repo.mark_succeeded(job_id)
    job_repo.commit()
    if metrics is not None:
        metrics.pipeline_jobs_succeeded_total.labels(worker_type="enrich", job_type=job_type).inc()
        metrics.pipeline_job_duration_seconds.labels(
            worker_type="enrich",
            job_type=job_type,
            stage="enrich",
            outcome="succeeded",
        ).observe(elapsed)
    logger.info(
        "enrich job succeeded: worker_id=%s job_type=%s job_id=%s attempt=%d",
        worker_id,
        job_type,
        job_id,
        attempts,
    )

    return True


def run_enrich_loop(
    job_repo: PipelineJobRepository,
    worker: SlowWorker,
    worker_id: str = "enrich-worker",
    poll_interval: float = 1.0,
    metrics: MetricsRegistry | None = None,
) -> None:
    """Run ``run_enrich_once`` in a loop until interrupted."""
    logger.info(
        "enrich worker started: worker_id=%s poll_interval=%.1f",
        worker_id,
        poll_interval,
    )
    try:
        while True:
            if metrics is not None:
                metrics.worker_heartbeat_timestamp_seconds.labels(
                    worker_type="enrich", worker_id=worker_id
                ).set_to_current_time()

            try:
                ran = run_enrich_once(job_repo, worker, worker_id=worker_id, metrics=metrics)
            except Exception as exc:
                logger.exception(
                    "unhandled enrich loop error: worker_id=%s error_type=%s",
                    worker_id,
                    type(exc).__name__,
                )
                time.sleep(poll_interval)
                continue

            if not ran:
                time.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("enrich worker shutting down: worker_id=%s", worker_id)


if __name__ == "__main__":
    from sqlalchemy import create_engine

    from services.intelligence.factory import build_llm_provider
    from services.intelligence.repository import IntelligenceRepository
    from services.search.factory import build_encoder
    from services.translation.ctranslate2_provider import CTranslate2OpusProvider
    from shared.config import Settings

    settings = Settings()
    engine = create_engine(settings.postgres_url)

    with engine.begin() as conn:
        doc_repo = DocumentRepository(conn)
        version_repo = TranslationVersionRepository(conn)
        layout_repo = LayoutBlockRepository(conn)
        qdrant_client = QdrantSearchClient(url=settings.qdrant_url)
        translator = LibreTranslateArgosProvider(base_url=settings.libretranslate_url)
        encoder = build_encoder(settings)

        intelligence_worker = IntelligenceWorker(
            repository=IntelligenceRepository(conn),
            ollama_client=build_llm_provider(settings),
            utility_model=settings.effective_utility_model,
        )

        # Construct high-quality translation provider when a bundle is configured (#731)
        high_provider = None
        if settings.translation_high_provider_bundle_path:
            try:
                high_provider = CTranslate2OpusProvider(
                    bundle_path=settings.translation_high_provider_bundle_path,
                    baseline=translator,
                )
                logger.info(
                    "High-quality translation provider loaded: pairs=%d",
                    len(high_provider.capabilities.get("language_pairs", [])),
                )
            except Exception:
                logger.warning(
                    "Failed to load high-quality translation provider from %s",
                    settings.translation_high_provider_bundle_path,
                    exc_info=True,
                )

        # Construct QE scorer when enabled (#733)
        qe_scorer = build_qe_scorer(
            enabled=settings.translation_qe_enabled,
            model_path=settings.translation_qe_model_path,
            low_score_threshold=settings.translation_qe_low_score_threshold,
        )

        worker = SlowWorker(
            document_repository=doc_repo,
            translator=translator,
            encoder=encoder,
            qdrant_client=qdrant_client,
            version_repository=version_repo,
            intelligence_worker=intelligence_worker,
            layout_repository=layout_repo,
            high_provider=high_provider,
            qe_scorer=qe_scorer,
        )

        run_enrich_loop(
            PipelineJobRepository(conn),
            worker,
            worker_id="enrich-worker",
        )
