"""MIME type detection for ingested files.

Uses content-sniffing via ``python-magic`` when available, falling back to
the stdlib ``mimetypes`` module (extension-based) so the system degrades
gracefully when libmagic is not installed.
"""

from __future__ import annotations

import logging
import mimetypes
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
        2. ``mimetypes.guess_type`` on *filename* (or *path.name*).
        3. Fallback: ``"application/octet-stream"``.
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
                    return detected
            except Exception:
                logger.debug("python-magic failed for path=%s; falling back to mimetypes", path)

        if guessed:
            return guessed

        return "application/octet-stream"


_detector = MimeDetector()


def detect_mime_type(path: Path, filename: str | None = None) -> str:
    """Module-level convenience wrapper around :class:`MimeDetector`."""
    return _detector.detect(path, filename)
