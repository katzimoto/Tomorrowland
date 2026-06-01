"""HTML text extractor."""

from __future__ import annotations

import logging
from html.parser import HTMLParser
from pathlib import Path

from services.extraction.base import ExtractionResult

logger = logging.getLogger(__name__)

_SKIP_TAGS = {"script", "style", "nav", "footer"}


class _HTMLTextParser(HTMLParser):
    """Collect visible text from HTML, dropping tags and scripts.

    Uses a depth counter per skip-tag family so nested skip elements
    (e.g. ``<nav><style>…</style>more nav text</nav>``) are handled
    correctly: the first matching open-tag increments the counter and
    text stays suppressed until the matching close-tag brings the counter
    back to zero.
    """

    def __init__(self) -> None:
        super().__init__()
        self._texts: list[str] = []
        self._skip_depth: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Self-closing tags like <script src="..." /> do not toggle skip state
        # because they have no content to exclude.
        pass

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._texts.append(stripped)

    def result(self) -> str:
        return "\n".join(self._texts)


class HtmlExtractor:
    """Extract visible text from HTML files."""

    def extract(self, path: Path) -> ExtractionResult:
        """Return visible text with tags, scripts, and styles stripped.

        Tries UTF-8 first, then falls back to latin-1 so that legacy
        ISO-8859-1 / Windows-1252 HTML files are not silently dropped.
        """
        raw: str | None = None
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            logger.debug("HTML file is not valid UTF-8, falling back to latin-1: %s", path)
        except OSError:
            return ExtractionResult(text="")

        if raw is None:
            # Fallback: latin-1 never raises a decode error and covers the
            # Windows-1252 / ISO-8859-1 range used by most legacy HTML pages.
            try:
                raw = path.read_text(encoding="latin-1")
            except OSError:
                return ExtractionResult(text="")

        parser = _HTMLTextParser()
        parser.feed(raw)
        return ExtractionResult(text=parser.result())
