"""Helpers for summary v2: chunking, JSON parsing, normalization, hashing."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

MAX_SUMMARIZE_CHARS = 8000
SUMMARY_CHUNK_CHARS = 6000
SUMMARY_MAX_CHUNKS = 8
SUMMARY_REDUCE_CHARS = 12000
SUMMARY_MAX_BULLETS = 7
SUMMARY_MAX_BULLET_LENGTH = 300

_KNOWN_LANGUAGES = frozenset(
    {
        "he",
        "en",
        "ar",
        "ru",
        "fr",
        "es",
        "de",
        "ja",
        "ko",
        "zh",
        "pt",
        "it",
        "nl",
        "pl",
        "tr",
    }
)
_KNOWN_DOC_TYPES = frozenset(
    {
        "contract",
        "report",
        "email",
        "presentation",
        "spreadsheet",
        "invoice",
        "memo",
        "policy",
        "technical",
        "article",
    }
)


def chunk_content(content: str, chunk_size: int = SUMMARY_CHUNK_CHARS) -> list[str]:
    """Split *content* into deterministic chunks of at most *chunk_size* chars.

    Returns up to ``SUMMARY_MAX_CHUNKS`` chunks.
    """
    if not content:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(content) and len(chunks) < SUMMARY_MAX_CHUNKS:
        end = start + chunk_size
        chunks.append(content[start:end])
        start = end
    return chunks


def parse_summary_json(raw: str) -> dict[str, Any] | None:
    """Try to extract a JSON object from *raw* and return it.

    Handles markdown-wrapped JSON (```json ... ```) and plain JSON.
    Returns ``None`` when parsing fails.
    """
    text = raw.strip()
    if text.startswith("```"):
        start = text.find("\n")
        if start != -1:
            text = text[start:].strip()
        end = text.rfind("```")
        if end != -1:
            text = text[:end].strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        logger.debug("Failed to parse summary JSON output")
    return None


def normalize_language(lang: Any) -> str:
    if isinstance(lang, str) and lang.strip().lower() in _KNOWN_LANGUAGES:
        return lang.strip().lower()
    return "unknown"


def normalize_document_type(doc_type: Any) -> str:
    if isinstance(doc_type, str) and doc_type.strip().lower() in _KNOWN_DOC_TYPES:
        return doc_type.strip().lower()
    return "unknown"


def normalize_source_text(source: Any) -> str:
    if isinstance(source, str) and source.strip().lower() in ("original", "translated"):
        return source.strip().lower()
    return "unknown"


def normalize_bullets(
    raw: Any,
    max_bullets: int = SUMMARY_MAX_BULLETS,
    max_length: int = SUMMARY_MAX_BULLET_LENGTH,
) -> list[str]:
    if not isinstance(raw, list):
        return []
    bullets: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text:
            continue
        text = text[:max_length]
        bullets.append(text)
        if len(bullets) >= max_bullets:
            break
    return bullets


def normalize_summary_output(raw: str) -> dict[str, Any]:
    """Parse and normalize a summary generation output.

    Returns a dict with keys: summary, bullets, language, document_type, source_text, status
    """
    parsed = parse_summary_json(raw)
    if parsed is not None:
        summary_text = (parsed.get("summary") or raw).strip()
        return {
            "summary": summary_text,
            "bullets": normalize_bullets(parsed.get("bullets")),
            "language": normalize_language(parsed.get("language")),
            "document_type": normalize_document_type(parsed.get("document_type")),
            "source_text": normalize_source_text(parsed.get("source_text")),
            "status": "available",
        }
    return {
        "summary": raw.strip(),
        "bullets": [],
        "language": "unknown",
        "document_type": "unknown",
        "source_text": "unknown",
        "status": "degraded",
    }


def content_hash(text: str) -> str:
    """Return a stable hex digest of *text*."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_error_category(exc: Exception) -> str:
    """Return a safe error category string from an exception."""
    msg = str(exc).lower()
    if "unavailable" in msg or "connection" in msg:
        return "model_unavailable"
    if "timeout" in msg:
        return "timeout"
    if "decode" in msg or "parse" in msg:
        return "malformed_output"
    if isinstance(exc, ValueError) and "empty" in msg:
        return "empty_content"
    return "unknown_failure"


def build_reduce_prompt(chunks: list[str], max_chars: int = SUMMARY_REDUCE_CHARS) -> str:
    """Build a reduction prompt from chunk summaries, bounded by *max_chars*."""
    combined = "\n\n".join(chunks)
    truncated = combined[:max_chars]
    return (
        "You are given several chunk summaries of a longer document below. "
        "Combine them into a single concise summary of the whole document. "
        "Respond with JSON only:\n"
        '{"summary": "...", "bullets": ["...", "..."], '
        '"language": "en|he|...|unknown", '
        '"document_type": "contract|report|email|...|unknown"}\n\n'
        f"{truncated}"
    )
