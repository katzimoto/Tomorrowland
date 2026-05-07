"""HTML text extractor."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


class _HTMLTextParser(HTMLParser):
    """Collect visible text from HTML, dropping tags and scripts."""

    def __init__(self) -> None:
        super().__init__()
        self._texts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "nav", "footer"}:
            self._skip = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Self-closing tags like <script src="..." /> do not toggle skip state
        # because they have no content to exclude.
        pass

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "nav", "footer"}:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self._texts.append(stripped)

    def result(self) -> str:
        return "\n".join(self._texts)


class HtmlExtractor:
    """Extract visible text from HTML files."""

    def extract(self, path: Path) -> str:
        """Return visible text with tags, scripts, and styles stripped."""
        try:
            raw = path.read_text(encoding="utf-8")
            parser = _HTMLTextParser()
            parser.feed(raw)
            return parser.result()
        except (OSError, UnicodeDecodeError):
            return ""
