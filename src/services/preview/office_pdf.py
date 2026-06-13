"""Office (DOCX/PPTX/…) → PDF preview renderer via LibreOffice headless.

Converts the source document to a single ``converted.pdf`` artifact that the
existing pdf.js viewer renders with page/slide navigation, zoom, and search.
Runs only in the preview worker (the soffice image), never in the API process.

LibreOffice ``--convert-to`` does not execute document macros; ``--norestore``
plus a per-job UserInstallation profile isolates state. Network access is not
needed for conversion and is denied to the worker at the compose level.
"""

from __future__ import annotations

import io
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader

logger = logging.getLogger(__name__)


class OfficeRenderError(RuntimeError):
    """Raised when LibreOffice conversion fails. ``category`` feeds the manifest."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class RenderedOffice:
    """Office renderer output consumed by the render orchestrator."""

    # artifact_id -> (relative filename, content type, bytes)
    artifacts: dict[str, tuple[str, str, bytes]]
    page_count: int | None
    truncated: bool


def _convert_to_pdf(source_path: Path, output_dir: Path, timeout: float) -> Path:
    """Run soffice headless to produce a PDF in ``output_dir``; return its path."""
    profile = output_dir / ".loprofile"
    try:
        result = subprocess.run(
            [
                "soffice",
                "--headless",
                "--norestore",
                "--nofirststartwizard",
                f"-env:UserInstallation=file://{profile}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output_dir),
                str(source_path),
            ],
            capture_output=True,
            timeout=timeout,
            check=False,
            # Isolate HOME so soffice never touches the worker's real home dir.
            env={"HOME": str(output_dir), "PATH": _system_path()},
        )
    except FileNotFoundError as exc:
        raise OfficeRenderError("renderer_unavailable", "soffice not found in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise OfficeRenderError("render_timeout", f"conversion exceeded {timeout}s") from exc

    pdf_path = output_dir / f"{source_path.stem}.pdf"
    if result.returncode != 0 or not pdf_path.is_file():
        detail = result.stderr.decode("utf-8", "replace").splitlines()[-1:] or ["unknown"]
        raise OfficeRenderError("render", f"soffice conversion failed: {detail[0]}")
    return pdf_path


def _system_path() -> str:
    import os

    return os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")


def render_office_pdf(
    source_path: Path,
    *,
    timeout: float,
    max_pages: int,
) -> RenderedOffice:
    """Convert an Office document to a cached PDF artifact.

    Raises :class:`OfficeRenderError` (with a manifest ``category``) on any
    deterministic failure so the orchestrator can persist a terminal state.
    """
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        pdf_path = _convert_to_pdf(source_path, out_dir, timeout)
        pdf_bytes = pdf_path.read_bytes()

    page_count: int | None = None
    truncated = False
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        page_count = len(reader.pages)
    except Exception:
        logger.warning("could not read converted PDF page count for %s", source_path.name)

    if page_count is not None and page_count > max_pages:
        truncated = True

    artifacts: dict[str, tuple[str, str, bytes]] = {
        "converted-pdf": ("converted.pdf", "application/pdf", pdf_bytes),
    }
    return RenderedOffice(artifacts=artifacts, page_count=page_count, truncated=truncated)


def build_office_manifest_section(rendered: RenderedOffice) -> dict[str, Any]:
    """The manifest ``office`` section for a converted Office document."""
    return {
        "pdf_artifact_id": "converted-pdf",
        "page_count": rendered.page_count,
        "text_fallback": True,
    }
