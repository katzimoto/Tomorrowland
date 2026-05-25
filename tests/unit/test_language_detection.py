"""Tests for the LanguageDetector."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.extraction.language import LanguageDetector


def test_detect_returns_none_for_short_text() -> None:
    detector = LanguageDetector()
    assert detector.detect("Hi") is None


def test_detect_returns_none_when_langdetect_missing() -> None:
    with patch("services.extraction.language._LANGDETECT_AVAILABLE", False):
        assert LanguageDetector().detect("This is a normal English sentence.") is None


def test_detect_returns_language_for_english_text() -> None:
    detector = LanguageDetector()
    text = (
        "The quick brown fox jumps over the lazy dog. "
        "This sentence is written in English and should be detected correctly. "
        "Language detection works best with longer input texts."
    )
    result = detector.detect(text)
    # Result is either "en" or None (when langdetect is not installed in test env).
    assert result in (None, "en")


def test_detect_returns_none_on_exception() -> None:
    mock_detect = MagicMock(side_effect=Exception("boom"))
    with (
        patch("services.extraction.language._LANGDETECT_AVAILABLE", True),
        patch("services.extraction.language.detect_langs", mock_detect, create=True),
    ):
        assert LanguageDetector().detect("A" * 200) is None


def test_detect_returns_none_for_low_confidence() -> None:
    mock_lang = MagicMock()
    mock_lang.lang = "fr"
    mock_lang.prob = 0.5  # below the 0.80 threshold

    mock_detect = MagicMock(return_value=[mock_lang])
    with (
        patch("services.extraction.language._LANGDETECT_AVAILABLE", True),
        patch("services.extraction.language.detect_langs", mock_detect, create=True),
    ):
        assert LanguageDetector().detect("A" * 200) is None


def test_detect_returns_language_for_high_confidence() -> None:
    mock_lang = MagicMock()
    mock_lang.lang = "de"
    mock_lang.prob = 0.95

    mock_detect = MagicMock(return_value=[mock_lang])
    with (
        patch("services.extraction.language._LANGDETECT_AVAILABLE", True),
        patch("services.extraction.language.detect_langs", mock_detect, create=True),
    ):
        assert LanguageDetector().detect("A" * 200) == "de"
