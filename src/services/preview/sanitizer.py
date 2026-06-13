"""Allowlist HTML sanitizer for email/Office preview artifacts (nh3-backed).

The sanitized output is additionally served with a deny-all CSP and rendered
inside a sandboxed iframe; this module is the first of three containment
layers, not the only one.

Inline images referenced by ``cid:`` are rewritten to ``data:`` URIs supplied
by the caller (the email renderer re-encodes attachment bytes itself). API
auth is header-only Bearer, so artifact URLs embedded in HTML could never
authenticate from an ``<img>`` tag — embedding is the air-gap-safe path.
Every ``img src`` value not constructed here is dropped and counted, which
also neutralizes tracking pixels.
"""

from __future__ import annotations

from dataclasses import dataclass

import nh3

# Structural and text-level tags commonly found in email bodies. No forms,
# no frames, no media beyond <img>, no <style>.
_ALLOWED_TAGS = {
    "a",
    "abbr",
    "b",
    "blockquote",
    "br",
    "caption",
    "code",
    "dd",
    "div",
    "dl",
    "dt",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "q",
    "s",
    "small",
    "span",
    "strong",
    "sub",
    "sup",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
}

# Drop these tags together with their content (nh3's default `tags` strips
# the tag but keeps inner text, which would leak script/style bodies).
_CLEAN_CONTENT_TAGS = {"script", "style", "title", "svg", "math"}

# No style/class/id anywhere in v1 — structure over fidelity. The explicit
# "*" entry overrides nh3's generic-attribute default ({"title", "lang"}):
# without it, attribute values like title='"><script>…' survive (escaped,
# so inert, but outside the allowlist contract).
_ALLOWED_ATTRIBUTES = {
    "*": set(),
    "a": {"href"},
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan", "align", "valign"},
    "th": {"colspan", "rowspan", "align", "valign"},
    "table": {"border", "cellpadding", "cellspacing", "width", "align"},
}

# "cid" must pass nh3's URL-scheme gate so the attribute filter can see and
# rewrite it; "data" lets the rewritten URI survive. Hostile cid:/data: img
# values never survive because the filter drops every src it did not build.
_URL_SCHEMES = {"http", "https", "mailto", "cid", "data"}


@dataclass(frozen=True)
class SanitizedHtml:
    """Sanitizer output: safe HTML plus diagnostics for the manifest."""

    html: str
    blocked_remote_images: int
    embedded_inline_images: int


def sanitize_email_html(
    raw_html: str, cid_data_uris: dict[str, str] | None = None
) -> SanitizedHtml:
    """Sanitize an email HTML body for iframe rendering.

    ``cid_data_uris`` maps Content-ID values (without angle brackets) to
    ``data:`` URIs prepared by the caller. ``img src="cid:<id>"`` references
    are rewritten to those URIs; every other ``img src`` is removed.
    """
    cid_map = cid_data_uris or {}
    blocked = 0
    embedded = 0

    def _attribute_filter(tag: str, attribute: str, value: str) -> str | None:
        nonlocal blocked, embedded
        if tag == "img" and attribute == "src":
            if value.startswith("cid:"):
                data_uri = cid_map.get(value.removeprefix("cid:").strip("<>"))
                if data_uri is not None:
                    embedded += 1
                    return data_uri
            blocked += 1
            return None
        return value

    cleaned = nh3.clean(
        raw_html,
        tags=_ALLOWED_TAGS,
        clean_content_tags=_CLEAN_CONTENT_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        attribute_filter=_attribute_filter,
        url_schemes=_URL_SCHEMES,
    )
    return SanitizedHtml(
        html=cleaned,
        blocked_remote_images=blocked,
        embedded_inline_images=embedded,
    )
