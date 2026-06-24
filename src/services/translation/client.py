"""LibreTranslate HTTP client with timeout, retry, and fallback."""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Translation metadata builder (#727)
# ---------------------------------------------------------------------------

_DEFAULT_PROVIDER = "libretranslate_argos"
_DEFAULT_MODEL_FAMILY = "argos"


def _safe_str(value: object) -> str | None:
    """Return *value* as a string, or None if it is not a real string.

    Defends against MagicMock and other non-serializable test doubles
    leaking into JSON metadata (#727).
    """
    return value if isinstance(value, str) else None


def build_translation_metadata(
    *,
    provider: str,
    provider_version: str | None = None,
    model_family: str | None = None,
    quality_lane: str,
    purpose: str,
    source_language: str | None,
    target_language: str,
    input_text: str,
    output_text: str,
    segment_count: int = 0,
    validation_status: str = "unknown",
    fallback_used: bool = False,
    fallback_reason: str | None = None,
    # Segment-aware validation fields (#728)
    failed_segment_count: int = 0,
    placeholder_mismatch_count: int = 0,
    number_date_mismatch_count: int = 0,
    length_ratio_outlier_count: int = 0,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build a metadata dict for a translation version (#727, #728)."""
    meta: dict[str, Any] = {
        "provider": provider,
        "quality_lane": quality_lane,
        "purpose": purpose,
        "source_language": source_language,
        "target_language": target_language,
        "input_char_count": len(input_text),
        "output_char_count": len(output_text),
        "segment_count": segment_count,
        "validation_status": validation_status,
        "fallback_used": fallback_used,
    }
    if provider_version is not None:
        meta["provider_version"] = provider_version
    if model_family is not None:
        meta["model_family"] = model_family
    if fallback_reason is not None:
        meta["fallback_reason"] = fallback_reason
    # Segment-aware validation fields (#728)
    if failed_segment_count > 0:
        meta["failed_segment_count"] = failed_segment_count
    if placeholder_mismatch_count > 0:
        meta["placeholder_mismatch_count"] = placeholder_mismatch_count
    if number_date_mismatch_count > 0:
        meta["number_date_mismatch_count"] = number_date_mismatch_count
    if length_ratio_outlier_count > 0:
        meta["length_ratio_outlier_count"] = length_ratio_outlier_count
    if warnings:
        meta["warnings"] = warnings
    return meta


class LibreTranslateClient:
    """Self-hosted LibreTranslate client with graceful fallback.

    On any network or server error the original text is returned unchanged
    so that ingestion never blocks on translation.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = httpx.Client(timeout=timeout)
        self._provider: str | None = None
        self._provider_version: str | None = None
        self._model_family: str | None = None

    @property
    def provider(self) -> str:
        """Return the detected or default provider name."""
        self._ensure_provider_info()
        return self._provider or _DEFAULT_PROVIDER

    @property
    def provider_version(self) -> str | None:
        """Return the detected provider version, if available."""
        self._ensure_provider_info()
        return self._provider_version

    @property
    def model_family(self) -> str | None:
        """Return the detected model family, if available."""
        self._ensure_provider_info()
        return self._model_family

    def _ensure_provider_info(self) -> None:
        """Lazily detect provider info from the LibreTranslate /spec endpoint."""
        if self._provider is not None:
            return
        self._provider = _DEFAULT_PROVIDER
        self._model_family = _DEFAULT_MODEL_FAMILY
        try:
            response = self._client.get(
                f"{self._base_url}/spec",
                timeout=5.0,
            )
            response.raise_for_status()
            data = response.json()
            info = data.get("info", {})
            if info:
                version = info.get("version")
                if version:
                    self._provider_version = f"libretranslate-{version}"
        except Exception:
            logger.debug("Could not fetch LibreTranslate /spec; using default provider info")

    def translate(
        self,
        text: str,
        source_lang: str | None,
        target_lang: str = "en",
    ) -> str:
        """Translate *text* from *source_lang* to *target_lang*.

        Returns the original text when translation fails or when *text* is empty.
        """
        if not text.strip():
            return text

        payload = {
            "q": text,
            "source": source_lang if source_lang is not None else "auto",
            "target": target_lang,
        }

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(
                    f"{self._base_url}/translate",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return str(data["translatedText"])
            except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                last_exc = exc
                extra = ""
                if hasattr(exc, "response") and exc.response is not None:
                    extra = f" body={exc.response.text[:500]}"
                if attempt < self._max_retries:
                    # Exponential backoff with jitter: 1s → 2s → 4s → ...
                    # capped at 10s, plus up to 25% random jitter to prevent
                    # thundering herd when LibreTranslate restarts.
                    delay = min(2**attempt, 10.0)
                    delay += delay * random.uniform(0, 0.25)
                    logger.warning(
                        "Translation attempt %d failed (%s)%s, retrying in %.1fs",
                        attempt + 1,
                        exc,
                        extra,
                        delay,
                    )
                    time.sleep(delay)
                    continue
            except httpx.RequestError as exc:
                last_exc = exc
                logger.warning(
                    "Translation network error on attempt %d (%s)",
                    attempt + 1,
                    exc,
                )
                break
            except (ValueError, KeyError) as exc:
                last_exc = exc
                logger.warning("Translation response malformed (%s)", exc)
                break

        logger.warning(
            "Translation failed after %d attempts (%s), returning original",
            self._max_retries + 1,
            last_exc,
        )
        return text

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()
