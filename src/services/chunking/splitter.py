"""Token-based text chunking with sentence-boundary awareness."""

from __future__ import annotations

import bisect
import re
from re import Pattern
from typing import Any

# Sentence boundary patterns per language group.
# English/Latin: punctuation + space + capital letter.
# Hebrew: punctuation + space + Hebrew letter.
# Generic fallback: any punctuation + space + non-whitespace.
_SENTENCE_PATTERNS: dict[str, Pattern[str]] = {
    "en": re.compile(r"[.!?]\s+(?=[A-Z])|[.!?]\s*$"),
    "he": re.compile(r"[.!?]\s+(?=[\u05D0-\u05EA])|[.!?]\s*$"),
}
_FALLBACK_PATTERN: Pattern[str] = re.compile(r"[.!?]\s+(?=\S)|[.!?]\s*$")


def _sentence_pattern(language: str | None = None) -> Pattern[str]:
    """Return the sentence-boundary pattern for *language*."""
    if language and language in _SENTENCE_PATTERNS:
        return _SENTENCE_PATTERNS[language]
    return _FALLBACK_PATTERN


_TOKEN_ESTIMATE_RATIO: float = 2.0


def _estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in *text* using a character-based heuristic.

    Uses ``len(text) / _TOKEN_ESTIMATE_RATIO`` (default 2.0).  A ratio of 2.0
    is deliberately conservative: Latin scripts tokenise at ~4 chars/token, but
    dense scripts such as Hebrew, Arabic, and CJK can be 1–2 chars/token.
    Using 2.0 ensures ``max_tokens`` enforcement in the splitter is safe for all
    supported languages at the cost of slightly smaller English chunks.
    """
    return max(1, int(len(text) / _TOKEN_ESTIMATE_RATIO))


def _ensure_max_tokens(chunks: list[str], max_tokens: int) -> list[str]:
    """Further split any chunk whose estimated token count exceeds *max_tokens*.

    Splits oversized chunks at sentence boundaries when possible, otherwise
    at a hard character limit derived from *max_tokens*.
    """
    result: list[str] = []
    for chunk in chunks:
        if _estimate_tokens(chunk) <= max_tokens:
            result.append(chunk)
            continue
        # Oversized chunk: split further using the same sentence-boundary approach
        sub_chunks = _chunk_by_token_estimate(chunk, max_tokens)
        result.extend(sub_chunks)
    return result


def _chunk_by_token_estimate(text: str, max_tokens: int) -> list[str]:
    """Split *text* into chunks each estimated at ≤ *max_tokens* tokens."""
    max_chars = int(max_tokens * _TOKEN_ESTIMATE_RATIO)
    sentences = _split_sentences(text, None)
    chunks: list[str] = []
    current: list[str] = []
    current_est = 0
    for sentence in sentences:
        sentence_est = _estimate_tokens(sentence)
        if current and current_est + sentence_est > max_tokens:
            chunks.append(" ".join(current))
            current = []
            current_est = 0
        # Single sentence larger than max_tokens: hard-cut at character limit
        if _estimate_tokens(sentence) > max_tokens:
            for i in range(0, len(sentence), max_chars):
                segment = sentence[i : i + max_chars]
                if segment:
                    chunks.append(segment)
            continue
        current.append(sentence)
        current_est += sentence_est
    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 50,
    language: str | None = None,
    max_tokens: int | None = None,
) -> list[str]:
    """Split *text* into chunks of at most *chunk_size* tokens (whitespace-split).

    Chunks are split on sentence boundaries when possible. When a sentence
    would exceed the remaining token budget, a hard cut is made at the token
    limit. *overlap* tokens from the end of the previous chunk are repeated at
    the start of the next chunk. The last chunk is not padded.

    When *language* is provided, the sentence-boundary detector uses a
    language-appropriate pattern. Known languages: ``en``, ``he``. Unknown
    languages fall back to a generic pattern that splits on any punctuation
    followed by a space and a non-whitespace character.

    When *max_tokens* is provided, any chunk whose estimated token count
    exceeds *max_tokens* is further split.

    Returns an empty list when *text* is empty or whitespace-only.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and less than chunk_size")

    if not text.strip():
        return []

    sentences = _split_sentences(text, language)
    chunks: list[str] = []
    current_chunk_words: list[str] = []

    for sentence in sentences:
        sentence_words = sentence.split()
        if current_chunk_words and len(current_chunk_words) + len(sentence_words) > chunk_size:
            chunks.append(" ".join(current_chunk_words))
            overlap_words = current_chunk_words[-overlap:] if overlap > 0 else []
            current_chunk_words = overlap_words + sentence_words
        else:
            current_chunk_words.extend(sentence_words)

        while len(current_chunk_words) > chunk_size:
            chunk_words = current_chunk_words[:chunk_size]
            chunks.append(" ".join(chunk_words))
            overlap_words = chunk_words[-overlap:] if overlap > 0 else []
            current_chunk_words = overlap_words + current_chunk_words[chunk_size:]

    if current_chunk_words:
        chunks.append(" ".join(current_chunk_words))

    if max_tokens is not None:
        chunks = _ensure_max_tokens(chunks, max_tokens)

    return chunks


