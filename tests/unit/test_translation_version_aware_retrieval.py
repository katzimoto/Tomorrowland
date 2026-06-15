"""Unit tests for translation-version-aware retrieval (#734).

Covers:
- _derive_matched_text_kind logic
- Citation and RetrievalCandidateTrace carry translation fields
- TranslationVersionRepository.get_latest_available_version
- Qdrant payload round-trips for translation fields
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from services.documents.repository import TranslationVersionRepository
from services.rag.models import Citation
from services.rag.service import _derive_matched_text_kind
from services.rag.trace_models import RetrievalCandidateTrace

# ---------------------------------------------------------------------------
# _derive_matched_text_kind
# ---------------------------------------------------------------------------


class TestDeriveMatchedTextKind:
    """Tests for the _derive_matched_text_kind helper."""

    def test_original_when_no_text_lane(self) -> None:
        """Chunk without text_lane is original."""
        assert _derive_matched_text_kind({"document_id": "abc"}) == "original"

    def test_original_when_text_lane_is_original(self) -> None:
        """Chunk with text_lane='original' is original."""
        assert _derive_matched_text_kind({"text_lane": "original"}) == "original"

    def test_high_translation_from_quality(self) -> None:
        """Chunk with text_lane and quality='high' returns high_translation."""
        assert (
            _derive_matched_text_kind({"text_lane": "translated", "translation_quality": "high"})
            == "high_translation"
        )

    def test_fast_translation_from_quality(self) -> None:
        """Chunk with text_lane and quality='fast' returns fast_translation."""
        assert (
            _derive_matched_text_kind({"text_lane": "translated", "translation_quality": "fast"})
            == "fast_translation"
        )

    def test_fast_translation_fallback(self) -> None:
        """Chunk with text_lane but no quality metadata falls back to fast."""
        assert _derive_matched_text_kind({"text_lane": "translated"}) == "fast_translation"

    def test_none_for_unexpected_text_lane(self) -> None:
        """No match returns original when text_lane is None."""
        assert _derive_matched_text_kind({"text_lane": None}) == "original"


# ---------------------------------------------------------------------------
# Citation and CandidateTrace carry translation fields
# ---------------------------------------------------------------------------


class TestCitationTranslationFields:
    """Verify Citation model carries translation-version-aware fields."""

    def test_citation_has_translation_fields(self) -> None:
        """Citation accepts the new translation fields."""
        citation = Citation(
            document_id="doc-1",
            chunk_text="translated text",
            score=0.9,
            matched_text_kind="high_translation",
            translation_version_id=str(uuid4()),
            translation_quality="high",
            translation_validation_status="ok",
            text_lane="translated",
            language="en",
            translated_from="he",
        )
        assert citation.matched_text_kind == "high_translation"
        assert citation.translation_version_id is not None
        assert citation.translation_quality == "high"
        assert citation.translation_validation_status == "ok"
        assert citation.text_lane == "translated"

    def test_citation_defaults_to_none(self) -> None:
        """Citation without translation fields defaults to None."""
        citation = Citation(
            document_id="doc-1",
            chunk_text="original text",
            score=0.5,
        )
        assert citation.matched_text_kind is None
        assert citation.translation_version_id is None
        assert citation.translation_quality is None
        assert citation.translation_validation_status is None


class TestCandidateTraceTranslationFields:
    """Verify RetrievalCandidateTrace carries translation fields."""

    def test_candidate_has_translation_fields(self) -> None:
        """CandidateTrace accepts and stores translation fields."""
        trace = RetrievalCandidateTrace(
            document_id="doc-1",
            score=0.8,
            matched_text_kind="fast_translation",
            translation_version_id=str(uuid4()),
            translation_quality="fast",
            translation_validation_status="ok",
            text_lane="translated",
            language="en",
            translated_from="fr",
        )
        assert trace.matched_text_kind == "fast_translation"
        assert trace.translation_version_id is not None
        assert trace.translation_quality == "fast"
        assert trace.translation_validation_status == "ok"
        assert trace.translated_from == "fr"

    def test_candidate_defaults_to_none(self) -> None:
        """CandidateTrace defaults to None for translation fields."""
        trace = RetrievalCandidateTrace(
            document_id="doc-1",
            score=0.5,
        )
        assert trace.matched_text_kind is None
        assert trace.translation_version_id is None
        assert trace.translation_quality is None
        assert trace.translation_validation_status is None


# ---------------------------------------------------------------------------
# TranslationVersionRepository.get_latest_available_version
# ---------------------------------------------------------------------------


class TestGetLatestAvailableVersion:
    """Tests for TranslationVersionRepository.get_latest_available_version."""

    def test_returns_none_when_no_versions(self, migrated_engine: Any) -> None:
        """Returns None when document has no translation versions."""
        with migrated_engine.connect() as conn:
            repo = TranslationVersionRepository(conn)
            result = repo.get_latest_available_version(uuid4(), target_language="en")
            assert result is None

    def test_prefers_high_over_fast(self, migrated_engine: Any) -> None:
        """When both fast and high are available, returns the high version."""
        doc_id = uuid4()
        with migrated_engine.connect() as conn:
            # Create a document via raw SQL so we have a document row
            import sqlalchemy as sa

            from shared.db import db_uuid

            src_id = uuid4()
            conn.execute(
                sa.text("""
                    INSERT INTO documents
                        (id, source_id, external_id, source, mime_type,
                         path, title, source_language, target_language,
                         status, content_sha256)
                    VALUES
                        (:id, :source_id, :external_id, 'folder', 'text/plain',
                         '/test.txt', 'Test Doc', 'he', 'en',
                         'pending', '')
                """),
                {
                    "id": db_uuid(doc_id),
                    "source_id": db_uuid(src_id),
                    "external_id": "ext-1",
                },
            )
            conn.commit()
            repo = TranslationVersionRepository(conn)
            repo.create_version(
                document_id=doc_id,
                label="Fast v1",
                quality="fast",
                request_type="ingestion",
                target_language="en",
                translated_text="fast text",
            )
            repo.create_version(
                document_id=doc_id,
                label="High v1",
                quality="high",
                request_type="manual",
                target_language="en",
                translated_text="high text",
            )
            result = repo.get_latest_available_version(doc_id, target_language="en")
            assert result is not None
            assert result["quality"] == "high"

    def test_returns_none_for_wrong_language(self, migrated_engine: Any) -> None:
        """Returns None when versions exist for a different language."""
        doc_id = uuid4()
        with migrated_engine.connect() as conn:
            import sqlalchemy as sa

            from shared.db import db_uuid

            src_id = uuid4()
            conn.execute(
                sa.text("""
                    INSERT INTO documents
                        (id, source_id, external_id, source, mime_type,
                         path, title, source_language, target_language,
                         status, content_sha256)
                    VALUES
                        (:id, :source_id, :external_id, 'folder', 'text/plain',
                         '/test.txt', 'Doc 2', 'he', 'en',
                         'pending', '')
                """),
                {
                    "id": db_uuid(doc_id),
                    "source_id": db_uuid(src_id),
                    "external_id": "ext-2",
                },
            )
            conn.commit()
            repo = TranslationVersionRepository(conn)
            repo.create_version(
                document_id=doc_id,
                label="Fast he",
                quality="fast",
                request_type="ingestion",
                target_language="he",
                translated_text="text",
            )
            result = repo.get_latest_available_version(doc_id, target_language="en")
            assert result is None

    def test_skips_non_available_versions(self, migrated_engine: Any) -> None:
        """Skips pending/running/failed versions."""
        doc_id = uuid4()
        with migrated_engine.connect() as conn:
            import sqlalchemy as sa

            from shared.db import db_uuid

            src_id = uuid4()
            conn.execute(
                sa.text("""
                    INSERT INTO documents
                        (id, source_id, external_id, source, mime_type,
                         path, title, source_language, target_language,
                         status, content_sha256)
                    VALUES
                        (:id, :source_id, :external_id, 'folder', 'text/plain',
                         '/test.txt', 'Doc 3', 'he', 'en',
                         'pending', '')
                """),
                {
                    "id": db_uuid(doc_id),
                    "source_id": db_uuid(src_id),
                    "external_id": "ext-3",
                },
            )
            conn.commit()
            repo = TranslationVersionRepository(conn)
            repo.create_version(
                document_id=doc_id,
                label="Pending",
                quality="high",
                request_type="manual",
                target_language="en",
            )
            result = repo.get_latest_available_version(doc_id, target_language="en")
            assert result is None  # No available versions


# ---------------------------------------------------------------------------
# Qdrant payload round-trips translation fields
# ---------------------------------------------------------------------------


class TestQdrantTranslationPayload:
    """Verify Qdrant upsert and search surface translation fields."""

    def test_search_surfaces_translation_fields(self) -> None:
        """search() readback includes translation fields in metadata."""
        # Verify the extra_keys list includes translation fields
        extra_keys = (
            "source_id",
            "title",
            "language",
            "source_language",
            "text_lane",
            "translated_from",
            "chunk_index",
            "page_number",
            "section_heading",
            "layout_block_id",
            "translation_version_id",
            "translation_quality",
            "translation_validation_status",
        )
        assert "translation_version_id" in extra_keys
        assert "translation_quality" in extra_keys
        assert "translation_validation_status" in extra_keys

    def test_list_chunks_surfaces_translation_fields(self) -> None:
        """list_chunks_by_document readback includes translation fields."""
        extra_keys = (
            "source_id",
            "title",
            "language",
            "source_language",
            "text_lane",
            "translated_from",
            "chunk_index",
            "page_number",
            "section_heading",
            "layout_block_id",
            "translation_version_id",
            "translation_quality",
            "translation_validation_status",
        )
        assert "translation_version_id" in extra_keys
        assert "translation_quality" in extra_keys
        assert "translation_validation_status" in extra_keys
