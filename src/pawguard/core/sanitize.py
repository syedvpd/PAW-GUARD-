"""Server-side HTML sanitization for all user-supplied rich-text fields.

Every field that accepts free text from a non-admin user and may contain
HTML (grievance descriptions, CMS content, notification bodies, foster/volunteer
notes) MUST pass through sanitize_html() before persistence.

Uses nh3 (Rust-backed, actively maintained) to strip dangerous tags and
attributes including <script>, on* event handlers, and javascript: URLs.
"""

from __future__ import annotations

try:
    import nh3

    _NH3_AVAILABLE = True
except ImportError:  # pragma: no cover — production always has nh3
    _NH3_AVAILABLE = False

# Tags that are safe for user-authored rich text.
# Intentionally conservative: no <script>, <iframe>, <form>, <object>, <embed>.
_ALLOWED_TAGS: set[str] = {
    "a",
    "b",
    "blockquote",
    "br",
    "code",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "strong",
    "u",
    "ul",
}

# Per-tag attribute allow-list.  Anything not listed is stripped.
_ALLOWED_ATTRIBUTES: dict[str, set[str]] = {
    "a": {"href", "title"},
}


def sanitize_html(text: str | None) -> str | None:
    """Strip dangerous HTML from user-supplied rich-text content.

    Returns ``None`` unchanged when the input is ``None`` or empty.
    Falls back to plain-text stripping when nh3 is unavailable (tests only).
    """
    if not text:
        return text

    if _NH3_AVAILABLE:
        return nh3.clean(
            text,
            tags=_ALLOWED_TAGS,
            attributes=_ALLOWED_ATTRIBUTES,
            url_schemes={"https", "http", "mailto"},
            strip_comments=True,
        )

    # Fallback: naive tag stripper for environments without nh3.
    # This is intentionally not used in production — nh3 is a hard dependency.
    import re

    return re.sub(r"<[^>]+>", "", text)


def sanitize_plain(text: str | None) -> str | None:
    """Strip ALL HTML tags, returning plain text only.

    Use this for fields that accept plain text but should never store any HTML
    (e.g. names, short notes where rich formatting is not intended).
    """
    if not text:
        return text

    if _NH3_AVAILABLE:
        return nh3.clean(text, tags=set(), attributes={})

    import re

    return re.sub(r"<[^>]+>", "", text)