def resolve_chunk_locations(
    original_text: str,
    chunks: list[str],
    location_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map each chunk to its page_number / section_heading from *location_segments*.

    Each segment dict must have ``start_char`` and ``end_char`` (Python slice
    offsets into *original_text*), and optionally ``page_number`` and/or
    ``section_heading``.  For each chunk we find the segment with the largest
    overlap and return its location fields.  Returns one dict per chunk (empty
    dict when no segment matches).
    """
    if not chunks or not location_segments:
        return [{} for _ in chunks]

    # Sort segments by start_char for binary search
    sorted_segs = sorted(location_segments, key=lambda s: s["start_char"])
    starts = [s["start_char"] for s in sorted_segs]

    def _overlap(seg: dict[str, Any], c_start: int, c_end: int) -> int:
        s_end: int = seg.get("end_char", 0)
        s_start: int = seg.get("start_char", 0)
        return max(0, min(s_end, c_end) - max(s_start, c_start))

    positions = _find_chunk_positions(original_text, chunks)
    result: list[dict[str, Any]] = []
    for c_start, c_end in positions:
        best: dict[str, Any] = {}
        best_overlap = 0
        # Find the first segment that could overlap
        idx = bisect.bisect_right(starts, c_end) - 1
        # Scan backward then forward for overlapping segments.
        # Window of ±2 segments (5 total) is fine for PDF pages and PPTX
        # slides. For DOCX documents with many tiny heading sections (dense
        # API reference, legal docs), a chunk spanning more than 5 sections
        # could map to the wrong section — acceptable for this first cut.
        for si in range(max(0, idx - 2), min(len(sorted_segs), idx + 3)):
            seg = sorted_segs[si]
            if seg["start_char"] > c_end:
                break
            if seg["end_char"] <= c_start:
                continue
            ov = _overlap(seg, c_start, c_end)
            if ov > best_overlap:
                best_overlap = ov
                best = {}
                if "page_number" in seg:
                    best["page_number"] = seg["page_number"]
                if "section_heading" in seg:
                    best["section_heading"] = seg["section_heading"]
        result.append(best)
    return result


def _find_chunk_positions(text: str, chunks: list[str]) -> list[tuple[int, int]]:
    """Map each chunk to its (start, end) character position in *text*.

    Uses sequential scanning to handle overlap between neighbouring chunks.
    Returns ``(0, 0)`` for any chunk whose text cannot be located.

    Note: ``chunk_text()`` joins sentences with single spaces while the
    original text may use newlines between pages/slides/paragraphs.  We
    normalize chunk whitespace to single spaces but search in the original
    (un-normalized) text.  Any chunk spanning a page/slide/paragraph boundary
    will fail the search and silently return ``(0, 0)`` — graceful degradation,
    not a bug.
    """
    positions: list[tuple[int, int]] = []
    pos = 0
    for chunk in chunks:
        normalized = re.sub(r"\s+", " ", chunk.strip())
        if not normalized:
            positions.append((0, 0))
            continue
        idx = text.find(normalized, pos)
        if idx == -1:
            idx = text.find(normalized)
        if idx == -1:
            positions.append((0, 0))
            continue
        end = idx + len(normalized)
        positions.append((idx, end))
        pos = end
    return positions


def _split_sentences(text: str, language: str | None = None) -> list[str]:
    """Split *text* into sentences using the pattern for *language*."""
    if not text.strip():
        return []

    pattern = _sentence_pattern(language)
    matches = list(pattern.finditer(text))
    if not matches:
        return [text.strip()]

    sentences: list[str] = []
    start = 0
    for match in matches:
        end = match.end()
        sentence = text[start:end].strip()
        if sentence:
            sentences.append(sentence)
        start = end

    if start < len(text):
        trailing = text[start:].strip()
        if trailing:
            sentences.append(trailing)

    return sentences
