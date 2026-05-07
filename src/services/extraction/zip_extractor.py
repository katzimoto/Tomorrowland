"""ZIP archive text extractor."""

from __future__ import annotations

import zipfile
from pathlib import Path


class ZipExtractor:
    """Extract file listing from ZIP archives."""

    def extract(self, path: Path) -> str:
        """Return a newline-separated list of filenames inside the archive."""
        try:
            with zipfile.ZipFile(path, "r") as zf:
                return "\n".join(zf.namelist())
        except (OSError, zipfile.BadZipFile):
            return ""
