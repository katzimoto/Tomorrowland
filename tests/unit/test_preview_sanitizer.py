from __future__ import annotations

from services.preview.sanitizer import sanitize_email_html


def test_script_tags_removed_with_content() -> None:
    result = sanitize_email_html("<p>safe</p><script>alert('xss')</script>")
    assert "<script" not in result.html
    assert "alert" not in result.html
    assert "<p>safe</p>" in result.html


def test_event_handlers_stripped() -> None:
    result = sanitize_email_html('<img src="cid:x" onerror="alert(1)">')
    assert "onerror" not in result.html


def test_javascript_href_dropped() -> None:
    result = sanitize_email_html("<a href=\"javascript:alert('xss')\">click</a>")
    assert "javascript:" not in result.html
    assert "click" in result.html


def test_https_href_kept_with_rel() -> None:
    result = sanitize_email_html('<a href="https://safe.example/doc">link</a>')
    assert 'href="https://safe.example/doc"' in result.html
    assert "noopener" in result.html


def test_remote_image_blocked_and_counted() -> None:
    result = sanitize_email_html(
        '<img src="https://tracker.example/px.gif" width="1" height="1">'
        '<img src="https://tracker.example/px2.gif">'
    )
    assert "tracker.example" not in result.html
    assert result.blocked_remote_images == 2


def test_cid_image_rewritten_to_data_uri() -> None:
    result = sanitize_email_html(
        '<img src="cid:diagram@example.com" alt="d">',
        {"diagram@example.com": "data:image/png;base64,AAAA"},
    )
    assert 'src="data:image/png;base64,AAAA"' in result.html
    assert result.embedded_inline_images == 1
    assert result.blocked_remote_images == 0


def test_unknown_cid_dropped_and_counted_blocked() -> None:
    result = sanitize_email_html('<img src="cid:missing@example.com">', {})
    assert "cid:" not in result.html
    assert result.blocked_remote_images == 1


def test_hostile_data_uri_dropped() -> None:
    result = sanitize_email_html('<img src="data:text/html,<script>alert(1)</script>">')
    assert "data:" not in result.html
    assert result.blocked_remote_images == 1


def test_forms_iframes_meta_style_removed() -> None:
    result = sanitize_email_html(
        '<meta http-equiv="refresh" content="0;url=https://evil/">'
        '<style>body{background:url("https://evil/c.gif")}</style>'
        '<form action="https://evil/p"><input name="pw"></form>'
        '<iframe src="https://evil/f"></iframe>'
        "<p>content</p>"
    )
    for fragment in ("<meta", "<style", "<form", "<input", "<iframe", "evil"):
        assert fragment not in result.html
    assert "<p>content</p>" in result.html


def test_style_attribute_stripped() -> None:
    result = sanitize_email_html('<p style="background:url(https://evil/p.gif)">text</p>')
    assert "style=" not in result.html
    assert "text" in result.html


def test_attribute_breakout_vector_neutralized() -> None:
    # The #623 vector: attribute value containing a closing quote + script.
    result = sanitize_email_html('<img src="x" title=\'"><script>alert("breakout")</script>\'>')
    assert "<script" not in result.html
    assert "alert" not in result.html


def test_table_structure_preserved() -> None:
    result = sanitize_email_html(
        '<table border="1"><tr><th colspan="2">h</th></tr><tr><td>a</td><td>b</td></tr></table>'
    )
    assert "<table" in result.html
    assert 'colspan="2"' in result.html


def test_entity_encoded_script_stays_inert() -> None:
    result = sanitize_email_html("<p>&lt;script&gt;entity smuggle&lt;/script&gt;</p>")
    assert "<script" not in result.html
    assert "&lt;script&gt;" in result.html
