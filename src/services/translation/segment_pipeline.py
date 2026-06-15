"""Segment-aware translation pipeline with placeholder protection and validation.

Shared by both fast (ingestion) and high (enrichment) lanes.  Replaces the
previous whole-document translation approach with a pipeline that:

1. Builds segments from layout blocks or paragraph boundaries
2. Protects placeholders (URLs, emails, numbers, dates, etc.)
3. Translates each segment individually through the provider
4. Validates placeholder preservation and segment quality
5. Reassembles the translated text with restored placeholders

Partial segment failures do not block the pipeline — the original text is used
for failed segments and validation metadata records the issue.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Placeholder patterns
# ---------------------------------------------------------------------------

# Ordered from most-specific to least-specific so shorter patterns don't
# capture parts of longer ones.
_PLACEHOLDER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "url",
        re.compile(
            r"https?://[^\s<>\"')\]}>]+",
        ),
    ),
    (
        "email",
        re.compile(
            r"[a-zA-Z0-9._%+\-]{1,64}@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
        ),
    ),
    (
        "file_path",
        re.compile(
            r"""(?:^|[\s("'])(/(?:[a-zA-Z0-9._\-]+/)*[a-zA-Z0-9._\-]+)""",
        ),
    ),
    (
        "date_iso",
        re.compile(
            r"\b\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?\b",
        ),
    ),
    (
        "currency",
        re.compile(
            r"""[$\u20AC\u00A3\u00A5]\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b""",
        ),
    ),
    (
        "number",
        re.compile(
            r"\b\d+(?:\.\d+)?\b",
        ),
    ),
    (
        "ticket_id",
        re.compile(
            r"\b[A-Z]{2,6}-\d{2,8}\b",
        ),
    ),
]

# Fallback placeholder token template.  Must be unlikely to appear in
# natural text so we can reliably find it after translation.
_PLACEHOLDER_TOKEN = "__PH{idx}__"

# Sentinel delimiter placed between segments for batch translation.
# Chosen to survive LibreTranslate's tokenisation.
_SEGMENT_DELIMITER = "\n\n|||SEG|||\n\n"  # noqa: F841 — reserved for future batch translation

# Pre-built dict for O(1) pattern lookup by type name.
_PLACEHOLDER_PATTERNS_DICT: dict[str, re.Pattern[str]] = dict(_PLACEHOLDER_PATTERNS)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Segment:
    """A single text segment for translation."""

    index: int
    text: str
    # Source of the segment: "layout_block" or "paragraph"
    source: str = "paragraph"


