"""MIME type detection for ingested files.

Uses a three-layer content-sniffing strategy so that the system degrades
gracefully when optional libraries are not installed:

1. **Magika** — Google's ML-based file type detector (``magika`` package,
   included in core dependencies).  Results above
   :data:`_MAGIKA_SCORE_THRESHOLD` (0.80) are used directly; lower-confidence
   results fall through to the next layer.  Magika correctly identifies Office
   Open XML formats (DOCX, XLSX, PPTX) without needing to inspect the ZIP
   container, making it the most reliable layer for ambiguous files.

2. **python-magic** — ``libmagic`` content sniffing.  Handles common binary
   formats quickly but may return generic types (``text/plain``,
   ``application/zip``) for formats it cannot fully identify.

3. **mimetypes + sniff_office_mime** — stdlib-only fallback.  Extension-based
   guessing supplemented by raw ZIP/OLE byte inspection so that Office files
   with no extension are still identified correctly.
"""

from __future__ import annotations

import logging
import mimetypes
import zipfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import magic as _magic

    _MAGIC_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MAGIC_AVAILABLE = False

try:
    from magika import Magika as _MagikaClass

    _MAGIKA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MAGIKA_AVAILABLE = False

# Minimum Magika confidence score required to accept the ML detection result.
# Below this threshold the fallback chain (python-magic → mimetypes →
# sniff_office_mime) takes over.  0.80 lets through DOCX/XLSX/PPTX/PDF/EPUB
# (all score ≥ 0.90 on typical files) while skipping low-confidence results
# for plain text and email formats where extension-based detection is more
# reliable.
_MAGIKA_SCORE_THRESHOLD: float = 0.80

# Lazy singleton — Magika loads an ONNX neural-network model on first use;
# instantiating it at import time would slow every worker startup.
_magika_singleton: Any = None


def _get_magika() -> Any:
    """Return the module-level Magika singleton, creating it on first call."""
    global _magika_singleton
    if _magika_singleton is None:
        _magika_singleton = _MagikaClass()  # noqa: F821  # unbound when magika not installed
    return _magika_singleton


# Supplement stdlib mimetypes with types it does not know about.
# This ensures the extension-based fallback path works for these formats
# even when libmagic is not installed.
mimetypes.add_type("application/vnd.ms-outlook", ".msg")
mimetypes.add_type("text/plain", ".log")
mimetypes.add_type("text/plain", ".ini")
mimetypes.add_type("text/plain", ".conf")
mimetypes.add_type("application/toml", ".toml")

# --- Office Open XML magic bytes ----------------------------------------

_ZIP_MAGIC = b"PK\x03\x04"
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

# Canonical MIME constants (duplicated from registry to avoid circular imports)
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

# Ordered: first marker found wins.  Covers standard and macro-enabled variants.
_OOXML_MARKERS: tuple[tuple[str, str], ...] = (
    ("word/document.xml", _DOCX_MIME),
    ("xl/workbook.xml", _XLSX_MIME),
    ("ppt/presentation.xml", _PPTX_MIME),
    # Macro-enabled / template variants share the same ZIP structure
    ("word/", _DOCX_MIME),
    ("xl/", _XLSX_MIME),
    ("ppt/", _PPTX_MIME),
)


def sniff_office_mime(path: Path) -> str | None:
    """Return the specific Office MIME type by inspecting the file's raw content.

    Handles two container formats without any external libraries:

    * **ZIP** (``PK\\x03\\x04``) — opens the archive and checks for well-known
      Office Open XML entry prefixes (``word/``, ``xl/``, ``ppt/``) and the
      ODF ``mimetype`` entry.  Returns *None* for ZIPs that are not recognised
      Office containers (plain ZIP, EPUB, JAR, …) so the caller can fall
      through to normal ZIP handling.

    * **OLE Compound Document** (``\\xD0\\xCF\\x11\\xE0…``) — only the magic
      bytes are checked here; sub-type identification (doc vs. xls vs. ppt)
      requires parsing the OLE directory, which is handled by the extractors
      themselves.  Returns ``"application/x-ole-storage"`` as a signal so
      callers can attempt format-specific extraction.

    Returns ``None`` when the file cannot be opened or is not a recognised
    Office container.
    """
    try:
        with open(path, "rb") as fh:
            header = fh.read(8)
    except OSError:
        return None

    if header[:4] == _ZIP_MAGIC:
        return _sniff_zip_office(path)

    if header == _OLE_MAGIC:
        # Exact sub-type (doc/xls/ppt) requires OLE directory parsing;
        # return a generic compound-document type as a hint.
        return "application/x-ole-storage"

    return None


