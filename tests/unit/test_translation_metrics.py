"""Unit tests for translation benchmark metrics (#732)."""

from __future__ import annotations

import pytest

from tests.eval.metrics_translation import (
    TranslationCaseResult,
    aggregate_translation_metrics,
    compare_providers,
    number_preservation,
    placeholder_preservation,
    token_sufficiency,
)

# ---------------------------------------------------------------------------
# placeholder_preservation
# ---------------------------------------------------------------------------


def test_placeholder_preservation_all_found() -> None:
    result = placeholder_preservation(
        "Visit https://example.com or email a@b.com for doc ABC-001 v2.1",
        ["https://example.com", "a@b.com", "ABC-001", "2.1"],
    )
    assert result == 1.0


def test_placeholder_preservation_partial() -> None:
    result = placeholder_preservation(
        "Visit https://example.com for details",
        ["https://example.com", "a@b.com", "ABC-001"],
    )
    assert result == 1.0 / 3.0


def test_placeholder_preservation_none_found() -> None:
    result = placeholder_preservation(
        "No placeholders in this text",
        ["https://example.com", "a@b.com"],
    )
    assert result == 0.0


def test_placeholder_preservation_empty_expected() -> None:
    result = placeholder_preservation("some text", [])
    assert result == 1.0


# ---------------------------------------------------------------------------
# number_preservation
# ---------------------------------------------------------------------------


def test_number_preservation_all_found() -> None:
    result = number_preservation(
        "Revenue: 124,500,000. Growth: 8.3%. Units: 5,800.",
        ["124,500,000", "8.3", "5,800"],
    )
    assert result == 1.0


def test_number_preservation_partial() -> None:
    result = number_preservation(
        "Revenue 124,500,000 only",
        ["124,500,000", "8.3", "5,800"],
    )
    assert result == 1.0 / 3.0


def test_number_preservation_none_found() -> None:
    result = number_preservation("No numbers", ["12.5", "100"])
    assert result == 0.0


def test_number_preservation_empty_expected() -> None:
    result = number_preservation("has 42 numbers", [])
    assert result == 1.0


# ---------------------------------------------------------------------------
# token_sufficiency
# ---------------------------------------------------------------------------


def test_token_sufficiency_enough() -> None:
    assert token_sufficiency("one two three four five six seven eight nine ten", 5) is True


def test_token_sufficiency_not_enough() -> None:
    assert token_sufficiency("only three words here", 5) is False


def test_token_sufficiency_exact() -> None:
    assert token_sufficiency("a b c d e", 5) is True


def test_token_sufficiency_empty() -> None:
    assert token_sufficiency("", 1) is False


def test_token_sufficiency_zero_min() -> None:
    assert token_sufficiency("any text", 0) is True


# ---------------------------------------------------------------------------
# compare_providers
# ---------------------------------------------------------------------------


def test_compare_providers_with_both() -> None:
    fast = TranslationCaseResult(
        case_id="test",
        provider="fast",
        source_lang="he",
        target_lang="en",
        source_text="test",
        translated_text="fast output",
        token_count=10,
        placeholder_preservation=0.8,
        number_preservation=0.9,
        tokens_sufficient=True,
    )
    high = TranslationCaseResult(
        case_id="test",
        provider="high",
        source_lang="he",
        target_lang="en",
        source_text="test",
        translated_text="high output",
        token_count=12,
        placeholder_preservation=1.0,
        number_preservation=1.0,
        tokens_sufficient=True,
    )
    comparison = compare_providers(fast, high)
    assert comparison["delta_placeholder_preservation"] == pytest.approx(0.2)
    assert comparison["delta_number_preservation"] == pytest.approx(0.1)
    assert comparison["delta_token_count"] == 2


def test_compare_providers_high_none() -> None:
    fast = TranslationCaseResult(
        case_id="test",
        provider="fast",
        source_lang="he",
        target_lang="en",
        source_text="test",
        translated_text="fast output",
        token_count=10,
        placeholder_preservation=1.0,
        number_preservation=1.0,
        tokens_sufficient=True,
    )
    comparison = compare_providers(fast, None)
    assert comparison == {}


# ---------------------------------------------------------------------------
# aggregate_translation_metrics
# ---------------------------------------------------------------------------


def _make_result(
    case_id: str,
    provider: str,
    placeholder_preservation: float = 1.0,
    number_preservation: float = 1.0,
    tokens_sufficient: bool = True,
    error: str | None = None,
) -> TranslationCaseResult:
    return TranslationCaseResult(
        case_id=case_id,
        provider=provider,
        source_lang="he",
        target_lang="en",
        source_text="test",
        translated_text="translated text with several tokens here",
        token_count=6,
        placeholder_preservation=placeholder_preservation,
        number_preservation=number_preservation,
        tokens_sufficient=tokens_sufficient,
        error=error,
    )


def test_aggregate_empty() -> None:
    metrics = aggregate_translation_metrics([])
    assert metrics.total_cases == 0
    assert metrics.cases_with_fast == 0
    assert metrics.cases_with_high == 0


def test_aggregate_fast_only() -> None:
    results = [
        _make_result("a", "fast", 1.0, 0.9, True),
        _make_result("b", "fast", 0.8, 1.0, True),
    ]
    metrics = aggregate_translation_metrics(results)
    assert metrics.cases_with_fast == 2
    assert metrics.cases_with_high == 0
    assert metrics.fast_placeholder_preservation == 0.9  # (1.0+0.8)/2
    assert metrics.fast_number_preservation == 0.95  # (0.9+1.0)/2
    assert metrics.fast_tokens_sufficient_rate == 1.0
    assert metrics.errors_fast == 0


def test_aggregate_mixed_providers() -> None:
    results = [
        _make_result("a", "fast", 1.0, 1.0, True),
        _make_result("a", "high", 0.9, 0.8, True),
        _make_result("b", "fast", 0.7, 0.6, False),
    ]
    metrics = aggregate_translation_metrics(results)
    assert metrics.cases_with_fast == 2
    assert metrics.cases_with_high == 1
    # Fast: (1.0+0.7)/2 = 0.85, (1.0+0.6)/2 = 0.8
    assert metrics.fast_placeholder_preservation == 0.85
    assert metrics.fast_number_preservation == 0.8
    assert metrics.fast_tokens_sufficient_rate == 0.5  # 1/2
    # High: just one case
    assert metrics.high_placeholder_preservation == 0.9
    assert metrics.high_number_preservation == 0.8
    assert metrics.high_tokens_sufficient_rate == 1.0


def test_aggregate_with_errors() -> None:
    results = [
        _make_result("a", "fast", 1.0, 1.0, True),
        _make_result("b", "fast", 0.5, 0.5, False, error="ConnectionError"),
        _make_result("c", "fast", 0.0, 0.0, False, error="Timeout"),
    ]
    metrics = aggregate_translation_metrics(results)
    assert metrics.errors_fast == 2
    assert metrics.fast_tokens_sufficient_rate == 1.0 / 3.0
