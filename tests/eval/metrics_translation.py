"""Translation quality metrics for offline benchmark evaluation (#732).

Metrics measure placeholder preservation, number retention, token sufficiency,
and provider comparison — independent of retrieval or citation quality.

All functions are deterministic and require no network access.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TranslationCaseResult:
    """Per-case result for a single translation provider run."""

    case_id: str
    provider: str  # "fast" or "high"
    source_lang: str | None
    target_lang: str
    source_text: str
    translated_text: str
    token_count: int
    placeholder_preservation: float  # 0.0–1.0
    number_preservation: float  # 0.0–1.0
    tokens_sufficient: bool
    error: str | None = None
    latency_ms: float = 0.0
    provider_version: str | None = None


@dataclass
class TranslationAggregateMetrics:
    """Aggregate metrics across all translation benchmark cases."""

    total_cases: int = 0
    # Per-provider metrics
    fast_placeholder_preservation: float = 1.0
    fast_number_preservation: float = 1.0
    fast_tokens_sufficient_rate: float = 1.0
    high_placeholder_preservation: float = 1.0
    high_number_preservation: float = 1.0
    high_tokens_sufficient_rate: float = 1.0
    cases_with_fast: int = 0
    cases_with_high: int = 0
    errors_fast: int = 0
    errors_high: int = 0
    # Per-case detail
    results: list[TranslationCaseResult] = field(default_factory=list)


def placeholder_preservation(
    translated_text: str,
    expected_placeholders: list[str],
) -> float:
    """Fraction of expected placeholder substrings found in the translated output.

    Placeholders are strings that must appear verbatim (URLs, emails,
    document IDs, version numbers). Returns 1.0 if no placeholders are
    expected.
    """
    if not expected_placeholders:
        return 1.0
    found = sum(1 for p in expected_placeholders if p in translated_text)
    return found / len(expected_placeholders)


def number_preservation(
    translated_text: str,
    expected_numbers: list[str],
) -> float:
    """Fraction of expected numeric substrings found in the translated output.

    Numbers may be reformatted (locale-appropriate separators), so this
    checks for substring presence. Returns 1.0 if no numbers are expected.
    """
    if not expected_numbers:
        return 1.0
    found = sum(1 for n in expected_numbers if n in translated_text)
    return found / len(expected_numbers)


def token_sufficiency(
    translated_text: str,
    min_tokens: int,
) -> bool:
    """Check that the translated output has at least *min_tokens* tokens.

    Catches catastrophic truncation, empty-output bugs, and provider
    failures that return the original text silently.
    """
    return len(translated_text.split()) >= min_tokens


def compare_providers(
    fast_result: TranslationCaseResult,
    high_result: TranslationCaseResult | None,
) -> dict[str, float]:
    """Compute per-case comparison deltas between fast and high providers.

    Returns a dict with delta values; empty if no high_provider result.
    """
    if high_result is None:
        return {}
    return {
        "delta_placeholder_preservation": (
            high_result.placeholder_preservation - fast_result.placeholder_preservation
        ),
        "delta_number_preservation": (
            high_result.number_preservation - fast_result.number_preservation
        ),
        "delta_token_count": high_result.token_count - fast_result.token_count,
    }


def aggregate_translation_metrics(
    results: list[TranslationCaseResult],
) -> TranslationAggregateMetrics:
    """Compute aggregate metrics from a list of per-case results."""
    agg = TranslationAggregateMetrics(total_cases=len(results), results=results)

    fast_results = [r for r in results if r.provider == "fast"]
    high_results = [r for r in results if r.provider == "high"]

    agg.cases_with_fast = len(fast_results)
    agg.cases_with_high = len(high_results)

    if fast_results:
        agg.fast_placeholder_preservation = sum(
            r.placeholder_preservation for r in fast_results
        ) / len(fast_results)
        agg.fast_number_preservation = sum(r.number_preservation for r in fast_results) / len(
            fast_results
        )
        agg.fast_tokens_sufficient_rate = sum(1 for r in fast_results if r.tokens_sufficient) / len(
            fast_results
        )
        agg.errors_fast = sum(1 for r in fast_results if r.error is not None)

    if high_results:
        agg.high_placeholder_preservation = sum(
            r.placeholder_preservation for r in high_results
        ) / len(high_results)
        agg.high_number_preservation = sum(r.number_preservation for r in high_results) / len(
            high_results
        )
        agg.high_tokens_sufficient_rate = sum(1 for r in high_results if r.tokens_sufficient) / len(
            high_results
        )
        agg.errors_high = sum(1 for r in high_results if r.error is not None)

    return agg
