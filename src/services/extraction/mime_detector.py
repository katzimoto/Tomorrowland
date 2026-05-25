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


class MimeDetector:
    """Detect the MIME type of a file by content and extension."""

    def detect(self, path: Path, filename: str | None = None) -> str:
        """Return the MIME type for *path*.

        Resolution order:
        1. ``python-magic`` content-sniffing (if libmagic is installed).
        2. ``mimetypes.guess_type`` on *filename* (or *path.name*).
        3. Fallback: ``"application/octet-stream"``.
        """
        name = filename or path.name

        if _MAGIC_AVAILABLE:
            try:
                detected: str = _magic.from_file(str(path), mime=True)
                if detected and detected != "application/octet-stream":
                    return detected
            except Exception:
                logger.debug("python-magic failed for path=%s; falling back to mimetypes", path)

        guessed, _ = mimetypes.guess_type(name)
        if guessed:
            return guessed

        return "application/octet-stream"


_detector = MimeDetector()


def detect_mime_type(path: Path, filename: str | None = None) -> str:
    """Module-level convenience wrapper around :class:`MimeDetector`."""
    return _detector.detect(path, filename)
