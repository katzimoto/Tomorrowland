"""Regression tests for extractor bugs fixed in fix/extractor-bugs.

Each test is named after the bug it prevents regressing.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.extraction.docx import DocxExtractor
from services.extraction.html import HtmlExtractor
from services.extraction.registry import ExtractorRegistry
from services.extraction.rtf import RtfExtractor
from services.extraction.xlsx import XlsxExtractor
from services.extraction.xml_extractor import XmlExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Bug 1: HTML nested skip-tag depth counter
# ---------------------------------------------------------------------------


def test_html_nested_skip_tags_suppressed(tmp_path: Path) -> None:
    """Text inside nested skip elements must not leak into output.

    <nav><style>css</style>still-nav-text</nav>
    Before the fix `_skip` was reset to False on </style>, so
    'still-nav-text' was captured.  After the fix the depth counter keeps
    _skip_depth > 0 until </nav>.
    """
    p = tmp_path / "nested.html"
    p.write_text(
        "<html><body>"
        "<p>visible</p>"
        "<nav><style>.x{color:red}</style>nav-leak-text</nav>"
        "<p>also visible</p>"
        "</body></html>",
        encoding="utf-8",
    )
    result = HtmlExtractor().extract(p)
    assert "visible" in result.text
    assert "also visible" in result.text
    assert "nav-leak-text" not in result.text
    assert ".x{color:red}" not in result.text


def test_html_deeply_nested_skip_not_leaked(tmp_path: Path) -> None:
    """Three levels of skip nesting: all suppressed until outermost closes."""
    p = tmp_path / "deep.html"
    p.write_text(
        "<html><body>"
        "<nav><div><script>alert(1)</script>inner-nav</div>outer-nav</nav>"
        "<p>content</p>"
        "</body></html>",
        encoding="utf-8",
    )
    result = HtmlExtractor().extract(p)
    assert "content" in result.text
    assert "alert" not in result.text
    assert "inner-nav" not in result.text
    assert "outer-nav" not in result.text


# ---------------------------------------------------------------------------
# Bug 2: HTML encoding fallback
# ---------------------------------------------------------------------------


def test_html_extractor_latin1_file_not_empty(tmp_path: Path) -> None:
    """An ISO-8859-1 HTML file must not silently return empty string."""
    p = tmp_path / "latin1.html"
    # Write 'café' as raw latin-1 bytes — NOT valid UTF-8.
    p.write_bytes(b"<html><body><p>caf\xe9</p></body></html>")
    result = HtmlExtractor().extract(p)
    assert result.text != ""
    assert "caf" in result.text  # at minimum the ASCII part must be present


# ---------------------------------------------------------------------------
# Bug 3: RTF encoding fallback
# ---------------------------------------------------------------------------


def test_rtf_extractor_latin1_file_not_empty(tmp_path: Path) -> None:
    """RTF with Windows-1252 extended bytes must not return empty."""
    p = tmp_path / "win1252.rtf"
    # Simple RTF with a Windows-1252 en-dash (0x96) in the text.
    rtf = (
        rb"{\rtf1\ansi\deff0 {\fonttbl {\f0 Courier;}}"
        rb"\f0\fs24 Hello\x96World}"
    )
    p.write_bytes(rtf)
    result = RtfExtractor().extract(p)
    # Must not be empty — at least the ASCII portions are preserved.
    assert result.text != ""
    assert "Hello" in result.text


# ---------------------------------------------------------------------------
# Bug 4 + 5: XML extractor strips tags and handles non-UTF-8 encoding
# ---------------------------------------------------------------------------


def test_xml_extractor_strips_tags(tmp_path: Path) -> None:
    """Extracted text must not contain XML markup."""
    p = tmp_path / "doc.xml"
    p.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<root><section><title>Hello XML</title><body>world</body></section></root>",
        encoding="utf-8",
    )
    result = XmlExtractor().extract(p)
    assert "Hello XML" in result.text
    assert "world" in result.text
    # Tags must be absent
    assert "<root>" not in result.text
    assert "<title>" not in result.text
    assert "<section>" not in result.text


def test_xml_extractor_handles_iso8859_encoding(tmp_path: Path) -> None:
    """XML with encoding="iso-8859-1" in the prolog must be extracted."""
    p = tmp_path / "latin.xml"
    content = '<?xml version="1.0" encoding="iso-8859-1"?><root><item>caf\xe9</item></root>'
    p.write_bytes(content.encode("iso-8859-1"))
    result = XmlExtractor().extract(p)
    assert result.text != ""
    assert "caf" in result.text


def test_xml_extractor_returns_empty_for_malformed(tmp_path: Path) -> None:
    p = tmp_path / "bad.xml"
    p.write_text("<unclosed>", encoding="utf-8")
    assert XmlExtractor().extract(p).text == ""


# ---------------------------------------------------------------------------
# Bug 6: DOCX merged table cell deduplication
# ---------------------------------------------------------------------------


def test_docx_merged_cells_not_duplicated(tmp_path: Path) -> None:
    """Merged cells must appear exactly once in extracted text."""
    from docx import Document

    doc = Document()
    table = doc.add_table(rows=1, cols=3)
    # Populate all three cells with distinct text first.
    table.cell(0, 0).text = "CellA"
    table.cell(0, 1).text = "CellB"
    table.cell(0, 2).text = "CellC"
    # Merge columns 0 and 1.
    merged = table.cell(0, 0).merge(table.cell(0, 1))
    merged.text = "MergedAB"

    p = tmp_path / "merged.docx"
    doc.save(str(p))

    result = DocxExtractor().extract(p)
    # "MergedAB" must appear exactly once.
    assert result.text.count("MergedAB") == 1
    # "CellC" must still be present.
    assert "CellC" in result.text


# ---------------------------------------------------------------------------
# Bug 7: MSG extractor file-handle leak (close() called)
# ---------------------------------------------------------------------------


def test_msg_extractor_closes_message_after_extract() -> None:
    """extract_msg.Message.close() must be called after extract()."""
    from services.extraction.msg_extractor import MsgExtractor

    mock_msg = MagicMock()
    mock_msg.subject = "Test"
    mock_msg.body = "body text"
    mock_msg.to = ""
    mock_msg.sender = ""
    mock_msg.date = None
    mock_msg.attachments = []

    with patch("services.extraction.msg_extractor.extract_msg.Message", return_value=mock_msg):
        MsgExtractor().extract(FIXTURES / "sample.msg")

    mock_msg.close.assert_called_once()


def test_msg_extractor_closes_message_on_exception() -> None:
    """close() must be called even when body extraction raises mid-way."""
    from unittest.mock import PropertyMock

    from services.extraction.msg_extractor import MsgExtractor

    mock_msg = MagicMock()
    mock_msg.subject = "Test"
    mock_msg.body = "body"
    mock_msg.sender = ""
    mock_msg.to = ""
    mock_msg.date = None
    # Iterating attachments raises — triggers the except path inside extract().
    type(mock_msg).attachments = PropertyMock(side_effect=RuntimeError("disk error"))

    with patch("services.extraction.msg_extractor.extract_msg.Message", return_value=mock_msg):
        result = MsgExtractor().extract(FIXTURES / "sample.msg")

    # Should not raise; extractor returns ExtractionResult(text="") on any exception.
    assert result.text == ""
    mock_msg.close.assert_called_once()


def test_msg_extractor_returns_attachments_via_extract() -> None:
    """Attachment bytes must be available via extract().attachments."""
    from services.extraction.msg_extractor import MsgExtractor

    mock_att = MagicMock()
    mock_att.longFilename = "report.pdf"
    mock_att.data = b"PDF content"
    mock_att.content_type = "application/pdf"

    mock_msg = MagicMock()
    mock_msg.subject = "Test"
    mock_msg.body = "body text"
    mock_msg.to = ""
    mock_msg.sender = ""
    mock_msg.date = None
    mock_msg.attachments = [mock_att]

    with patch("services.extraction.msg_extractor.extract_msg.Message", return_value=mock_msg):
        result = MsgExtractor().extract(FIXTURES / "sample.msg")

    assert len(result.attachments) == 1
    assert result.attachments[0].filename == "report.pdf"
    assert result.attachments[0].mime_type == "application/pdf"
    mock_msg.close.assert_called_once()


# ---------------------------------------------------------------------------
# Bug 8: XLSX workbook closed on exception
# ---------------------------------------------------------------------------


def test_xlsx_workbook_closed_on_exception(tmp_path: Path) -> None:
    """wb.close() must be called even when iteration raises."""
    from unittest.mock import MagicMock, patch

    mock_wb = MagicMock()
    # Simulate a crash while iterating worksheets.
    mock_wb.worksheets = MagicMock(side_effect=RuntimeError("disk error"))

    with patch("services.extraction.xlsx.load_workbook", return_value=mock_wb):
        p = tmp_path / "boom.xlsx"
        p.write_bytes(b"fake")
        result = XlsxExtractor().extract(p)

    assert result.text == ""
    mock_wb.close.assert_called_once()


# ---------------------------------------------------------------------------
# Bug 9 + 10: Registry alias/dead-entry cleanup
# ---------------------------------------------------------------------------


def test_registry_x_tar_has_extractor() -> None:
    """application/x-tar must still resolve to TarExtractor after alias cleanup."""
    registry = ExtractorRegistry()
    assert registry.get("application/x-tar") is not None


def test_registry_x_zip_compressed_resolves_via_alias() -> None:
    """application/x-zip-compressed must resolve to the same extractor as application/zip."""
    registry = ExtractorRegistry()
    assert registry.get("application/x-zip-compressed") is registry.get("application/zip")


# ---------------------------------------------------------------------------
# Bug 11: translation_worker empty content_text → graceful skip, not dead-letter
# ---------------------------------------------------------------------------


def test_translation_worker_empty_content_text_skips_gracefully() -> None:
    """A document with no extractable text must not be dead-lettered.

    The durable-queue translation_worker previously raised ValueError when
    content_text was empty, causing up to max_attempts retries and eventual
    dead-lettering for documents that genuinely have no text (scanned PDFs
    without OCR, empty files).  After the fix it returns True (job consumed)
    and enqueues the next stage.
    """
    from uuid import uuid4

    from services.pipeline.translation_worker import run_translation_once

    doc_id = uuid4()
    source_id = uuid4()
    job_id = uuid4()

    fake_job = {
        "id": job_id,
        "document_id": doc_id,
        "job_type": "translate_document",
        "attempts": 1,
        "max_attempts": 3,
        "source_id": source_id,
    }

    fake_doc = MagicMock()
    fake_doc.source_language = "en"

    job_repo = MagicMock()
    job_repo.claim_next.return_value = fake_job
    job_repo.get_payload.return_value = {"content_text": ""}  # empty!

    doc_repo = MagicMock()
    doc_repo.get_by_id.return_value = fake_doc

    translator = MagicMock()

    result = run_translation_once(job_repo, doc_repo, translator)

    assert result is True
    # Must NOT have called translate() on empty text
    translator.translate.assert_not_called()
    # Must have stored empty translated text
    job_repo.update_translated_text.assert_called_once_with(doc_id, "")
    # Must have succeeded (not retried / dead-lettered)
    job_repo.mark_succeeded.assert_called_once()
    job_repo.mark_retry.assert_not_called()
    job_repo.mark_dead_letter.assert_not_called()
    # Must have enqueued the index job so the pipeline continues
    job_repo.enqueue_document.assert_called_once()


# ---------------------------------------------------------------------------
# Bug 12: slow_worker run_enrich_loop logs wrong exception type
# ---------------------------------------------------------------------------


def test_slow_worker_enrich_loop_logs_actual_exception_type(tmp_path: Path) -> None:
    """run_enrich_loop must log the real exception class, not always 'type'."""

    from services.pipeline.slow_worker import run_enrich_loop

    call_count = 0

    def _boom_once(job_repo, worker, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("disk full")
        raise KeyboardInterrupt  # stop the loop cleanly

    with (
        patch("services.pipeline.slow_worker.run_enrich_once", side_effect=_boom_once),
        patch("services.pipeline.slow_worker.logger") as mock_logger,
        patch("time.sleep"),
        contextlib.suppress(KeyboardInterrupt),
    ):
        run_enrich_loop(MagicMock(), MagicMock())

    # Find the exception call; the error_type arg must be "RuntimeError"
    exception_calls = list(mock_logger.exception.call_args_list)
    assert exception_calls, "logger.exception was never called"
    # The second positional arg after the format string should be "RuntimeError"
    logged_error_type = exception_calls[0][0][2]  # format string, worker_id, error_type
    assert logged_error_type == "RuntimeError", (
        f"Expected 'RuntimeError' but got '{logged_error_type}'"
    )


# ---------------------------------------------------------------------------
# Bug 13: EPUB extractor misses multiline HTML tags
# ---------------------------------------------------------------------------


def test_epub_extractor_strips_multiline_tags(tmp_path: Path) -> None:
    """HTML tags spanning multiple lines must be fully removed, not left as fragments."""
    import sys
    import types

    multiline_html = b'<div\n  class="chapter"\n  id="ch1">\n<p>Hello EPUB multiline</p>\n</div>'

    mock_item = MagicMock()
    mock_item.get_content.return_value = multiline_html

    mock_book = MagicMock()
    mock_book.get_items_of_type.return_value = [mock_item]

    fake_ebooklib = types.ModuleType("ebooklib")
    fake_ebooklib.ITEM_DOCUMENT = 9  # type: ignore[attr-defined]
    fake_epub_mod = types.ModuleType("ebooklib.epub")
    fake_epub_mod.read_epub = MagicMock(return_value=mock_book)  # type: ignore[attr-defined]
    fake_ebooklib.epub = fake_epub_mod  # type: ignore[attr-defined]

    from services.extraction.epub import EpubExtractor

    with patch.dict(sys.modules, {"ebooklib": fake_ebooklib, "ebooklib.epub": fake_epub_mod}):
        result = EpubExtractor().extract(tmp_path / "dummy.epub")

    assert "Hello EPUB multiline" in result.text
    # No tag fragment should remain
    assert "<div" not in result.text
    assert 'class="chapter"' not in result.text
    assert "id=" not in result.text


# ---------------------------------------------------------------------------
# Bug 14: EML extractor always uses declared MIME type, ignores filename guess
# ---------------------------------------------------------------------------


def test_eml_extract_attachments_prefers_filename_mime_over_default(tmp_path: Path) -> None:
    """Attachment without explicit Content-Type should use filename-guessed MIME."""
    from services.extraction.eml import EmlExtractor

    # Simulate using the extractor with a patched email parse result
    eml_path = tmp_path / "test.eml"

    with patch("services.extraction.eml.email.message_from_bytes") as mock_parse:
        mock_msg = MagicMock()
        mock_att = MagicMock()
        mock_att.is_multipart.return_value = False
        mock_att.get_filename.return_value = "report.pdf"
        mock_att.get_content_disposition.return_value = "attachment"
        mock_att.get_payload.return_value = b"PDF bytes"
        mock_att.get_content_type.return_value = "text/plain"  # default (no explicit header)
        # Simulate no Content-Type header present
        mock_att.__contains__ = MagicMock(side_effect=lambda key: key != "Content-Type")

        mock_msg.walk.return_value = [mock_att]
        mock_parse.return_value = mock_msg

        eml_path.write_bytes(b"dummy")
        result = EmlExtractor().extract(eml_path)

    attachments = result.attachments
    assert len(attachments) == 1
    # Must use filename-guessed type, not the default "text/plain"
    assert attachments[0].mime_type == "application/pdf"


# ---------------------------------------------------------------------------
# Bug 15: TranslateConsumer hardcodes target_lang="en", ignores doc.target_language
# ---------------------------------------------------------------------------


def test_translate_consumer_uses_doc_target_language() -> None:
    """TranslateConsumer must pass doc.target_language to the translator, not hardcode 'en'.

    Previously all three translation calls used the string literal "en":
      - translator.translate(..., target_lang="en")
      - version_repo.find_pending_or_running(document_id, "en")
      - version_repo.create_version(..., target_language="en")

    After the fix each uses (doc.target_language or "en") so that documents
    configured for French, Spanish, etc. are actually translated to those
    languages and their version records are tagged correctly.
    """
    from uuid import uuid4

    from services.pipeline.translate_worker import TranslateConsumer

    document_id = uuid4()
    source_id = uuid4()
    job_id = uuid4()

    mock_doc = MagicMock()
    mock_doc.source_language = "fr"
    mock_doc.target_language = "de"  # German — must NOT be overridden to "en"

    mock_doc_repo = MagicMock()
    mock_doc_repo.get_by_id.return_value = mock_doc

    mock_translator = MagicMock()
    mock_translator.translate.return_value = "Übersetzter Text"

    mock_version_repo = MagicMock()
    mock_version_repo.find_pending_or_running.return_value = None  # create new version

    mock_job_repo = MagicMock()
    mock_publisher = MagicMock()

    consumer = TranslateConsumer(
        rabbit=MagicMock(),
        job_repo=mock_job_repo,
        publisher=mock_publisher,
        translator=mock_translator,
        version_repo=mock_version_repo,
        doc_repo=mock_doc_repo,
    )

    consumer.handle_message(
        job_id=job_id,
        document_id=document_id,
        source_id=source_id,
        attempt=1,
        correlation_id="test-corr",
        content_text="Bonjour le monde",
    )

    # Translator must have been called with target_lang="de", not "en"
    mock_translator.translate.assert_called_once()
    call_kwargs = mock_translator.translate.call_args
    assert call_kwargs.kwargs.get("target_lang") == "de", (
        f"Expected target_lang='de' but got {call_kwargs.kwargs.get('target_lang')!r}"
    )

    # Version lookup and creation must use "de", not "en"
    mock_version_repo.find_pending_or_running.assert_called_with(document_id, "de")
    create_call = mock_version_repo.create_version.call_args
    assert create_call.kwargs.get("target_language") == "de", (
        f"Expected target_language='de' but got {create_call.kwargs.get('target_language')!r}"
    )


def test_translate_consumer_defaults_target_lang_to_en_when_doc_missing() -> None:
    """When doc_repo is None or doc is not found, target_lang must default to 'en'."""
    from uuid import uuid4

    from services.pipeline.translate_worker import TranslateConsumer

    document_id = uuid4()
    source_id = uuid4()
    job_id = uuid4()

    mock_translator = MagicMock()
    mock_translator.translate.return_value = "Hello world"

    mock_version_repo = MagicMock()
    mock_version_repo.find_pending_or_running.return_value = None

    mock_job_repo = MagicMock()
    mock_publisher = MagicMock()

    # No doc_repo provided — doc will be None
    consumer = TranslateConsumer(
        rabbit=MagicMock(),
        job_repo=mock_job_repo,
        publisher=mock_publisher,
        translator=mock_translator,
        version_repo=mock_version_repo,
        doc_repo=None,
    )

    consumer.handle_message(
        job_id=job_id,
        document_id=document_id,
        source_id=source_id,
        attempt=1,
        correlation_id="test-corr",
        content_text="Bonjour",
    )

    # Must fall back to "en"
    call_kwargs = mock_translator.translate.call_args
    assert call_kwargs.kwargs.get("target_lang") == "en"
    mock_version_repo.find_pending_or_running.assert_called_with(document_id, "en")
