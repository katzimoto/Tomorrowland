"""MIME type detection for ingested files.

Uses content-sniffing via ``python-magic`` when available, falling back to
the stdlib ``mimetypes`` module (extension-based) so the system degrades
gracefully when libmagic is not installed.

A second content-sniffing layer (``sniff_office_mime``) uses only the stdlib
``zipfile`` module to identify ZIP-based Office Open XML formats (DOCX, XLSX,
PPTX, ODF) and detects OLE Compound Document magic bytes for legacy Office
formats (.doc, .xls, .ppt) — no external libraries required.  This ensures
correct MIME detection even when files lack extensions and python-magic is
unavailable.
"""

from __future__ import annotations

import logging
import mimetypes
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import magic as _magic  # type: ignore[import-not-found]

    _MAGIC_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MAGIC_AVAILABLE = False

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
_OLE_MAGIC = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"

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
        1. ``python-magic`` content-sniffing (if libmagic is installed).
           If the sniffed type is generic (e.g. ``text/plain``), the
           extension-based guess is preferred when it is more specific.
           If the sniffed type is ``application/zip`` and no extension is
           available, falls through to Office content sniffing.
        2. ``mimetypes.guess_type`` on *filename* (or *path.name*).
        3. ``sniff_office_mime`` — stdlib-only ZIP/OLE inspection.
        4. Fallback: ``"application/octet-stream"``.
        """
        name = filename or path.name

        # Always compute the extension-based guess so we can fall back to it.
        guessed, _ = mimetypes.guess_type(name)

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
