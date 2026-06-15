"""Synchronous document ingestion pipeline."""

from __future__ import annotations

import hashlib
import logging
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Any, NamedTuple
from uuid import UUID

from services.alerts.service import AlertMatcher
from services.chunking.splitter import chunk_text, resolve_chunk_locations
from services.documents.layout_block_repository import LayoutBlockRepository
from services.documents.repository import DocumentRelationshipRepository, DocumentRepository
from services.extraction.base import AttachmentData, ExtractionResult
from services.extraction.language import LanguageDetector
from services.extraction.registry import ExtractorRegistry
from services.intelligence.worker import IntelligenceWorker
from services.search.encoder import TextEncoder
from services.search.meili_provider import MeilisearchSearchProvider
from services.search.meili_types import ChunkMetadata, SearchChunkRecord
from services.search.qdrant import QdrantSearchClient
from services.translation.provider import TranslationProvider
from shared.correlation import get_correlation_id
from shared.metrics import MetricsRegistry

logger = logging.getLogger(__name__)


def _maybe_delete_connector_temp(path: str) -> None:
    """Delete *path* if it lives inside the system temporary directory.

    Connectors that download files to a temp location (SMB, Atlassian
    attachment downloads) set ``doc.path`` to a temp file the worker owns
    after extraction.  Folder and NiFi staged files live outside the system
    temp directory and are intentionally left untouched.

    Errors are logged but never fatal — a failed cleanup is not worth
    interrupting the pipeline for.
    """
    try:
        p = Path(path)
        if p.is_relative_to(Path(tempfile.gettempdir())):
            p.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning(
            "Failed to delete connector temp file path=%s error_type=%s",
            path,
            exc.__class__.__name__,
        )


class ProcessResult(NamedTuple):
    """Result returned by process_document on success."""

    extracted_text: str
    translated_text: str
    translation_quality: str | None  # "fast" when translation changed the text; None otherwise


