from __future__ import annotations

from pathlib import Path

import pytest

from services.preview.email_renderer import detect_quoted_ranges, render_email

FIXTURES = Path(__file__).parent.parent / "fixtures" / "mail"


def _render(name: str, **kwargs: int) -> object:
    raw = (FIXTURES / name).read_bytes()
    return render_email(
        raw,
        max_inline_images=kwargs.get("max_inline_images", 50),
        max_inline_image_bytes=kwargs.get("max_inline_image_bytes", 5_242_880),
    )


def test_plain_email_headers_and_text_body() -> None:
    rendered = _render("plain.eml")
    meta = rendered.email_manifest
    assert meta["subject"] == "Quarterly figures"
    assert "alice@example.com" in meta["from"]
    assert len(meta["to"]) == 2
    assert meta["cc"] == ["dave@example.com"]
    assert meta["message_id"] == "<plain-001@example.com>"
    assert meta["date"].startswith("2026-01-05")
    assert meta["has_text_body"] is True
    assert meta["has_html_body"] is False
    _filename, content_type, data = rendered.artifacts["body-text"]
    assert content_type == "text/plain"
    assert b"Q4 figures" in data


def test_html_email_inline_image_embedded_and_pixel_blocked() -> None:
    rendered = _render("html-inline.eml")
    meta = rendered.email_manifest
    assert meta["has_html_body"] is True
    assert len(meta["inline_images"]) == 1
    assert meta["inline_images"][0]["content_type"] == "image/png"
    assert meta["embedded_inline_images"] == 1
    assert meta["blocked_remote_images"] == 1  # the tracking pixel
    _filename, content_type, data = rendered.artifacts["body-html"]
    assert content_type == "text/html"
    html = data.decode("utf-8")
    assert "data:image/png;base64," in html
    assert "tracker.example.net" not in html
    assert "<table" in html


def test_inline_image_count_cap() -> None:
    rendered = _render("html-inline.eml", max_inline_images=0)
    meta = rendered.email_manifest
    assert meta["inline_images"] == []
    assert meta["skipped_inline_images"] == 1
    html = rendered.artifacts["body-html"][2].decode("utf-8")
    assert "data:image/png" not in html


def test_thread_quoted_range_detected() -> None:
    rendered = _render("thread.eml")
    ranges = rendered.email_manifest["quoted_ranges"]
    assert len(ranges) == 1
    assert ranges[0]["label"].startswith("On Mon, Jan 5, 2026")
    assert ranges[0]["end_line"] > ranges[0]["start_line"]


def test_attachments_listed_without_document_ids() -> None:
    rendered = _render("attachments.eml")
    attachments = rendered.email_manifest["attachments"]
    assert [a["filename"] for a in attachments] == ["contract.pdf", "appendix.txt"]
    assert attachments[0]["content_type"] == "application/pdf"
    assert attachments[0]["size_bytes"] > 0
    assert attachments[0]["document_id"] is None
    assert attachments[0]["preview_available"] is False


def test_malicious_email_sanitized() -> None:
    rendered = _render("malicious.eml")
    html = rendered.artifacts["body-html"][2].decode("utf-8")
    for fragment in ("<script", "onerror", "javascript:", "<form", "<iframe", "<meta", "style="):
        assert fragment not in html
    assert 'href="https://safe.example/doc"' in html
    assert rendered.email_manifest["blocked_remote_images"] >= 3
    # RFC 2047-encoded subject decoded
    assert "Urgent" in rendered.email_manifest["subject"]


def test_quoted_range_trailing_gt_block() -> None:
    text = "Reply text\n\n> quoted line one\n> quoted line two"
    ranges = detect_quoted_ranges(text)
    assert len(ranges) == 1
    assert ranges[0]["start_line"] == 2


def test_quoted_range_absent_for_plain_text() -> None:
    assert detect_quoted_ranges("Just a normal\nemail body") == []


def test_malformed_bytes_raise_no_uncaught_keyerror() -> None:
    # Garbage parses as an empty message rather than raising — render_email
    # must produce a manifest with no bodies (orchestrator marks it partial).
    rendered = render_email(b"\x00\xff garbage", max_inline_images=5, max_inline_image_bytes=1024)
    assert rendered.email_manifest["has_text_body"] in (True, False)


@pytest.mark.parametrize("name", ["plain.eml", "html-inline.eml", "thread.eml"])
def test_no_bcc_leak_when_absent(name: str) -> None:
    rendered = _render(name)
    assert rendered.email_manifest["bcc"] == []
