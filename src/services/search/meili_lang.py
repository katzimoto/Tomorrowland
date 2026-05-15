from __future__ import annotations

from typing import Literal

QueryLanguage = Literal["en", "he", "mixed"]

# Hebrew Unicode block: Basic Hebrew (U+0591–U+05FF).
# Includes vowel points, punctuation, and letters — all indicate Hebrew content.
_HEBREW_START = 0x0591
_HEBREW_END = 0x05FF

_HE_THRESHOLD = 0.6   # > 60 % Hebrew → "he"
_MIXED_THRESHOLD = 0.1  # > 10 % Hebrew → "mixed"


def detect_query_language(q: str) -> QueryLanguage:
    """Detect the primary language of a search query string.

    Uses the ratio of Hebrew Unicode characters (U+0591–U+05FF) to total
    non-whitespace characters. Reliable for short queries without requiring
    an external language detection library.

    Returns:
        ``"he"`` when > 60 % of non-whitespace characters are Hebrew.
        ``"mixed"`` when 10–60 % are Hebrew.
        ``"en"`` otherwise (including empty and whitespace-only input).
    """
    non_ws = [c for c in q if not c.isspace()]
    if not non_ws:
        return "en"

    hebrew_count = sum(1 for c in non_ws if _HEBREW_START <= ord(c) <= _HEBREW_END)
    ratio = hebrew_count / len(non_ws)

    if ratio > _HE_THRESHOLD:
        return "he"
    if ratio > _MIXED_THRESHOLD:
        return "mixed"
    return "en"


def resolve_query_language(
    q: str,
    language: Literal["auto", "en", "he"],
) -> QueryLanguage:
    """Resolve the effective query language from the user's preference.

    When ``language`` is ``"auto"``, runs ``detect_query_language``.
    When ``language`` is ``"en"`` or ``"he"``, returns it directly without
    inspecting the query string — the user's explicit choice takes precedence.

    The returned value is metadata for UI hints and logging only. It does not
    change which Meilisearch index or attributes are searched.
    """
    if language == "auto":
        return detect_query_language(q)
    return language
