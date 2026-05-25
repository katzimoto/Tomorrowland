"""Lightweight language detection for extracted document text.

Uses ``langdetect`` (pure-Python, no network calls) to infer the ISO 639-1
language code of a text excerpt.  Returns ``None`` when the text is too
short, detection confidence is low, or ``langdetect`` is not installed.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_MIN_TEXT_LENGTH = 100
_MIN_CONFIDENCE = 0.80

try:
    from langdetect import DetectorFactory, detect_langs  # type: ignore[import-not-found]

    # Pin the random seed so results are reproducible across runs.
    DetectorFactory.seed = 0
    _LANGDETECT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _LANGDETECT_AVAILABLE = False


class LanguageDetector:
    """Detect the dominant language of a text string."""

    def detect(self, text: str) -> str | None:
        """Return an ISO 639-1 language code or *None*.

        Returns *None* when:
        - ``langdetect`` is not installed
        - *text* is shorter than 100 characters
        - the top candidate's probability is below 0.80
        - detection raises any exception
        """
        if not _LANGDETECT_AVAILABLE:
            return None
        if len(text) < _MIN_TEXT_LENGTH:
            return None
        try:
            candidates = detect_langs(text)
            if not candidates:
                return None
            top = candidates[0]
            if top.prob < _MIN_CONFIDENCE:
                logger.debug(
                    "Language detection confidence too low lang=%s prob=%.2f",
                    top.lang,
                    top.prob,
                )
                return None
            return str(top.lang)
        except Exception:
            logger.debug("Language detection failed", exc_info=True)
            return None
