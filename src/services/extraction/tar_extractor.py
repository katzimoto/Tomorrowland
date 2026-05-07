"""TAR archive text extractor."""

from __future__ import annotations

import tarfile
from pathlib import Path


class TarExtractor:
    """Extract file listing from TAR archives."""

    def extract(self, path: Path) -> str:
        """Return a newline-separated list of filenames inside the archive."""
        try:
            with tarfile.open(path, "r:*") as tf:
                return "\n".join(m.name for m in tf.getmembers())
        except (OSError, tarfile.TarError):
            return ""