@dataclass
class PlaceholderMap:
    """Mapping of placeholder token → original text for a single segment."""

    token_to_original: dict[str, str] = field(default_factory=dict)
    # Count of placeholders found by type, for validation
    type_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Aggregated validation metadata for a segment-aware translation."""

    segment_count: int
    failed_segment_count: int
    placeholder_mismatch_count: int
    number_date_mismatch_count: int
    length_ratio_outlier_count: int
    validation_status: str  # "ok" | "warning" | "failed"
    warnings: list[str]


# Translation function signature: (text, source_lang, target_lang) -> str
TranslateFn = Callable[[str, str | None, str], str]


# ---------------------------------------------------------------------------
# Segment builder
# ---------------------------------------------------------------------------


def build_segments(
    text: str,
    layout_blocks: list[dict[str, Any]] | None = None,
    *,
    max_segment_chars: int = 5000,
) -> list[Segment]:
    """Build translation segments from *text*.

    Prefers layout blocks when available (each block's ``text`` field becomes
    a segment).  Falls back to paragraph splitting on double-newline
    boundaries, then sentence splitting for oversized paragraphs.

    Empty segments are filtered out.  Very large segments are split further at
    character boundaries.
    """
    if not text.strip():
        return []

    # --- Layout-block path ---
    if layout_blocks:
        segments: list[Segment] = []
        for idx, block in enumerate(layout_blocks):
            block_text = (block.get("text") or "").strip()
            if not block_text:
                continue
            segments.append(Segment(index=idx, text=block_text, source="layout_block"))
        if segments:
            return _split_oversized(segments, max_segment_chars)

    # --- Paragraph fallback path ---
    paragraphs = _split_paragraphs(text)
    segments = []
    for idx, para in enumerate(paragraphs):
        if not para.strip():
            continue
        segments.append(Segment(index=idx, text=para.strip(), source="paragraph"))

    return _split_oversized(segments, max_segment_chars)


def _split_paragraphs(text: str) -> list[str]:
    """Split *text* at double-newline boundaries for paragraph segments."""
    # Normalize line endings
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    # Split on blank lines (two or more consecutive newlines)
    parts = re.split(r"\n{2,}", normalized)
    return [p.strip() for p in parts if p.strip()]


def _split_oversized(
    segments: list[Segment],
    max_chars: int,
) -> list[Segment]:
    """Split any segment longer than *max_chars* into sub-segments at sentence boundaries."""
    result: list[Segment] = []
    for seg in segments:
        if len(seg.text) <= max_chars:
            result.append(seg)
            continue
        sub_texts = _split_sentences_for_segments(seg.text)
        sub_segments: list[str] = []
        current = ""
        for st in sub_texts:
            if current and len(current) + len(st) > max_chars:
                sub_segments.append(current.strip())
                current = st
            else:
                current = (current + " " + st).strip() if current else st
        if current.strip():
            sub_segments.append(current.strip())
        for sub_idx, sub_text in enumerate(sub_segments):
            result.append(
                Segment(
                    index=seg.index * 1000 + sub_idx,
                    text=sub_text,
                    source=seg.source,
                )
            )
    return result


def _split_sentences_for_segments(text: str) -> list[str]:
    """Split text into sentences using a simple boundary pattern."""
    pattern = re.compile(r"[.!?]\s+(?=[A-Z\u05D0-\u05EA])|[.!?]\s*$")
    matches = list(pattern.finditer(text))
    if not matches:
        return [text]
    sentences: list[str] = []
    start = 0
    for match in matches:
        end = match.end()
        sentence = text[start:end].strip()
        if sentence:
            sentences.append(sentence)
        start = end
    trailing = text[start:].strip()
    if trailing:
        sentences.append(trailing)
    return sentences


# ---------------------------------------------------------------------------
# Placeholder protector
# ---------------------------------------------------------------------------


def protect_placeholders(text: str) -> tuple[str, PlaceholderMap]:
    """Replace recognised placeholders in *text* with unique tokens.

    Returns ``(protected_text, placeholder_map)``.  The map records every
    replacement so it can be restored after translation.
    """
    ph_map = PlaceholderMap()
    placeholder_spans: list[tuple[int, int, str, str]] = []
    # (start, end, token, ph_type)

    # Collect all placeholder matches, ordered by position
    for ph_type, pattern in _PLACEHOLDER_PATTERNS:
        for match in pattern.finditer(text):
            placeholder_spans.append((match.start(), match.end(), match.group(0), ph_type))

    # Sort by start position, then by end descending (longest match first
    # when they share a start position)
    placeholder_spans.sort(key=lambda s: (s[0], -s[1]))

    # Remove overlapping spans (keep the longest / first one)
    filtered: list[tuple[int, int, str, str]] = []
    for span in placeholder_spans:
        start, end = span[0], span[1]
        if filtered and start < filtered[-1][1]:
            continue  # overlaps with previous
        filtered.append(span)

    # Build the protected text by replacing placeholders from right to left
    # (so earlier indices remain valid after later replacements).
    result = text
    for idx, (start, end, original, ph_type) in enumerate(reversed(filtered)):
        token_idx = len(filtered) - 1 - idx
        token = _PLACEHOLDER_TOKEN.format(idx=token_idx)
        result = result[:start] + token + result[end:]
        ph_map.token_to_original[token] = original
        ph_map.type_counts[ph_type] = ph_map.type_counts.get(ph_type, 0) + 1

    return result, ph_map


def restore_placeholders(text: str, ph_map: PlaceholderMap) -> tuple[str, int]:
    """Restore placeholder tokens in *text* back to their original values.

    Returns ``(restored_text, mismatch_count)`` where *mismatch_count* is the
    number of tokens from the map that were **not** found in the translated
    text (i.e. lost during translation).
    """
    mismatch_count = 0
    result = text
    for token, original in ph_map.token_to_original.items():
        if token in result:
            result = result.replace(token, original, 1)
        else:
            mismatch_count += 1
            logger.debug("Placeholder %s lost during translation", token)
    return result, mismatch_count


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def validate_segments(
    original_segments: list[Segment],
    translated_texts: list[str],
    failed_indices: set[int],
    placeholder_maps: list[PlaceholderMap],
    total_placeholder_mismatches: int,
) -> ValidationResult:
    """Build validation metadata for the segment-aware translation.

    Checks:
    - Segment counts
    - Placeholder mismatches
    - Number/date mismatches (via type_counts)
    - Length-ratio outliers
    """
    segment_count = len(original_segments)
    failed_count = len(failed_indices)

    # Count number/date mismatches by comparing type counts
    number_date_mismatches = 0
    for i, ph_map in enumerate(placeholder_maps):
        if i >= len(translated_texts):
            break
        if i in failed_indices:
            continue
        trans_text = translated_texts[i]
        # Count numbers/dates in translated text and compare
        for ph_type in ("number", "date_iso", "currency"):
            expected = ph_map.type_counts.get(ph_type, 0)
            if expected == 0:
                continue
            pattern = _PLACEHOLDER_PATTERNS_DICT[ph_type]
            found = len(pattern.findall(trans_text))
            if found != expected:
                number_date_mismatches += abs(found - expected)

    # Length-ratio outliers: segments where the translation length is
    # suspiciously different from the original (>3x or <1/3).
    length_outliers = 0
    for i, seg in enumerate(original_segments):
        if i >= len(translated_texts) or i in failed_indices:
            continue
        orig_len = max(len(seg.text), 1)
        trans_len = max(len(translated_texts[i]), 1)
        ratio = trans_len / orig_len
        if ratio > 3.0 or ratio < 0.33:
            length_outliers += 1

    # Build warnings
    warnings: list[str] = []
    if failed_count > 0:
        warnings.append(f"{failed_count} of {segment_count} segments failed translation")
    if total_placeholder_mismatches > 0:
        warnings.append(f"{total_placeholder_mismatches} placeholder(s) lost during translation")
    if number_date_mismatches > 0:
        warnings.append(f"{number_date_mismatches} number/date mismatch(es) detected")
    if length_outliers > 0:
        warnings.append(f"{length_outliers} segment(s) with unusual length ratio")

    # Determine overall status
    if failed_count == segment_count:
        validation_status = "failed"
    elif warnings:
        validation_status = "warning"
    else:
        validation_status = "ok"

    return ValidationResult(
        segment_count=segment_count,
        failed_segment_count=failed_count,
        placeholder_mismatch_count=total_placeholder_mismatches,
        number_date_mismatch_count=number_date_mismatches,
        length_ratio_outlier_count=length_outliers,
        validation_status=validation_status,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Reassembler
# ---------------------------------------------------------------------------


def reassemble(
    translated_texts: list[str],
    original_segments: list[Segment],
    original_text: str,
    *,
    separator: str = "\n\n",
) -> str:
    """Reassemble translated segments into a single text.

    When segments came from layout blocks, we join with double-newlines.
    When they came from paragraphs, we preserve the original paragraph
    structure as closely as possible.

    If the number of translated texts doesn't match the segments (shouldn't
    happen), falls back to simple join.
    """
    if not translated_texts:
        return original_text
    if len(translated_texts) != len(original_segments):
        return original_text
    return separator.join(translated_texts)


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------


def run_segment_pipeline(
    text: str,
    translate_fn: TranslateFn,
    source_lang: str | None,
    target_lang: str,
    *,
    layout_blocks: list[dict[str, Any]] | None = None,
    max_segment_chars: int = 5000,
) -> tuple[str, ValidationResult]:
    """Run the full segment-aware translation pipeline.

    Args:
        text: The full source text to translate.
        translate_fn: Callable ``(text, source_lang, target_lang) -> str``
            that performs the actual translation (e.g. ``translator.translate``).
        source_lang: Source language code (or None for auto).
        target_lang: Target language code.
        layout_blocks: Optional list of layout block dicts (each with a
            ``text`` key).  When provided, segments are aligned to layout
            block boundaries instead of paragraph boundaries.
        max_segment_chars: Maximum characters per segment before further
            splitting.

    Returns:
        ``(translated_text, validation_result)``
    """
    # 0. Early exit for empty/whitespace-only text
    if not text.strip():
        return text, ValidationResult(
            segment_count=0,
            failed_segment_count=0,
            placeholder_mismatch_count=0,
            number_date_mismatch_count=0,
            length_ratio_outlier_count=0,
            validation_status="ok",
            warnings=[],
        )

    # 1. Build segments
    segments = build_segments(text, layout_blocks, max_segment_chars=max_segment_chars)

    # 2. Protect placeholders in each segment
    protected_segments: list[str] = []
    placeholder_maps: list[PlaceholderMap] = []
    for seg in segments:
        protected, ph_map = protect_placeholders(seg.text)
        protected_segments.append(protected)
        placeholder_maps.append(ph_map)

    # 3. Translate each segment individually.
    #    Hard exceptions propagate — callers handle retry/DLQ.
    #    Only soft no-op results (translation returns unchanged text)
    #    are treated as segment failures.
    translated_texts: list[str] = []
    failed_indices: set[int] = set()
    for i, seg_text in enumerate(protected_segments):
        result = translate_fn(seg_text, source_lang, target_lang)

        # If translation returned the original protected text (no-op), mark
        # as failed so we use the real original text.
        if result == seg_text and seg_text.strip():
            failed_indices.add(i)

        translated_texts.append(result)

    # 4. Restore placeholders in each translated segment
    restored_texts: list[str] = []
    total_mismatches = 0
    for i, (trans, ph_map) in enumerate(zip(translated_texts, placeholder_maps, strict=False)):
        if i in failed_indices:
            # Use original segment text with placeholders restored
            restored_texts.append(segments[i].text)
        else:
            restored, mismatches = restore_placeholders(trans, ph_map)
            restored_texts.append(restored)
            total_mismatches += mismatches

    # 5. Validate
    validation = validate_segments(
        original_segments=segments,
        translated_texts=restored_texts,
        failed_indices=failed_indices,
        placeholder_maps=placeholder_maps,
        total_placeholder_mismatches=total_mismatches,
    )

    # 6. Reassemble
    assembled = reassemble(restored_texts, segments, text)

    return assembled, validation
