"""OneNote ``.one`` section-file extractor.

Uses the optional ``pyOneNote`` library when available; otherwise extraction
returns empty text.  The parser is treated as an unsafe external component,
so all parse failures are caught and converted to empty results with a log
warning.

Embedded files and images are represented as metadata placeholders in the
extracted text rather than expanded as child documents or executed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from services.extraction.base import (
    ExtractionResult,
    LocationSegment,
    ParserCapabilities,
    QualityTier,
)

logger = logging.getLogger(__name__)

_ONE_MIME = "application/ms-onenote"

# OneNote file magic bytes recognised by pyOneNote.
_ONE_MAGIC_HEADERS: tuple[bytes, ...] = (
    b"\xe4\x52\x5c\x7b\x8c\xd8\xa7\x4d\xae\xb1\x53\x78\xd0\x29\x96\xd3",
    b"\xa1\x2f\xff\x43\xd9\xef\x76\x4c\x9e\xe2\x10\xea\x57\x22\x76\x5f",
)

# Property values that typically contain readable text.
_TEXT_PROPERTY_NAMES = {
    "RichEditTextUnicode",
    "CachedTitleString",
    "CachedTitleStringFromPage",
    "TextRunData",
    "TextExtendedAscii",
    "WzHyperlinkUrl",
    "EmbeddedFileName",
    "ImageFilename",
    "ImageAltText",
    "SectionDisplayName",
}

# Node types that mark page boundaries.
_PAGE_NODE_TYPES = {
    "jcidPageNode",
    "jcidTitleNode",
}

# Node types that contain embedded objects / images.
_EMBEDDED_NODE_TYPES = {
    "jcidEmbeddedFileNode",
    "jcidImageNode",
}


def _is_onenote_file(path: Path) -> bool:
    """Return True when *path* starts with a known OneNote magic header."""
    try:
        with open(path, "rb") as fh:
            header = fh.read(16)
    except OSError:
        return False
    return header in _ONE_MAGIC_HEADERS


def _safe_str(value: Any) -> str:
    """Convert a property value to a safe string, ignoring bytes/unknown types."""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, dict)):
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-16", errors="ignore").strip("\x00")
        except UnicodeDecodeError:
            return ""
    return str(value) if value is not None else ""


def _extract_text_from_properties(properties: list[dict[str, Any]]) -> list[str]:
    """Collect readable text fragments from a list of property dicts."""
    fragments: list[str] = []
    seen: set[str] = set()
    for prop in properties:
        val = prop.get("val") if isinstance(prop, dict) else None
        if not isinstance(val, dict):
            continue
        for key, raw in val.items():
            if key not in _TEXT_PROPERTY_NAMES:
                continue
            text = _safe_str(raw).strip()
            if text and text not in seen:
                seen.add(text)
                fragments.append(text)
    return fragments


def _collect_pages(properties: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group OneNote properties into page-like structures.

    Pages are identified by ``jcidPageNode`` objects; their title is taken from
    the nearest ``CachedTitleString*`` property.  Outline/text nodes that are
    not obviously inside a page are still emitted as top-level content.
    """
    pages: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def _flush() -> None:
        nonlocal current
        if current is not None:
            pages.append(current)
            current = None

    def _ensure_current(title: str = "") -> dict[str, Any]:
        nonlocal current
        if current is None:
            current = {"title": title, "texts": [], "embedded": []}
        elif title:
            current["title"] = title
        return current

    for prop in properties:
        if not isinstance(prop, dict):
            continue
        node_type = prop.get("type", "")
        raw_val = prop.get("val")
        val: dict[str, Any] = raw_val if isinstance(raw_val, dict) else {}

        if node_type in _PAGE_NODE_TYPES:
            _flush()
            title = ""
            for key in ("CachedTitleString", "CachedTitleStringFromPage"):
                if key in val:
                    title = _safe_str(val[key]).strip()
                    break
            current = {"title": title, "texts": [], "embedded": []}
            # Page-level text can also live on the page node itself.
            current["texts"].extend(_extract_text_from_properties([prop]))
            continue

        if node_type in _EMBEDDED_NODE_TYPES:
            name = ""
            for key in ("EmbeddedFileName", "ImageFilename", "ImageAltText"):
                if key in val:
                    candidate = _safe_str(val[key]).strip()
                    if candidate:
                        name = candidate
                        break
            obj_type = "embedded-file" if node_type == "jcidEmbeddedFileNode" else "image"
            _ensure_current()["embedded"].append({"type": obj_type, "name": name or "unknown"})
            continue

        # Ordinary text-bearing node.
        texts = _extract_text_from_properties([prop])
        if texts:
            _ensure_current()["texts"].extend(texts)

    _flush()
    return pages


def _build_text_and_segments(
    pages: list[dict[str, Any]],
) -> tuple[str, list[LocationSegment]]:
    """Build Markdown-like text and page-boundary location segments."""
    parts: list[str] = []
    segments: list[LocationSegment] = []
    offset = 0
    for page in pages:
        title = page.get("title", "")
        page_parts: list[str] = []
        if title:
            page_parts.append(f"# {title}")
        for text in page.get("texts", []):
            if text == title:
                continue
            page_parts.append(text)
        embedded = page.get("embedded", [])
        if embedded:
            page_parts.append("")
            page_parts.append("## Embedded objects")
            for obj in embedded:
                label = obj.get("name") or "unknown"
                page_parts.append(f"- [{obj.get('type', 'object')}] {label}")
        if page_parts and page_parts[-1] != "":
            page_parts.append("")

        page_text = "\n".join(page_parts)
        if parts:
            parts.append("")
            offset += 1
        start = offset
        parts.append(page_text)
        offset += len(page_text)
        if title:
            segments.append(
                LocationSegment(
                    start_char=start,
                    end_char=offset,
                    section_heading=title,
                )
            )
    text = "\n".join(parts)
    return text, segments


class OneNoteExtractor:
    """Extract text and page metadata from Microsoft OneNote ``.one`` files.

    Requires the optional ``pyOneNote`` package.  When it is not installed, or
    when the file is corrupt/unsupported, extraction returns an empty result
    rather than raising.
    """

    _CAPS = ParserCapabilities(
        parser_name="onenote",
        parser_version="0.1.0",
        supported_mime_types=(_ONE_MIME,),
        quality_tier=QualityTier.STANDARD,
    )

    def capabilities(self) -> ParserCapabilities:
        return self._CAPS

    def extract(self, path: Path) -> ExtractionResult:
        """Return extracted text and page-level metadata from a ``.one`` file."""
        if not path.exists():
            return ExtractionResult(text="")

        if not _is_onenote_file(path):
            logger.warning("File does not have a OneNote magic header path=%s", path)
            return ExtractionResult(text="")

        try:
            from pyOneNote.OneDocument import OneDocment
        except ImportError:
            logger.debug("pyOneNote not installed; skipping OneNote extraction path=%s", path)
            return ExtractionResult(text="")

        try:
            with open(path, "rb") as fh:
                document = OneDocment(fh)
                data = document.get_json()
        except Exception:
            logger.warning("Failed to parse OneNote file path=%s", path, exc_info=True)
            return ExtractionResult(text="")

        properties = data.get("properties", []) if isinstance(data, dict) else []
        if not isinstance(properties, list):
            return ExtractionResult(text="")

        pages = _collect_pages(properties)
        text, segments = _build_text_and_segments(pages)

        return ExtractionResult(text=text, location_segments=segments)
