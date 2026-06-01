"""LibreTranslate HTTP client with timeout, retry, and fallback."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class LibreTranslateClient:
    """Self-hosted LibreTranslate client with graceful fallback.

    On any network or server error the original text is returned unchanged
    so that ingestion never blocks on translation.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        timeout: float = 30.0,
        max_retries: int = 1,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = httpx.Client(timeout=timeout)

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
                    logger.warning(
                        "Translation attempt %d failed (%s)%s, retrying",
                        attempt + 1,
                        exc,
                        extra,
                    )
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