def _sniff_zip_office(path: Path) -> str | None:
    """Peek inside a ZIP to identify an Office Open XML or ODF container."""
    try:
        with zipfile.ZipFile(str(path), "r") as zf:
            names = set(zf.namelist())

            # Office Open XML: check for distinctive top-level directory
            for marker, mime in _OOXML_MARKERS:
                if any(n == marker or n.startswith(marker) for n in names):
                    return mime

            # ODF formats embed their MIME type in a plain-text 'mimetype' entry
            if "mimetype" in names:
                odf_mime = zf.read("mimetype").decode("ascii", errors="ignore").strip()
                if odf_mime:
                    return odf_mime
    except Exception:  # noqa: BLE001
        pass
    return None


class MimeDetector:
    """Detect the MIME type of a file by content and extension."""

    # Generic MIME types that libmagic may return for files whose format is
    # better identified by file extension (e.g. EML files detected as text/plain).
    _GENERIC_TYPES: frozenset[str] = frozenset(
        {"text/plain", "application/octet-stream", "application/zip"}
    )

    def detect(self, path: Path, filename: str | None = None) -> str:
        """Return the MIME type for *path*.

        Resolution order:
        1. **Magika** ML-based detection (if ``magika`` is installed and the
           confidence score is ≥ :data:`_MAGIKA_SCORE_THRESHOLD`).  When the
           result is a generic type (e.g. ``text/plain``) and the extension-
           based guess is more specific, the extension wins.
        2. **python-magic** content-sniffing (if libmagic is installed).
           If the sniffed type is generic (e.g. ``text/plain``), the
           extension-based guess is preferred when it is more specific.
           If the sniffed type is ``application/zip`` and no extension is
           available, falls through to Office content sniffing.
        3. ``mimetypes.guess_type`` on *filename* (or *path.name*).
        4. ``sniff_office_mime`` — stdlib-only ZIP/OLE inspection.
        5. Fallback: ``"application/octet-stream"``.
        """
        name = filename or path.name

        # Always compute the extension-based guess so we can fall back to it.
        guessed, _ = mimetypes.guess_type(name)

        # --- Layer 1: Magika (ML-based, highest accuracy) -------------------
        if _MAGIKA_AVAILABLE:
            try:
                result = _get_magika().identify_path(path)
                if result.score >= _MAGIKA_SCORE_THRESHOLD:
                    magika_mime: str = result.output.mime_type
                    if magika_mime:
                        # Prefer a specific extension-based type over a generic
                        # Magika result (e.g. message/rfc822 over text/plain for
                        # .eml files).
                        if magika_mime in self._GENERIC_TYPES and guessed:
                            return guessed
                        return magika_mime
            except Exception:
                logger.debug("magika failed for path=%s; falling back", path)

        # --- Layer 2: python-magic ------------------------------------------
        if _MAGIC_AVAILABLE:
            try:
                detected: str = _magic.from_file(str(path), mime=True)
                if detected and detected != "application/octet-stream":
                    # Prefer a specific extension-based type over a generic
                    # libmagic result (e.g. message/rfc822 over text/plain for
                    # .eml files, or application/epub+zip over application/zip).
                    if detected in self._GENERIC_TYPES and guessed:
                        return guessed
                    # libmagic sees DOCX/XLSX/PPTX as application/zip; when no
                    # extension is available use content sniffing to be precise.
                    if detected == "application/zip" and not guessed:
                        sniffed = sniff_office_mime(path)
                        if sniffed and sniffed != "application/zip":
                            return sniffed
                    return detected
            except Exception:
                logger.debug("python-magic failed for path=%s; falling back to mimetypes", path)

        if guessed:
            return guessed

        # No extension — try content sniffing before giving up.
        sniffed = sniff_office_mime(path)
        if sniffed:
            return sniffed

        return "application/octet-stream"


_detector = MimeDetector()


def detect_mime_type(path: Path, filename: str | None = None) -> str:
    """Module-level convenience wrapper around :class:`MimeDetector`."""
    return _detector.detect(path, filename)
