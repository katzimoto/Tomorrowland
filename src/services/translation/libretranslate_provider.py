"""LibreTranslate Argos translation provider — wraps LibreTranslateClient."""

from __future__ import annotations

from typing import Any

from services.translation.client import LibreTranslateClient
from services.translation.provider import TranslationProvider

_DEFAULT_NAME = "libretranslate_argos"
_DEFAULT_MODEL_FAMILY = "argos"


class LibreTranslateArgosProvider(TranslationProvider):
    """Translation provider backed by a self-hosted LibreTranslate instance.

    Wraps :class:`~services.translation.client.LibreTranslateClient` so that
    workers depend on the :class:`TranslationProvider` interface instead of
    the concrete client.  This makes room for future providers (OPUS-MT,
    NLLB, cloud APIs) without changing pipeline logic.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._client = LibreTranslateClient(
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )

    # -- Provider identity --------------------------------------------------

    @property
    def name(self) -> str:
        return self._client.provider or _DEFAULT_NAME

    @property
    def version(self) -> str | None:
        return self._client.provider_version

    @property
    def model_family(self) -> str | None:
        return self._client.model_family or _DEFAULT_MODEL_FAMILY

    # -- Capabilities -------------------------------------------------------

    @property
    def capabilities(self) -> dict[str, Any]:
        return {
            "max_chars_per_request": 5000,
            "supports_batch": False,
            "supports_auto_detect": True,
            "model_family": self.model_family,
        }

    # -- Translation --------------------------------------------------------

    def translate(
        self,
        text: str,
        source_lang: str | None,
        target_lang: str = "en",
    ) -> str:
        return self._client.translate(text, source_lang=source_lang, target_lang=target_lang)

    # -- Health -------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Probe LibreTranslate availability via the /languages endpoint.

        Returns a status snapshot suitable for admin diagnostics.
        """
        import time

        start = time.monotonic()
        try:
            response = self._client._client.get(
                f"{self._client._base_url}/languages",
                timeout=5.0,
            )
            response.raise_for_status()
            elapsed_ms = round((time.monotonic() - start) * 1000, 1)
            return {
                "status": "healthy",
                "provider": self.name,
                "version": self.version,
                "latency_ms": elapsed_ms,
            }
        except Exception:
            elapsed_ms = round((time.monotonic() - start) * 1000, 1)
            return {
                "status": "unhealthy",
                "provider": self.name,
                "version": self.version,
                "latency_ms": elapsed_ms,
            }

    # -- Lifecycle ----------------------------------------------------------

    def close(self) -> None:
        self._client.close()
