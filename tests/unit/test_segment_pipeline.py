"""Unit tests for segment-aware translation pipeline (#728)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.translation.segment_pipeline import (
    PlaceholderMap,
    Segment,
    _split_oversized,
    _split_paragraphs,
    build_segments,
    protect_placeholders,
    reassemble,
    restore_placeholders,
    run_segment_pipeline,
    validate_segments,
)

# ---------------------------------------------------------------------------
# Segment builder
# ---------------------------------------------------------------------------


class TestBuildSegments:
    def test_empty_text_returns_empty(self) -> None:
        assert build_segments("") == []
        assert build_segments("   ") == []

    def test_paragraph_splitting(self) -> None:
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        segments = build_segments(text)
        assert len(segments) == 3
        assert segments[0].text == "First paragraph."
        assert segments[0].source == "paragraph"
        assert segments[0].index == 0
        assert segments[1].text == "Second paragraph."
        assert segments[2].text == "Third paragraph."

    def test_single_paragraph(self) -> None:
        text = "Just one paragraph."
        segments = build_segments(text)
        assert len(segments) == 1
        assert segments[0].text == "Just one paragraph."

    def test_paragraphs_with_extra_whitespace(self) -> None:
        text = "  First  \n\n\n\n  Second  "
        segments = build_segments(text)
        assert len(segments) == 2
        assert segments[0].text == "First"
        assert segments[1].text == "Second"

    def test_layout_blocks_preferred(self) -> None:
        text = "Full document text with paragraphs."
        layout_blocks = [
            {"text": "Block one text.", "block_type": "paragraph"},
            {"text": "Block two text.", "block_type": "heading"},
            {"text": "", "block_type": "figure"},  # empty — skipped
        ]
        segments = build_segments(text, layout_blocks)
        assert len(segments) == 2
        assert segments[0].text == "Block one text."
        assert segments[0].source == "layout_block"
        assert segments[1].text == "Block two text."
        assert segments[1].source == "layout_block"

    def test_layout_blocks_all_empty_falls_back(self) -> None:
        text = "Fallback paragraph one.\n\nFallback paragraph two."
        layout_blocks: list[dict[str, object]] = [
            {"text": "", "block_type": "figure"},
            {"text": None, "block_type": "figure"},
        ]
        segments = build_segments(text, layout_blocks)
        assert len(segments) == 2
        assert segments[0].source == "paragraph"

    def test_oversized_segment_split(self) -> None:
        """Very large paragraph should be split at sentence boundaries."""
        # Use realistic text: sentences separated by period+space, repeated to
        # create a long text that exceeds max_segment_chars.
        sentence = "The quick brown fox jumps over the lazy dog. "
        text = sentence * 200  # ~8800 chars
        segments = build_segments(text, max_segment_chars=3000)
        assert len(segments) > 1
        for seg in segments:
            assert len(seg.text) <= 3500  # allow some slack

    def test_layout_blocks_empty_list_falls_back(self) -> None:
        text = "Paragraph fallback."
        segments = build_segments(text, layout_blocks=[])
        assert len(segments) == 1
        assert segments[0].source == "paragraph"

    def test_paragraph_splitting_crlf(self) -> None:
        text = "First.\r\n\r\nSecond.\r\n\r\nThird."
        segments = build_segments(text)
        assert len(segments) == 3
        assert segments[0].text == "First."
        assert segments[1].text == "Second."

    def test_empty_paragraphs_filtered(self) -> None:
        text = "\n\n\nFirst.\n\n\n\n\nSecond.\n\n"
        segments = build_segments(text)
        assert len(segments) == 2


class TestSplitParagraphs:
    def test_basic(self) -> None:
        result = _split_paragraphs("A.\n\nB.\n\nC.")
        assert result == ["A.", "B.", "C."]

    def test_crlf(self) -> None:
        result = _split_paragraphs("A.\r\n\r\nB.")
        assert result == ["A.", "B."]

    def test_single(self) -> None:
        result = _split_paragraphs("Only one.")
        assert result == ["Only one."]


class TestSplitOversized:
    def test_no_split_when_under_limit(self) -> None:
        seg = Segment(index=0, text="Short text", source="paragraph")
        result = _split_oversized([seg], max_chars=5000)
        assert len(result) == 1
        assert result[0].text == "Short text"

    def test_split_when_over_limit(self) -> None:
        long_text = "A. B. " * 2000  # ~8000 chars
        seg = Segment(index=0, text=long_text, source="paragraph")
        result = _split_oversized([seg], max_chars=3000)
        assert len(result) > 1
        for r in result:
            assert len(r.text) <= 3500  # some slack

    def test_preserves_source(self) -> None:
        long_text = "A. B. " * 2000
        seg = Segment(index=5, text=long_text, source="layout_block")
        result = _split_oversized([seg], max_chars=3000)
        for r in result:
            assert r.source == "layout_block"


# ---------------------------------------------------------------------------
# Placeholder protector
# ---------------------------------------------------------------------------


class TestProtectPlaceholders:
    def test_url_protection(self) -> None:
        text = "Visit https://example.com/path for info."
        protected, ph_map = protect_placeholders(text)
        assert "https://example.com/path" not in protected
        assert "__PH" in protected
        assert len(ph_map.token_to_original) >= 1
        assert any(v == "https://example.com/path" for v in ph_map.token_to_original.values())

    def test_email_protection(self) -> None:
        text = "Contact user@example.com for help."
        protected, ph_map = protect_placeholders(text)
        assert "user@example.com" not in protected
        assert any(v == "user@example.com" for v in ph_map.token_to_original.values())

    def test_number_protection(self) -> None:
        text = "There are 42 items and 3.14 is pi."
        protected, ph_map = protect_placeholders(text)
        # Numbers should be protected
        assert len(ph_map.token_to_original) >= 2

    def test_date_protection(self) -> None:
        text = "Event on 2025-06-15 at 10:30."
        protected, ph_map = protect_placeholders(text)
        assert "2025-06-15" not in protected
        assert any(v == "2025-06-15" for v in ph_map.token_to_original.values())

    def test_currency_protection(self) -> None:
        text = "Price: $1,234.56 and €50.00"
        protected, ph_map = protect_placeholders(text)
        assert "$1,234.56" not in protected
        assert any(v == "$1,234.56" for v in ph_map.token_to_original.values())

    def test_ticket_id_protection(self) -> None:
        text = "See ticket PROJ-12345 for details."
        protected, ph_map = protect_placeholders(text)
        assert "PROJ-12345" not in protected
        assert any(v == "PROJ-12345" for v in ph_map.token_to_original.values())

    def test_multiple_placeholders(self) -> None:
        text = "Visit https://a.com or email x@y.com about ticket TASK-42."
        protected, ph_map = protect_placeholders(text)
        assert "https://a.com" not in protected
        assert "x@y.com" not in protected
        assert "TASK-42" not in protected
        assert len(ph_map.token_to_original) >= 3

    def test_no_placeholders(self) -> None:
        text = "Plain text without any special patterns."
        protected, ph_map = protect_placeholders(text)
        assert protected == text
        assert len(ph_map.token_to_original) == 0

    def test_type_counts(self) -> None:
        text = "See https://a.com and https://b.com and call 555-1234"
        _protected, ph_map = protect_placeholders(text)
        assert ph_map.type_counts.get("url", 0) >= 2

    def test_hebrew_text_with_numbers(self) -> None:
        text = "יש 42 תפוחים ו-3.14 זה פאי"
        protected, ph_map = protect_placeholders(text)
        assert "42" not in protected
        assert any(v == "42" for v in ph_map.token_to_original.values())

    def test_chinese_text_with_url(self) -> None:
        text = "访问 https://example.cn 了解更多"
        protected, ph_map = protect_placeholders(text)
        assert "https://example.cn" not in protected

    def test_overlapping_placeholders_longest_wins(self) -> None:
        """ISO date should be matched before a plain number within it."""
        text = "Date: 2025-06-15"
        protected, ph_map = protect_placeholders(text)
        assert "2025-06-15" not in protected
        # Should be one token for the whole date, not separate numbers
        assert any(v == "2025-06-15" for v in ph_map.token_to_original.values())

    def test_placeholder_map_roundtrip(self) -> None:
        text = "URL: https://test.com, Email: a@b.com, ID: PRJ-99."
        protected, ph_map = protect_placeholders(text)
        restored, mismatches = restore_placeholders(protected, ph_map)
        assert mismatches == 0
        assert restored == text


# ---------------------------------------------------------------------------
# Placeholder restoration
# ---------------------------------------------------------------------------


class TestRestorePlaceholders:
    def test_restore_all(self) -> None:
        ph_map = PlaceholderMap(
            token_to_original={"__PH0__": "https://test.com", "__PH1__": "42"},
        )
        result, mismatches = restore_placeholders("Go to __PH0__ page __PH1__", ph_map)
        assert result == "Go to https://test.com page 42"
        assert mismatches == 0

    def test_missing_token_counts_mismatch(self) -> None:
        ph_map = PlaceholderMap(
            token_to_original={"__PH0__": "https://test.com", "__PH1__": "42"},
        )
        # __PH0__ was lost during translation
        result, mismatches = restore_placeholders("Go to page __PH1__", ph_map)
        assert mismatches == 1
        assert "https://test.com" not in result

    def test_multiple_occurrences_single_token(self) -> None:
        """Each token appears once — restore replaces first occurrence."""
        ph_map = PlaceholderMap(
            token_to_original={"__PH0__": "value"},
        )
        result, mismatches = restore_placeholders("__PH0__ and __PH0__", ph_map)
        # Only the first replacement happens with replace(..., 1)
        assert result == "value and __PH0__"
        assert mismatches == 0


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class TestValidateSegments:
    def test_all_ok(self) -> None:
        segments = [Segment(index=0, text="Hello"), Segment(index=1, text="World")]
        translated = ["Bonjour", "Monde"]
        failed: set[int] = set()
        ph_maps = [PlaceholderMap(), PlaceholderMap()]
        result = validate_segments(segments, translated, failed, ph_maps, 0)
        assert result.validation_status == "ok"
        assert result.failed_segment_count == 0
        assert result.warnings == []

    def test_some_failed(self) -> None:
        segments = [
            Segment(index=0, text="A"),
            Segment(index=1, text="B"),
            Segment(index=2, text="C"),
        ]
        translated = ["A", "B", "C"]
        failed = {1}
        ph_maps = [PlaceholderMap(), PlaceholderMap(), PlaceholderMap()]
        result = validate_segments(segments, translated, failed, ph_maps, 0)
        assert result.validation_status == "warning"
        assert result.failed_segment_count == 1
        assert len(result.warnings) >= 1

    def test_all_failed(self) -> None:
        segments = [Segment(index=0, text="A"), Segment(index=1, text="B")]
        translated = ["A", "B"]
        failed = {0, 1}
        ph_maps = [PlaceholderMap(), PlaceholderMap()]
        result = validate_segments(segments, translated, failed, ph_maps, 0)
        assert result.validation_status == "failed"
        assert result.failed_segment_count == 2

    def test_placeholder_mismatches(self) -> None:
        segments = [Segment(index=0, text="Hello")]
        translated = ["Hello"]
        failed: set[int] = set()
        ph_maps = [PlaceholderMap()]
        result = validate_segments(segments, translated, failed, ph_maps, 5)
        assert result.placeholder_mismatch_count == 5
        assert result.validation_status == "warning"

    def test_length_outliers(self) -> None:
        """Very short translation of a long segment should be flagged."""
        segments = [Segment(index=0, text="A" * 1000)]
        translated = ["B"]  # extremely short compared to original
        failed: set[int] = set()
        ph_maps = [PlaceholderMap()]
        result = validate_segments(segments, translated, failed, ph_maps, 0)
        assert result.length_ratio_outlier_count >= 1

    def test_number_date_mismatch(self) -> None:
        segments = [Segment(index=0, text="There are 42 items")]
        translated = ["There are items"]  # number lost
        failed: set[int] = set()
        orig_protected, ph_map = protect_placeholders("There are 42 items")
        result = validate_segments(segments, translated, failed, [ph_map], 0)
        assert result.number_date_mismatch_count >= 1


# ---------------------------------------------------------------------------
# Reassembler
# ---------------------------------------------------------------------------


class TestReassemble:
    def test_join_segments(self) -> None:
        segments = [Segment(index=0, text="A"), Segment(index=1, text="B")]
        translated = ["A'", "B'"]
        result = reassemble(translated, segments, "A\n\nB")
        assert result == "A'\n\nB'"

    def test_empty_returns_original(self) -> None:
        segments: list[Segment] = []
        result = reassemble([], segments, "original")
        assert result == "original"

    def test_mismatch_returns_original(self) -> None:
        segments = [Segment(index=0, text="A")]
        translated = ["A'", "extra"]
        result = reassemble(translated, segments, "original")
        assert result == "original"


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------


class TestRunSegmentPipeline:
    def test_basic_translation(self) -> None:
        mock_translate = MagicMock()
        mock_translate.return_value = "Translated text"

        result, validation = run_segment_pipeline(
            "Hello world.",
            translate_fn=mock_translate,
            source_lang="en",
            target_lang="fr",
        )

        assert "Translated" in result
        assert validation.segment_count == 1
        assert validation.validation_status == "ok"

    def test_multi_paragraph(self) -> None:
        mock_translate = MagicMock()
        mock_translate.return_value = "Translated"

        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result, validation = run_segment_pipeline(
            text,
            translate_fn=mock_translate,
            source_lang="en",
            target_lang="fr",
        )

        assert mock_translate.call_count == 3
        assert validation.segment_count == 3

    def test_with_layout_blocks(self) -> None:
        mock_translate = MagicMock()
        mock_translate.return_value = "Translated block"

        layout_blocks = [
            {"text": "Block A text.", "block_type": "paragraph"},
            {"text": "Block B text.", "block_type": "heading"},
        ]
        result, validation = run_segment_pipeline(
            "Original full text",
            translate_fn=mock_translate,
            source_lang="en",
            target_lang="fr",
            layout_blocks=layout_blocks,
        )

        assert mock_translate.call_count == 2
        assert validation.segment_count == 2

    def test_partial_failure(self) -> None:
        call_count = [0]

        def translate_second_fails(text: str, source: str | None, target: str) -> str:
            call_count[0] += 1
            if call_count[0] == 2:
                return text  # simulate no-op translation (failure)
            return "Translated: " + text

        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result, validation = run_segment_pipeline(
            text,
            translate_fn=translate_second_fails,
            source_lang="en",
            target_lang="fr",
        )

        assert validation.failed_segment_count == 1
        assert validation.validation_status == "warning"
        # The failed segment should use original text
        assert "Second paragraph" in result

    def test_empty_text(self) -> None:
        # Empty text builds no segments → falls back to whole-text translate_fn
        mock_translate = MagicMock()
        mock_translate.return_value = ""
        result, validation = run_segment_pipeline(
            "",
            translate_fn=mock_translate,
            source_lang="en",
            target_lang="fr",
        )
        mock_translate.assert_called_once()
        assert result == ""
        assert validation.segment_count == 0

    def test_translation_exception_propagates(self) -> None:
        """Hard exceptions from translate_fn propagate — callers handle retry."""
        call_count = [0]

        def translate_second_crashes(text: str, source: str | None, target: str) -> str:
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("Provider unavailable")
            return "Translated: " + text

        text = "A.\n\nB.\n\nC."
        with pytest.raises(RuntimeError, match="Provider unavailable"):
            run_segment_pipeline(
                text,
                translate_fn=translate_second_crashes,
                source_lang="en",
                target_lang="fr",
            )

    def test_placeholder_protection_in_pipeline(self) -> None:
        def mock_translate(text: str, source: str | None, target: str) -> str:
            # Simulate a translation that drops some placeholders but keeps others.
            # Remove just one specific token to trigger mismatch detection.
            if "__PH" in text:
                # Drop the first placeholder token only
                import re

                return re.sub(r"__PH\d+__", "[LOST]", text, count=1)
            return "Translated: " + text

        text = "Visit https://example.com and https://other.com for details."
        result, validation = run_segment_pipeline(
            text,
            translate_fn=mock_translate,
            source_lang="en",
            target_lang="fr",
        )

        # At least one URL should still be present (the one whose token survived)
        assert "https://" in result
        # At least one placeholder mismatch should be detected
        assert validation.placeholder_mismatch_count >= 1

    def test_hebrew_to_english(self) -> None:
        mock_translate = MagicMock()
        mock_translate.return_value = "This is a test document."

        text = "זהו מסמך בדיקה.\n\nפסקה שנייה."
        result, validation = run_segment_pipeline(
            text,
            translate_fn=mock_translate,
            source_lang="he",
            target_lang="en",
        )

        assert validation.segment_count == 2
        assert mock_translate.call_count == 2

    def test_mixed_hebrew_english(self) -> None:
        mock_translate = MagicMock()
        mock_translate.return_value = "Translated mixed text"

        text = "English text here.\n\nטקסט בעברית כאן."
        result, validation = run_segment_pipeline(
            text,
            translate_fn=mock_translate,
            source_lang="he",
            target_lang="en",
        )

        assert validation.segment_count == 2

    def test_urls_emails_numbers_in_pipeline(self) -> None:
        mock_translate = MagicMock()
        mock_translate.side_effect = lambda t, s, tg: "Translated: " + t

        text = (
            "Contact user@example.com or visit https://test.com.\n\n"
            "Price: $99.99. Date: 2025-06-15. Ticket: PROJ-12345."
        )
        result, validation = run_segment_pipeline(
            text,
            translate_fn=mock_translate,
            source_lang="en",
            target_lang="fr",
        )

        # All placeholders should be preserved
        assert "user@example.com" in result
        assert "https://test.com" in result
        assert "PROJ-12345" in result

    def test_all_segments_fail(self) -> None:
        def translate_noop(text: str, source: str | None, target: str) -> str:
            return text  # all segments return original

        text = "First.\n\nSecond."
        result, validation = run_segment_pipeline(
            text,
            translate_fn=translate_noop,
            source_lang="en",
            target_lang="fr",
        )

        assert validation.failed_segment_count == 2
        assert validation.validation_status == "failed"

    def test_validation_metadata_includes_all_fields(self) -> None:
        mock_translate = MagicMock()
        mock_translate.return_value = "Translated"

        _result, validation = run_segment_pipeline(
            "Hello world.\n\nWith URL https://test.com.",
            translate_fn=mock_translate,
            source_lang="en",
            target_lang="fr",
        )

        assert hasattr(validation, "segment_count")
        assert hasattr(validation, "failed_segment_count")
        assert hasattr(validation, "placeholder_mismatch_count")
        assert hasattr(validation, "number_date_mismatch_count")
        assert hasattr(validation, "length_ratio_outlier_count")
        assert hasattr(validation, "validation_status")
        assert hasattr(validation, "warnings")
        assert validation.validation_status in ("ok", "warning", "failed")

    def test_whitespace_only_text(self) -> None:
        # Whitespace-only builds no segments → falls back to whole-text translate_fn
        mock_translate = MagicMock()
        mock_translate.return_value = "   \n\n   "
        result, validation = run_segment_pipeline(
            "   \n\n   ",
            translate_fn=mock_translate,
            source_lang="en",
            target_lang="fr",
        )
        mock_translate.assert_called_once()
        assert validation.segment_count == 0