class PipelineWorker:
    """Orchestrate extraction, translation, chunking, embedding, and indexing."""

    def __init__(
        self,
        document_repository: DocumentRepository,
        extractor_registry: ExtractorRegistry,
        translator: TranslationProvider,
        encoder: TextEncoder,
        qdrant_client: QdrantSearchClient,
        meili_provider: MeilisearchSearchProvider | None = None,
        intelligence_worker: IntelligenceWorker | None = None,
        alert_matcher: AlertMatcher | None = None,
        metrics: MetricsRegistry | None = None,
        embedding_max_tokens: int | None = None,
        lang_detector: LanguageDetector | None = None,
        enable_language_detection: bool = True,
        attachment_store: Path | None = None,
    ) -> None:
        self._doc_repo = document_repository
        self._extractor = extractor_registry
        self._translator = translator
        self._encoder = encoder
        self._qdrant = qdrant_client
        self._meili = meili_provider
        self._intelligence = intelligence_worker
        self._alert_matcher = alert_matcher
        self._metrics = metrics
        self._embedding_max_tokens = embedding_max_tokens
        self._lang_detector = lang_detector or LanguageDetector()
        self._enable_language_detection = enable_language_detection
        self._attachment_store = attachment_store

    @property
    def document_repository(self) -> DocumentRepository:
        return self._doc_repo

    @property
    def intelligence_worker(self) -> IntelligenceWorker | None:
        return self._intelligence

    @property
    def alert_matcher(self) -> AlertMatcher | None:
        return self._alert_matcher

    def process_document(
        self, document_id: UUID, pre_extracted_text: str | None = None
    ) -> ProcessResult | None:
        """Run the full pipeline for a single document.

        When *pre_extracted_text* is supplied it is used directly, bypassing
        the file extractor. This is required for connectors that fetch content
        over a network API rather than from a local file path.

        On success returns a :class:`ProcessResult` with both the raw extracted
        text and the translated text so the caller can persist them. On any
        unhandled exception the document status is set to ``"failed"`` and the
        exception is re-raised.
        """
        try:
            result = self._run(document_id, pre_extracted_text=pre_extracted_text)
            if self._metrics is not None:
                self._metrics.pipeline_documents_total.labels("document", "success").inc()
            return result
        except Exception:
            if self._metrics is not None:
                self._metrics.pipeline_documents_total.labels("document", "failure").inc()
            logger.exception(
                "Pipeline failed for document_id=%s correlation=%s",
                document_id,
                get_correlation_id(),
            )
            self._doc_repo.update_status(document_id, "failed")
            raise

    def _run(
        self,
        document_id: UUID,
        pre_extracted_text: str | None = None,
        _seen: frozenset[str] | None = None,
    ) -> ProcessResult:
        doc = self._doc_repo.get_by_id(document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")

        allowed_group_ids = [
            str(group_id) for group_id in self._doc_repo.source_group_ids(doc.source_id)
        ]

        # 1. Extract — use pre-extracted text when available (API sources),
        #    otherwise read from the local file path (folder sources).
        start = time.perf_counter()
        _extraction_result: ExtractionResult | None = None
        if pre_extracted_text is not None:
            text = pre_extracted_text
        elif doc.path is not None:
            _extraction_result = self._extractor.extract(Path(doc.path), doc.mime_type)
            text = _extraction_result.text
            # Release connector-owned temp files (SMB downloads, Atlassian
            # attachment downloads) immediately after text is extracted.
            # Folder and NiFi staged files live outside the system temp dir
            # and are not affected.
            _maybe_delete_connector_temp(doc.path)
        else:
            raise ValueError(
                f"Document {document_id} has neither a file path nor pre_extracted_text"
            )
        if self._metrics is not None:
            self._metrics.pipeline_stage_duration_seconds.labels("extraction").observe(
                time.perf_counter() - start
            )
            self._metrics.pipeline_documents_total.labels("extraction", "success").inc()
            if doc.path is not None:
                with suppress(OSError):
                    self._metrics.pipeline_document_bytes.labels(doc.source).observe(
                        float(Path(doc.path).stat().st_size)
                    )

        # 1b. Auto-detect source language when the connector did not supply one.
        if self._enable_language_detection and doc.source_language is None:
            detected_lang = self._lang_detector.detect(text)
            if detected_lang:
                self._doc_repo.update_source_language(document_id, detected_lang)
                doc = doc.model_copy(update={"source_language": detected_lang})

        # 2. Translate (falls back to original text on failure)
        start = time.perf_counter()
        if doc.source_language is None and text.strip():
            logger.warning(
                "source_language not set for document_id=%s; LibreTranslate will use "
                "auto-detect which may fail — configure source_language on the ingestion source",
                document_id,
            )
        translated = self._translator.translate(
            text, source_lang=doc.source_language, target_lang=doc.target_language or "en"
        )
        # "fast" only when translation produced a non-empty result that differs from the input.
        # Empty or identical output means LibreTranslate returned unchanged / failed auto-detect.
        translation_quality: str | None = "fast" if (translated and translated != text) else None
        if translation_quality is None and text.strip():
            logger.warning(
                "Translation returned unchanged text for document_id=%s source_language=%s — "
                "LibreTranslate may have failed auto-detect or the document is already in the "
                "target language. No translation version will be created.",
                document_id,
                doc.source_language,
            )
        if self._metrics is not None:
            self._metrics.translation_duration_seconds.labels("pipeline").observe(
                time.perf_counter() - start
            )
            self._metrics.translation_requests_total.labels("pipeline", "success").inc()
            self._metrics.translation_characters_total.labels("pipeline").inc(len(text))

        # 3. Chunk both original and translated text separately so each
        #    Meilisearch record pairs original chunk text (content) with its
        #    corresponding translated chunk (content_en).
        start = time.perf_counter()
        original_chunks = list(
            chunk_text(
                text,
                language=doc.source_language,
                max_tokens=self._embedding_max_tokens,
            )
        )
        translated_chunks = list(
            chunk_text(
                translated,
                language=doc.target_language,
                max_tokens=self._embedding_max_tokens,
            )
        )
        if self._metrics is not None:
            self._metrics.pipeline_stage_duration_seconds.labels("chunking").observe(
                time.perf_counter() - start
            )
            self._metrics.pipeline_chunks_total.labels("success").inc(
                max(len(original_chunks), len(translated_chunks))
            )

        # 5. Index chunks in Meilisearch when configured.
        self._index_meilisearch(
            document_id=document_id,
            doc=doc,
            original_chunks=original_chunks,
            translated_chunks=translated_chunks,
            allowed_group_ids=allowed_group_ids,
            text=text,
            translated=translated,
        )

        # 6. Index chunks in Qdrant (vector indexing is degraded/best-effort).
        self._index_qdrant(
            document_id=document_id,
            doc=doc,
            original_chunks=original_chunks,
            translated_chunks=translated_chunks,
            _extraction_result=_extraction_result,
            allowed_group_ids=allowed_group_ids,
            text=text,
        )

        # 7. Update status after text indexing has succeeded. Vector/Meilisearch
        #    indexing may be degraded; a future async job model should persist
        #    stage-specific retry state for those failures.
        self._doc_repo.update_indexed(document_id, "indexed", translation_quality)

        # 8. Process email/archive attachments as child documents (best-effort).
        #     Attachments are already extracted into _extraction_result by the
        #     extractor itself — the pipeline is fully agnostic to file type here.
        #     _seen tracks SHA-256 hashes of content already processed in this
        #     call chain to break circular references (e.g. ZIP-A → ZIP-B → ZIP-A).
        if _extraction_result is not None and _extraction_result.attachments:
            try:
                self._process_attachments(
                    document_id, doc, _extraction_result.attachments, _seen or frozenset()
                )
            except Exception:
                logger.exception(
                    "Attachment processing failed for document_id=%s correlation=%s",
                    document_id,
                    get_correlation_id(),
                )

        return ProcessResult(
            extracted_text=text,
            translated_text=translated,
            translation_quality=translation_quality,
        )

    def _index_meilisearch(
        self,
        *,
        document_id: UUID,
        doc: Any,
        original_chunks: list[str],
        translated_chunks: list[str],
        allowed_group_ids: list[str],
        text: str,
        translated: str,
    ) -> None:
        """Index chunks in Meilisearch (best-effort, failures are logged only)."""
        if self._meili is None:
            return
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
                    content_en=tran_chunk if translated != text else None,
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
                start = time.perf_counter()
                self._meili.index_batch(meili_records)
                if self._metrics is not None:
                    self._metrics.search_backend_duration_seconds.labels(
                        "meilisearch", "index"
                    ).observe(time.perf_counter() - start)
                    self._metrics.search_index_documents.labels("meilisearch").inc()
        except Exception as exc:
            logger.error(
                "Meilisearch indexing failed for document_id=%s error_type=%s correlation=%s",
                document_id,
                exc.__class__.__name__,
                get_correlation_id(),
            )

    def _index_qdrant(
        self,
        *,
        document_id: UUID,
        doc: Any,
        original_chunks: list[str],
        translated_chunks: list[str],
        _extraction_result: ExtractionResult | None,
        allowed_group_ids: list[str],
        text: str,
    ) -> None:
        """Index chunks in Qdrant (degraded/best-effort; failures are logged only)."""
        try:
            qdrant_chunks: list[dict[str, Any]] = []

            def _build_chunk(
                chunk_text_content: str,
                vector: list[float],
                idx: int,
                *,
                lang: str | None,
                suffix: str,
                page_number: int | None = None,
                section_heading: str | None = None,
            ) -> dict[str, Any]:
                entry: dict[str, Any] = {
                    "chunk_id": f"{document_id}-{suffix}-{idx}",
                    "document_id": str(document_id),
                    "group_id": allowed_group_ids,
                    "chunk_index": idx,
                    "text": chunk_text_content,
                    "vector": vector,
                    "source_id": str(doc.source_id),
                }
                if doc.title:
                    entry["title"] = doc.title
                if lang:
                    entry["language"] = lang
                if page_number is not None:
                    entry["page_number"] = page_number
                if section_heading is not None:
                    entry["section_heading"] = section_heading
                return entry

            location_segments_dicts: list[dict[str, Any]] = []
            if _extraction_result is not None and _extraction_result.location_segments:
                location_segments_dicts = [
                    s.to_dict() for s in _extraction_result.location_segments
                ]
            orig_locations = resolve_chunk_locations(text, original_chunks, location_segments_dicts)

            chunk_texts: list[str] = []
            chunk_meta: list[dict[str, Any]] = []

            for idx, chunk_text_content in enumerate(original_chunks):
                chunk_texts.append(chunk_text_content)
                loc = orig_locations[idx] if idx < len(orig_locations) else {}
                chunk_meta.append(
                    {
                        "lang": doc.source_language,
                        "suffix": "orig",
                        "idx": idx,
                        "page_number": loc.get("page_number"),
                        "section_heading": loc.get("section_heading"),
                    }
                )

            for idx, chunk_text_content in enumerate(translated_chunks):
                chunk_texts.append(chunk_text_content)
                chunk_meta.append(
                    {
                        "lang": doc.target_language,
                        "suffix": "trans",
                        "idx": idx,
                        "page_number": None,
                        "section_heading": None,
                    }
                )

            vectors = self._encoder.encode_batch(chunk_texts)

            for i, meta in enumerate(chunk_meta):
                qdrant_chunks.append(
                    _build_chunk(
                        chunk_texts[i],
                        vectors[i],
                        meta["idx"],
                        lang=meta["lang"],
                        suffix=meta["suffix"],
                        page_number=meta.get("page_number"),
                        section_heading=meta.get("section_heading"),
                    )
                )

            if qdrant_chunks:
                from services.rag.layout_hierarchy import resolve_chunk_layout_block_ids

                try:
                    layout_repo = LayoutBlockRepository(self._doc_repo._connection)
                    resolve_chunk_layout_block_ids(qdrant_chunks, document_id, layout_repo)
                except Exception:
                    logger.debug(
                        "layout_block_id resolution skipped for document_id=%s",
                        document_id,
                    )

                start = time.perf_counter()
                self._qdrant.upsert_chunks(qdrant_chunks, delete_existing=True)
                if self._metrics is not None:
                    self._metrics.search_backend_duration_seconds.labels(
                        "qdrant", "upsert"
                    ).observe(time.perf_counter() - start)
                    self._metrics.search_index_documents.labels("qdrant").inc()
        except Exception as exc:
            logger.error(
                "Vector indexing failed for document_id=%s error_type=%s correlation=%s",
                document_id,
                exc.__class__.__name__,
                get_correlation_id(),
            )

    def _process_attachments(
        self,
        parent_id: UUID,
        parent_doc: Any,
        attachments: list[AttachmentData],
        _seen: frozenset[str],
    ) -> None:
        """Create a child document and run the pipeline for each attachment."""
        for att in attachments:
            sha256 = hashlib.sha256(att.data).hexdigest()
            if sha256 in _seen:
                logger.debug(
                    "Skipping duplicate attachment filename=%s parent_id=%s sha256=%s",
                    att.filename,
                    parent_id,
                    sha256,
                )
                continue

            # Skip attachment types that genuinely cannot yield text.
            # Use has_extractor() so that MIME aliases (e.g. application/yaml →
            # text/plain) are resolved before the check.  Types with no specific
            # extractor fall through to GenericExtractor, which handles text
            # files with uncommon MIME types — those should NOT be skipped.
            # Only truly unextractable types (images without OCR, audio, video)
            # will have no registered extractor and no alias, so we skip them.
            if not self._extractor.has_extractor(att.mime_type):
                logger.debug(
                    "Skipping attachment with unextractable mime_type=%s filename=%s parent_id=%s",
                    att.mime_type,
                    att.filename,
                    parent_id,
                )
                continue
            try:
                suffix = Path(att.filename).suffix or ".bin"
                # Prefer a permanent location inside files_root so the download
                # endpoint can serve the original file later.  Fall back to a
                # temp file (deleted after pipeline) when no store is configured.
                if self._attachment_store is not None:
                    att_dir = self._attachment_store / sha256[:2]
                    att_dir.mkdir(parents=True, exist_ok=True)
                    att_path = att_dir / f"{sha256}{suffix}"
                    att_path.write_bytes(att.data)
                    tmp_path = str(att_path)
                    persistent = True
                else:
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                        tmp.write(att.data)
                        tmp_path = tmp.name
                    persistent = False

                child_external_id = (
                    f"{parent_doc.external_id}::attachment::{att.filename}::{sha256[:12]}"
                )
                child_doc = self._doc_repo.create(
                    source_id=parent_doc.source_id,
                    external_id=child_external_id,
                    source=parent_doc.source,
                    mime_type=att.mime_type,
                    path=tmp_path,
                    title=att.filename,
                    source_language=parent_doc.source_language,
                    metadata={"parent_document_id": str(parent_id)},
                )
                if child_doc is None:
                    # Already ingested — dedup hit
                    if not persistent:
                        Path(tmp_path).unlink(missing_ok=True)
                    continue

                rel_repo = DocumentRelationshipRepository(self._doc_repo._connection)
                rel_type = (
                    "email_attachment"
                    if parent_doc.mime_type in ("message/rfc822", "application/vnd.ms-outlook")
                    else "archive_child"
                )
                rel_repo.create_relationship(parent_id, child_doc.id, rel_type, att.filename)

                try:
                    self._run(child_doc.id, _seen=_seen | {sha256})
                    logger.info(
                        "Attachment processed: parent_id=%s child_id=%s filename=%s",
                        parent_id,
                        child_doc.id,
                        att.filename,
                    )
                except Exception:
                    logger.exception(
                        "Attachment pipeline failed: parent_id=%s filename=%s child_id=%s",
                        parent_id,
                        att.filename,
                        child_doc.id,
                    )
                finally:
                    if not persistent:
                        Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                logger.exception(
                    "Failed to create child document for attachment: parent_id=%s filename=%s",
                    parent_id,
                    att.filename,
                )
