"""Unit tests for PreviewService._generate_snippet fallback behaviour."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

from services.preview.service import SNIPPET_LENGTH, PreviewService


def _make_connection(*, content_text: str | None = None) -> MagicMock:
    """Return a mock SA connection whose SELECT returns *content_text*."""
    conn = MagicMock()

    # get_translated_text inner queries → no translation
    no_row = MagicMock()
    no_row.mappings.return_value.first.return_value = None

    # document_payloads row
    payload_mapping = MagicMock()
    payload_row = {"content_text": content_text} if content_text is not None else None
    payload_mapping.mappings.return_value.first.return_value = payload_row

    # Route calls: first few return no translation, last returns payload
    conn.execute.side_effect = [
        no_row,  # latest translation version query (get_translated_text)
        no_row,  # legacy translated_text query (get_translated_text)
        payload_mapping,  # document_payloads content_text query (_generate_snippet)
    ]
    return conn


def test_generate_snippet_reads_stored_content_text_when_file_deleted(
    tmp_path: Path,
) -> None:
    """Snippet must come from document_payloads when the source file is gone.

    Previously _generate_snippet fell back directly to file re-extraction.
    For temp-file connectors (SMB, Atlassian) the file is deleted after
    pipeline processing, so the snippet was always empty even though
    content_text was stored.
    """
    document_id = uuid4()
    deleted_path = str(tmp_path / "nonexistent.pptx")  # does not exist on disk

    conn = _make_connection(content_text="Slide 1 text\nSlide 2 text")
    svc = PreviewService(conn)

    snippet = svc._generate_snippet(
        document_id,
        deleted_path,
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )

    assert snippet == "Slide 1 text\nSlide 2 text"


def test_generate_snippet_truncates_stored_content_text() -> None:
    """Stored content_text longer than SNIPPET_LENGTH must be truncated."""
    document_id = uuid4()
    long_text = "x" * (SNIPPET_LENGTH + 500)

    conn = _make_connection(content_text=long_text)
    svc = PreviewService(conn)

    snippet = svc._generate_snippet(document_id, None, "text/plain")

    assert len(snippet) == SNIPPET_LENGTH


def test_generate_snippet_falls_through_to_file_when_no_payload(
    tmp_path: Path,
) -> None:
    """When document_payloads has no row, extraction from the live file is used."""
    document_id = uuid4()
    txt_file = tmp_path / "doc.txt"
    txt_file.write_text("file content", encoding="utf-8")

    conn = _make_connection(content_text=None)
    svc = PreviewService(conn)

    snippet = svc._generate_snippet(document_id, str(txt_file), "text/plain")

    assert snippet == "file content"


def test_generate_snippet_returns_empty_when_no_payload_and_file_missing() -> None:
    """No payload + missing file → empty snippet (not an error)."""
    document_id = uuid4()

    conn = _make_connection(content_text=None)
    svc = PreviewService(conn)

    snippet = svc._generate_snippet(document_id, "/nonexistent/path/file.pptx", "text/plain")

    assert snippet == ""


def test_sanitize_html_escapes_attribute_value_breakout() -> None:
    """A quote inside an attribute value must not break out and inject a handler."""
    raw = "<a title='x\" onmouseover=\"alert(1)'>hi</a>"
    out = PreviewService._sanitize_html(raw)
    assert 'onmouseover="alert(1)"' not in out
    assert "&quot;" in out


def test_sanitize_html_escapes_entity_smuggled_markup() -> None:
    """Entity-encoded markup decoded by the parser is re-escaped, not made live."""
    out = PreviewService._sanitize_html("&lt;img src=x onerror=alert(1)&gt;")
    assert "<img" not in out
    assert "&lt;img" in out


def test_sanitize_html_strips_javascript_and_obfuscated_urls() -> None:
    assert "javascript:" not in PreviewService._sanitize_html('<a href="javascript:alert(1)">x</a>')
    # Whitespace inside the scheme must not bypass the check.
    assert "href" not in PreviewService._sanitize_html('<a href="java\tscript:alert(1)">x</a>')


def test_sanitize_html_removes_dangerous_tags_keeps_safe_formatting() -> None:
    out = PreviewService._sanitize_html(
        '<p>hello<script>alert(1)</script> <strong onclick="x()">world</strong></p>'
    )
    assert "<script" not in out
    assert "alert(1)" not in out
    assert "onclick" not in out
    assert "<strong>world</strong>" in out
    assert "hello" in out
