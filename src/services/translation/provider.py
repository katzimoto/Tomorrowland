"""Pluggable translation provider interface (#729).

Workers depend on this interface instead of a concrete client, so future
providers (OPUS-MT, NLLB, cloud APIs) can be swapped in without changing
pipeline logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class TranslationProvider(ABC):
    """Abstract base class for translation providers.

    Every provider must report its identity, capabilities, and health,
    and expose a ``translate`` method compatible with the segment pipeline
    (positional args: ``text, source_lang, target_lang``).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name (e.g. ``"libretranslate_argos"``)."""
        ...

    @property
    @abstractmethod
    def version(self) -> str | None:
        """Detected provider version string, or *None* when unknown."""
        ...

    @property
    @abstractmethod
    def model_family(self) -> str | None:
        """Model family identifier (e.g. ``"argos"``)."""
        ...

    @property
    def capabilities(self) -> dict[str, Any]:
        """Feature flags and limits the provider advertises.

        Subclasses should override to report language pairs, max text
        length, batch support, etc.  Default returns an empty dict.

        Example return value::

            {
                "max_chars_per_request": 5000,
                "supports_batch": False,
                "source_languages": ["en", "fr", "de", "he", "zh", "auto"],
                "target_languages": ["en", "fr", "de", "he", "zh"],
            }
        """
        return {}

    @abstractmethod
    def translate(
        self,
        text: str,
        source_lang: str | None,
        target_lang: str = "en",
    ) -> str:
        """Translate *text* from *source_lang* to *target_lang*.

        Must return the original text on unrecoverable errors so that
        ingestion is never blocked.
        """
        ...

    def health(self) -> dict[str, Any]:
        """Return a health-check snapshot for admin diagnostics.

        Default implementation reports ``status="unknown"``.
        Subclasses should override to perform a lightweight probe
        (e.g. a ``/languages`` GET against the upstream service).

        Example return value::

            {
                "status": "healthy",
                "provider": "libretranslate_argos",
                "version": "libretranslate-1.6.0",
                "latency_ms": 12.3,
            }
        """
        return {"status": "unknown", "provider": self.name}

    def close(self) -> None:  # noqa: B027
        """Release any underlying resources (HTTP clients, etc.).

        Default is a no-op; subclasses with state should override.
        """
