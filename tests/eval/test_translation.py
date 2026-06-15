"""Offline translation benchmark evaluation harness (#732).

Compares fast (LibreTranslate/Argos) and high (CTranslate2/OPUS-MT)
translation providers on multilingual enterprise text fixtures.

Run with:
    pytest tests/eval/test_translation.py --eval
    pytest tests/eval/test_translation.py --eval --eval-output results-translation.json

These tests are skipped in normal CI (requires --eval flag).
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

import pytest

from tests.eval.fixtures.translation import TRANSLATION_EVAL_CASES
from tests.eval.metrics_translation import (
    TranslationCaseResult,
    aggregate_translation_metrics,
    compare_providers,
    number_preservation,
    placeholder_preservation,
    token_sufficiency,
)


def _build_fast_provider() -> Any:
    """Build the fast (LibreTranslate/Argos) translation provider."""
    from services.translation.libretranslate_provider import (
        LibreTranslateArgosProvider,
    )
    from shared.config import Settings

    settings = Settings()
    return LibreTranslateArgosProvider(
        base_url=settings.libretranslate_url,
        api_key=settings.libretranslate_api_key,
        timeout=settings.libretranslate_timeout,
    )


def _build_high_provider() -> Any | None:
    """Build the high (CTranslate2/OPUS-MT) provider, or None if unavailable."""
    import os

    from shared.config import Settings

    settings = Settings()
    bundle_path = settings.translation_high_provider_bundle_path
    if not bundle_path or not os.path.isdir(bundle_path):
        return None

    try:
        from services.translation.ctranslate2_provider import (
            CTranslate2OpusProvider,
        )

        return CTranslate2OpusProvider(
            bundle_path=bundle_path,
            baseline=_build_fast_provider(),
        )
    except ImportError:
        return None


def _run_translation_case(
    case: dict,
    provider: Any,
    provider_label: str,
) -> TranslationCaseResult:
    """Run a single translation case through one provider."""
    source_text = str(case["source_text"])
    source_lang = case.get("source_lang")
    target_lang = str(case.get("target_lang", "en"))
    expected_placeholders = case.get("expected_placeholders", [])
    expected_numbers = case.get("expected_numbers", [])
    min_tokens = int(case.get("expected_tokens_min", 5))

    start = time.perf_counter()
    error: str | None = None
    translated = ""

    try:
        translated = provider.translate(
            text=source_text,
            source_lang=source_lang,
            target_lang=target_lang,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        translated = ""

    elapsed_ms = (time.perf_counter() - start) * 1000
    token_count = len(translated.split())
    pp = placeholder_preservation(translated, expected_placeholders)
    np_val = number_preservation(translated, expected_numbers)
    ts = token_sufficiency(translated, min_tokens)

    version: str | None = None
    with contextlib.suppress(Exception):
        version = provider.version  # type: ignore[union-attr]

    return TranslationCaseResult(
        case_id=str(case["id"]),
        provider=provider_label,
        source_lang=source_lang,
        target_lang=target_lang,
        source_text=source_text[:200],
        translated_text=translated[:500],
        token_count=token_count,
        placeholder_preservation=pp,
        number_preservation=np_val,
        tokens_sufficient=ts,
        error=error,
        latency_ms=elapsed_ms,
        provider_version=version,
    )


@pytest.mark.eval
@pytest.mark.parametrize(
    "case",
    TRANSLATION_EVAL_CASES,
    ids=[c["id"] for c in TRANSLATION_EVAL_CASES],
)
def test_translation_case(
    case: dict,
    eval_config: str,
    eval_results_collector: list[dict],
) -> None:
    """Run a single translation benchmark case through fast and high providers."""
    fast = _build_fast_provider()
    high = _build_high_provider()

    fast_result = _run_translation_case(case, fast, "fast")
    high_result = _run_translation_case(case, high, "high") if high else None

    # Cleanup
    with contextlib.suppress(Exception):
        fast.close()  # type: ignore[union-attr]
    if high:
        with contextlib.suppress(Exception):
            high.close()  # type: ignore[union-attr]

    comparison = compare_providers(fast_result, high_result)

    case_record = {
        "id": case["id"],
        "category": case["category"],
        "source_lang": case.get("source_lang"),
        "target_lang": case.get("target_lang", "en"),
        "tags": case.get("tags", []),
        "eval_config": eval_config,
        "notes": case.get("notes", ""),
        # Fast provider result
        "fast": {
            "token_count": fast_result.token_count,
            "placeholder_preservation": fast_result.placeholder_preservation,
            "number_preservation": fast_result.number_preservation,
            "tokens_sufficient": fast_result.tokens_sufficient,
            "latency_ms": fast_result.latency_ms,
            "provider_version": fast_result.provider_version,
            "error": fast_result.error,
            "translated_preview": fast_result.translated_text[:300],
        },
        # High provider result (nullable)
        "high": (
            {
                "token_count": high_result.token_count,
                "placeholder_preservation": high_result.placeholder_preservation,
                "number_preservation": high_result.number_preservation,
                "tokens_sufficient": high_result.tokens_sufficient,
                "latency_ms": high_result.latency_ms,
                "provider_version": high_result.provider_version,
                "error": high_result.error,
                "translated_preview": high_result.translated_text[:300],
            }
            if high_result
            else None
        ),
        "comparison": comparison,
        "high_available": high is not None,
        "passed": (fast_result.error is None and fast_result.tokens_sufficient),
    }

    eval_results_collector.append(case_record)

    # Assert minimum quality: fast provider must not error and must
    # produce sufficient tokens.
    assert fast_result.error is None, f"Fast provider failed on {case['id']}: {fast_result.error}"
    assert fast_result.tokens_sufficient, (
        f"Fast provider produced insufficient tokens for {case['id']}: "
        f"got {fast_result.token_count}, need at least "
        f"{case.get('expected_tokens_min', 5)}"
    )


@pytest.mark.eval
def test_aggregate_translation_metrics(
    eval_results_collector: list[dict],
) -> None:
    """Print aggregate translation metrics after all cases have run."""
    if not eval_results_collector:
        pytest.skip("No translation eval cases ran")

    # Reconstruct TranslationCaseResult list from the collected dicts
    all_results: list[TranslationCaseResult] = []
    for record in eval_results_collector:
        fast_data = record["fast"]
        all_results.append(
            TranslationCaseResult(
                case_id=record["id"],
                provider="fast",
                source_lang=record.get("source_lang"),
                target_lang=record.get("target_lang", "en"),
                source_text="",
                translated_text=fast_data.get("translated_preview", ""),
                token_count=fast_data.get("token_count", 0),
                placeholder_preservation=fast_data.get("placeholder_preservation", 0.0),
                number_preservation=fast_data.get("number_preservation", 0.0),
                tokens_sufficient=fast_data.get("tokens_sufficient", False),
                error=fast_data.get("error"),
                latency_ms=fast_data.get("latency_ms", 0.0),
                provider_version=fast_data.get("provider_version"),
            )
        )
        if record["high"]:
            high_data = record["high"]
            all_results.append(
                TranslationCaseResult(
                    case_id=record["id"],
                    provider="high",
                    source_lang=record.get("source_lang"),
                    target_lang=record.get("target_lang", "en"),
                    source_text="",
                    translated_text=high_data.get("translated_preview", ""),
                    token_count=high_data.get("token_count", 0),
                    placeholder_preservation=high_data.get("placeholder_preservation", 0.0),
                    number_preservation=high_data.get("number_preservation", 0.0),
                    tokens_sufficient=high_data.get("tokens_sufficient", False),
                    error=high_data.get("error"),
                    latency_ms=high_data.get("latency_ms", 0.0),
                    provider_version=high_data.get("provider_version"),
                )
            )

    metrics = aggregate_translation_metrics(all_results)

    import json

    report = {
        "total_cases": metrics.total_cases,
        "cases_with_fast": metrics.cases_with_fast,
        "cases_with_high": metrics.cases_with_high,
        "fast": {
            "placeholder_preservation": metrics.fast_placeholder_preservation,
            "number_preservation": metrics.fast_number_preservation,
            "tokens_sufficient_rate": metrics.fast_tokens_sufficient_rate,
            "errors": metrics.errors_fast,
        },
        "high": {
            "placeholder_preservation": metrics.high_placeholder_preservation,
            "number_preservation": metrics.high_number_preservation,
            "tokens_sufficient_rate": metrics.high_tokens_sufficient_rate,
            "errors": metrics.errors_high,
        },
    }
    print("\n\n=== Translation Benchmark Aggregate Metrics ===")
    print(json.dumps(report, indent=2))
    print("================================================\n")

    # Soft assertions: document quality, don't gate CI
    if metrics.cases_with_fast > 0:
        assert metrics.fast_tokens_sufficient_rate >= 0.5, (
            f"Fast provider token sufficiency rate too low: "
            f"{metrics.fast_tokens_sufficient_rate:.2%}"
        )
