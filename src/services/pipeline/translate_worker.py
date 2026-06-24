"""Translate stage consumer — translates extracted text and publishes embed."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from services.documents.layout_block_repository import LayoutBlockRepository
from services.documents.repository import DocumentRepository, TranslationVersionRepository
from services.extraction.language import LanguageDetector
from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.publisher import DocumentPublisher
from services.translation.client import _safe_str, build_translation_metadata
from services.translation.provider import TranslationProvider
from services.translation.segment_pipeline import run_segment_pipeline

logger = logging.getLogger(__name__)

_LANGUAGE_DETECTOR = LanguageDetector()

# LibreTranslate language packs shipped with the (air-gapped) deployment.
# Detection results outside this set are ignored so we never send an
# unsupported source code, which LibreTranslate rejects with HTTP 400.
_SUPPORTED_SOURCE_LANGUAGES = frozenset({"ar", "en", "es", "fr", "he", "ko", "ru", "th", "zh"})

# A handful of Han characters is a strong, length-independent signal that the
# text is Chinese — far more reliable here than statistical detectors.
_CJK_MIN_CHARS = 8


def _count_han(text: str) -> int:
    """Count CJK Unified Ideographs (Han characters) in *text*."""
    return sum(1 for ch in text if "一" <= ch <= "鿿")


def _detect_source_language(content_text: str) -> str | None:
    """Best-effort source language when the document's own is unknown.

    LibreTranslate's built-in ``auto`` detection is unreliable for CJK text — it
    reports English with zero confidence and returns the input unchanged,
    producing a "translation" that is still in the source language. Statistical
    detection (langdetect) also mis-fires when CJK is mixed with ASCII (e.g. a
    Chinese document peppered with English keywords gets labelled Vietnamese).

    So we first use a script-based shortcut for Han characters, then fall back
    to langdetect for everything else, normalising to a base code LibreTranslate
    accepts (e.g. ``zh-cn`` -> ``zh``). Results outside the supported set, or
    inconclusive detection, return ``None`` — leaving the existing ``auto``
    behaviour untouched.
    """
    if _count_han(content_text) >= _CJK_MIN_CHARS:
        return "zh" if "zh" in _SUPPORTED_SOURCE_LANGUAGES else None

    detected = _LANGUAGE_DETECTOR.detect(content_text)
    if not detected:
        return None
    base = detected.split("-")[0]
    return base if base in _SUPPORTED_SOURCE_LANGUAGES else None


def _build_fast_metadata(
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
    """Build translation metadata for fast-lane ingestion (#727, #728)."""
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
        quality_lane="fast",
        purpose="search",
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


class TranslateConsumer(BaseConsumer):
    queue_name = "document.translate.requested"
    worker_type = "translate-worker"

    def __init__(
        self,
        rabbit: Any,
        job_repo: PipelineJobRepository,
        publisher: DocumentPublisher,
        translator: TranslationProvider | None = None,
        version_repo: TranslationVersionRepository | None = None,
        doc_repo: DocumentRepository | None = None,
        layout_repo: LayoutBlockRepository | None = None,
        health_port: int = 8082,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
        self._publisher = publisher
        self._translator = translator
        self._version_repo = version_repo
        self._doc_repo = doc_repo
        self._layout_repo = layout_repo

    def handle_message(
        self,
        job_id: UUID,
        document_id: UUID,
        source_id: UUID,
        attempt: int,
        correlation_id: str,
        content_text: str = "",
        translated_text: str = "",
    ) -> None:
        doc = self._doc_repo.get_by_id(document_id) if self._doc_repo else None
        lang = doc.source_language if doc else None
        if lang == "":
            lang = None
        target_lang = (doc.target_language if doc else None) or "en"

        if not content_text:
            logger.debug("translate skipped: empty content_text for document_id=%s", document_id)
            self._job_repo.mark_running_stage(job_id, "translated")
            self._publisher.publish_embed(
                job_id=job_id,
                document_id=document_id,
                source_id=source_id,
                attempt=attempt,
                content_text=content_text,
            )
            return

        # When the document's source language was never determined upstream,
        # detect it here rather than relying on LibreTranslate's unreliable
        # ``auto`` mode (which silently no-ops on CJK text).
        if lang is None:
            lang = _detect_source_language(content_text)

        # Load layout blocks for segment-aware translation (#728)
        layout_blocks: list[dict[str, Any]] | None = None
        if self._layout_repo is not None and self._translator is not None:
            try:
                layout_blocks_raw = self._layout_repo.list_by_document(document_id)
                if layout_blocks_raw:
                    layout_blocks = [
                        {"text": block.text, "block_type": block.block_type}
                        for block in layout_blocks_raw
                        if block.text
                    ]
            except Exception:
                logger.debug(
                    "Layout block load failed for document_id=%s, "
                    "falling back to paragraph segmentation",
                    document_id,
                )
                layout_blocks = None

        translated = content_text
        validation_warnings: list[str] = []
        validation_segment_count = 0
        validation_failed = 0
        validation_ph_mismatch = 0
        validation_num_date = 0
        validation_len_outlier = 0
        if self._translator:
            translated, validation = run_segment_pipeline(
                content_text,
                translate_fn=self._translator.translate,
                source_lang=lang,
                target_lang=target_lang,
                layout_blocks=layout_blocks,
            )
            validation_segment_count = validation.segment_count
            validation_failed = validation.failed_segment_count
            validation_ph_mismatch = validation.placeholder_mismatch_count
            validation_num_date = validation.number_date_mismatch_count
            validation_len_outlier = validation.length_ratio_outlier_count
            validation_status = validation.validation_status
            if validation.warnings:
                validation_warnings = validation.warnings
            if not translated:
                translated = content_text

        self._job_repo.update_translated_text(document_id, translated)
        self._job_repo.mark_running_stage(job_id, "translated")

        did_translate = translated != content_text
        quality = "fast" if did_translate else None

        _version_id_str: str | None = None
        _vs_str: str | None = None
        if self._version_repo and did_translate:
            # Build translation metadata for fast-lane ingestion (#727, #728)
            _meta = _build_fast_metadata(
                translator=self._translator,
                source_language=lang,
                target_language=target_lang,
                input_text=content_text,
                output_text=translated,
                fallback_used=False,
                segment_count=validation_segment_count,
                failed_segment_count=validation_failed,
                placeholder_mismatch_count=validation_ph_mismatch,
                number_date_mismatch_count=validation_num_date,
                length_ratio_outlier_count=validation_len_outlier,
                pipeline_validation_status=validation_status,
                warnings=validation_warnings if validation_warnings else None,
            )
            _vs_raw = _meta.get("validation_status")
            _vs_str = str(_vs_raw) if _vs_raw in ("ok", "warning", "failed") else "ok"
            existing = self._version_repo.find_pending_or_running(document_id, target_lang)
            if existing is not None:
                _version_id_str = str(existing["id"])
                self._version_repo.update_version_status(
                    UUID(_version_id_str),
                    "available",
                    translated_text=translated,
                    metadata=_meta,
                    provider=_meta.get("provider"),
                )
            else:
                _version_id_str = str(
                    self._version_repo.create_version(
                        document_id=document_id,
                        label="Ingestion",
                        quality="fast",
                        request_type="ingestion",
                        target_language=target_lang,
                        translated_text=translated,
                        metadata=_meta,
                        provider=_meta.get("provider"),
                    )["id"]
                )

        # Defer document indexing status to the IndexConsumer — do not call
        # update_indexed here so the document only transitions to "indexed"
        # after Meilisearch indexing has actually succeeded.
        if self._doc_repo and translated and quality is not None:
            self._doc_repo.update_translation_quality(document_id, quality)
        # Early index pass (enrich=False): makes the document keyword-
        # searchable immediately and keeps search working if the embed stage
        # is degraded. Intelligence/alert fire on the embed worker's final
        # index pass (enrich=True) so enrichment runs exactly once (#694).
        self._publisher.publish_index(
            job_id=job_id,
            document_id=document_id,
            source_id=source_id,
            attempt=attempt,
            content_text=content_text,
            translated_text=translated,
            enrich=False,
        )
        self._publisher.publish_embed(
            job_id=job_id,
            document_id=document_id,
            source_id=source_id,
            attempt=attempt,
            content_text=content_text,
            translated_text=translated,
            translation_version_id=_version_id_str,
            translation_quality=quality,
            translation_validation_status=_vs_str,
        )


def main() -> None:
    import logging

    import sqlalchemy as sa

    from services.documents.layout_block_repository import LayoutBlockRepository
    from services.documents.repository import DocumentRepository, TranslationVersionRepository
    from services.pipeline.jobs import PipelineJobRepository
    from services.pipeline.publisher import DocumentPublisher
    from services.translation.libretranslate_provider import LibreTranslateArgosProvider
    from shared.config import Settings
    from shared.rabbit import RabbitClient

    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    engine = sa.create_engine(settings.postgres_url)
    connection = engine.connect()
    rabbit = RabbitClient(settings.rabbitmq_url, enabled=True)
    job_repo = PipelineJobRepository(connection)
    doc_repo = DocumentRepository(connection)
    publisher = DocumentPublisher(job_repo=job_repo, rabbit=rabbit)
    translator = LibreTranslateArgosProvider(base_url=settings.libretranslate_url)
    version_repo = TranslationVersionRepository(connection)
    layout_repo = LayoutBlockRepository(connection)
    consumer = TranslateConsumer(
        rabbit=rabbit,
        job_repo=job_repo,
        publisher=publisher,
        translator=translator,
        version_repo=version_repo,
        doc_repo=doc_repo,
        layout_repo=layout_repo,
    )
    consumer.run()
