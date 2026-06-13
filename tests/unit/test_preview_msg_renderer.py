from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from services.preview.msg_renderer import render_msg

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _fake_attachment(**kwargs: object) -> SimpleNamespace:
    base: dict[str, object] = {
        "longFilename": None,
        "filename": None,
        "shortFilename": None,
        "name": None,
        "data": None,
        "mimetype": None,
        "content_type": None,
        "mime_type": None,
        "cid": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _render_with(msg: SimpleNamespace, **caps: int):
    with patch("services.preview.msg_renderer.extract_msg.Message", return_value=msg):
        return render_msg(
            Path("/tmp/sample.msg"),
            max_inline_images=caps.get("max_inline_images", 50),
            max_inline_image_bytes=caps.get("max_inline_image_bytes", 5_242_880),
        )


def test_msg_html_body_sanitized_and_metadata() -> None:
    msg = SimpleNamespace(
        subject="Outlook subject",
        sender="alice@example.com",
        to="bob@example.com; carol@example.com",
        cc="dave@example.com",
        bcc="",
        date="2026-01-10T09:00:00",
        messageId="<msg-1@example.com>",
        inReplyTo=None,
        htmlBody=b"<p>Hello</p><script>alert(1)</script><img src='https://evil/p.gif'>",
        body="Hello plain",
        attachments=[],
        close=lambda: None,
    )
    rendered = _render_with(msg)
    meta = rendered.email_manifest
    assert meta["subject"] == "Outlook subject"
    assert meta["from"] == "alice@example.com"
    assert meta["to"] == ["bob@example.com", "carol@example.com"]
    assert meta["cc"] == ["dave@example.com"]
    assert meta["message_id"] == "<msg-1@example.com>"
    assert meta["has_html_body"] is True
    assert meta["blocked_remote_images"] == 1
    html = rendered.artifacts["body-html"][2].decode("utf-8")
    assert "<script" not in html
    assert "evil" not in html


def test_msg_rtf_only_body_falls_back_to_text() -> None:
    msg = SimpleNamespace(
        subject="RTF only",
        sender="alice@example.com",
        to="bob@example.com",
        cc="",
        bcc="",
        date=None,
        messageId=None,
        inReplyTo=None,
        htmlBody=None,
        html=None,
        body="Plain body fallback",
        attachments=[],
        close=lambda: None,
    )
    rendered = _render_with(msg)
    assert rendered.email_manifest["has_html_body"] is False
    assert rendered.email_manifest["has_text_body"] is True
    assert rendered.artifacts["body-text"][2] == b"Plain body fallback"


def test_msg_inline_image_embedded_regular_attachment_listed() -> None:
    inline = _fake_attachment(name="logo.png", data=PNG_BYTES, mimetype="image/png", cid="logo@1")
    regular = _fake_attachment(
        longFilename="contract.pdf", data=b"%PDF-fake", mimetype="application/pdf"
    )
    msg = SimpleNamespace(
        subject="With attachments",
        sender="a@example.com",
        to="b@example.com",
        cc="",
        bcc="",
        date=None,
        messageId=None,
        inReplyTo=None,
        htmlBody=b"<p>See <img src='cid:logo@1'></p>",
        body="see attached",
        attachments=[inline, regular],
        close=lambda: None,
    )
    rendered = _render_with(msg)
    meta = rendered.email_manifest
    assert len(meta["inline_images"]) == 1
    assert meta["embedded_inline_images"] == 1
    # The inline image is not listed as a regular attachment.
    assert [a["filename"] for a in meta["attachments"]] == ["contract.pdf"]
    html = rendered.artifacts["body-html"][2].decode("utf-8")
    assert "data:image/png;base64," in html


def test_msg_inline_image_cap_skips_and_counts() -> None:
    inline = _fake_attachment(name="logo.png", data=PNG_BYTES, mimetype="image/png", cid="logo@1")
    msg = SimpleNamespace(
        subject="s",
        sender="a@example.com",
        to="b@example.com",
        cc="",
        bcc="",
        date=None,
        messageId=None,
        inReplyTo=None,
        htmlBody=b"<p><img src='cid:logo@1'></p>",
        body="b",
        attachments=[inline],
        close=lambda: None,
    )
    rendered = _render_with(msg, max_inline_images=0)
    assert rendered.email_manifest["inline_images"] == []
    assert rendered.email_manifest["skipped_inline_images"] == 1


def test_msg_message_closed_after_render() -> None:
    closed = {"value": False}

    def _close() -> None:
        closed["value"] = True

    msg = SimpleNamespace(
        subject="s",
        sender="a@example.com",
        to="",
        cc="",
        bcc="",
        date=None,
        messageId=None,
        inReplyTo=None,
        htmlBody=None,
        html=None,
        body="body",
        attachments=[],
        close=_close,
    )
    _render_with(msg)
    assert closed["value"] is True
