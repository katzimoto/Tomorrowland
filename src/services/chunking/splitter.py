"""Token-based text chunking with sentence-boundary awareness."""

from __future__ import annotations

import re
from re import Pattern

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


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 50,
    language: str | None = None,
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

    return chunks


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
