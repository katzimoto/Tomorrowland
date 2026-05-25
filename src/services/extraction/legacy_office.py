"""Legacy Office format extractor via LibreOffice headless conversion.

Handles ``.doc``, ``.xls``, and ``.ppt`` (Word/Excel/PowerPoint 97-2003)
by spawning ``soffice --headless --convert-to txt``.  Requires LibreOffice
to be present in PATH.

Only registered when ``ENABLE_LEGACY_OFFICE=true`` is set.  Times out after
30 seconds; returns an empty string on timeout, non-zero exit, or any other
failure.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 30


class LegacyOfficeExtractor:
    """Convert legacy Office files to plain text via LibreOffice headless."""

    def extract(self, path: Path) -> str:
        """Return plain text by converting *path* with LibreOffice.

        Writes the converted ``.txt`` file to a temporary directory and reads
        it back.  Cleans up on completion regardless of outcome.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                result = subprocess.run(
                    [
                        "soffice",
                        "--headless",
                        "--convert-to",
                        "txt:Text",
                        "--outdir",
                        tmpdir,
                        str(path),
                    ],
                    capture_output=True,
                    timeout=_TIMEOUT_SECONDS,
                )
            except FileNotFoundError:
                logger.debug("soffice not found in PATH; legacy Office extraction unavailable")
                return ""
            except subprocess.TimeoutExpired:
                logger.warning(
                    "LibreOffice conversion timed out after %ds path=%s",
                    _TIMEOUT_SECONDS,
                    path,
                )
                return ""
            except Exception:
                logger.debug("LibreOffice conversion failed for path=%s", path, exc_info=True)
                return ""

            if result.returncode != 0:
                logger.debug(
                    "soffice exited with code=%d path=%s stderr=%s",
                    result.returncode,
                    path,
                    result.stderr[:200],
                )
                return ""

            # LibreOffice names the output file after the input stem.
            out_path = Path(tmpdir) / (path.stem + ".txt")
            if not out_path.exists():
                logger.debug("soffice produced no output for path=%s", path)
                return ""

            try:
                return out_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return ""
