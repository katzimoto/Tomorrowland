"""EPUB extractor using ebooklib."""

from __future__ import annotations

import re
from pathlib import Path

# re.DOTALL so tags spanning multiple lines (e.g. attributes on separate lines)
# are fully stripped rather than leaving tag fragments in the extracted text.
_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    return _WHITESPACE_RE.sub(" ", text).strip()


class EpubExtractor:
    """Extract plain text from EPUB files.

    Iterates the spine items in document order and strips HTML markup.
    Returns an empty string when ``ebooklib`` is not installed or the
    file is unreadable.
    """

    def extract(self, path: Path) -> str:
        """Return concatenated plain text from all spine items."""
        try:
            import ebooklib  # type: ignore[import-not-found]
            from ebooklib import epub
        except ImportError:
            return ""

        try:
            book = epub.read_epub(str(path), options={"ignore_ncx": True})
        except Exception:
            return ""

        parts: list[str] = []
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            try:
                content = item.get_content().decode("utf-8", errors="replace")
                text = _strip_html(content)
                if text:
                    parts.append(text)
            except Exception:
                continue

        return "\n".join(parts)
