from __future__ import annotations

from services.search.meili_lang import detect_query_language, resolve_query_language

# ---------------------------------------------------------------------------
# detect_query_language
# ---------------------------------------------------------------------------


def test_pure_english_returns_en() -> None:
    assert detect_query_language("quarterly report") == "en"


def test_pure_hebrew_returns_he() -> None:
    assert detect_query_language("דוח רבעוני") == "he"


def test_mixed_query_he_dominates_returns_mixed() -> None:
    # "דוח quarterly" — roughly 50/50, detected as mixed
    assert detect_query_language("דוח quarterly") == "mixed"


def test_mostly_hebrew_with_latin_chars_returns_he() -> None:
    # "ניתוח של Q4" — Q and 4 are latin/digit, rest Hebrew
    assert detect_query_language("ניתוח של Q4") == "he"


def test_single_hebrew_char_returns_he() -> None:
    assert detect_query_language("א") == "he"


def test_empty_string_returns_en() -> None:
    assert detect_query_language("") == "en"


def test_whitespace_only_returns_en() -> None:
    assert detect_query_language("   ") == "en"
    assert detect_query_language("\t\n") == "en"


def test_punctuation_only_returns_en() -> None:
    assert detect_query_language("?!.,;:") == "en"


def test_numbers_only_returns_en() -> None:
    assert detect_query_language("2024") == "en"


def test_low_hebrew_ratio_returns_mixed() -> None:
    # "report אב" → 6 + 2 = 8 non-ws chars, 2 Hebrew = 25% → mixed
    assert detect_query_language("report אב") == "mixed"


def test_below_threshold_returns_en() -> None:
    # "report 2024 א" → 11 non-ws chars, 1 Hebrew ≈ 9.1% < 10% → en
    assert detect_query_language("report 2024 א") == "en"


def test_all_hebrew_vowel_points_returns_he() -> None:
    # Vowel points (U+05B0–U+05BD) are in the Hebrew Unicode block
    assert detect_query_language("שָׁלוֹם") == "he"


# ---------------------------------------------------------------------------
# resolve_query_language
# ---------------------------------------------------------------------------


def test_resolve_auto_detects_english() -> None:
    assert resolve_query_language("quarterly report", "auto") == "en"


def test_resolve_auto_detects_hebrew() -> None:
    assert resolve_query_language("דוח רבעוני", "auto") == "he"


def test_resolve_auto_detects_mixed() -> None:
    assert resolve_query_language("דוח quarterly", "auto") == "mixed"


def test_resolve_explicit_en_overrides_hebrew_query() -> None:
    # Even though the string is Hebrew, explicit "en" wins
    assert resolve_query_language("דוח", "en") == "en"


def test_resolve_explicit_he_overrides_english_query() -> None:
    assert resolve_query_language("report", "he") == "he"


def test_resolve_auto_empty_string_returns_en() -> None:
    assert resolve_query_language("", "auto") == "en"
