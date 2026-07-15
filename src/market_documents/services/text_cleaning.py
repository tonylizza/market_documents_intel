"""Deterministic, conservative text cleaning.

Every function here is pure and order-sensitive; `clean_text` applies them
in a fixed sequence. This module performs only literal, near-lossless
normalization -- no summarization, stemming, or wording changes. Deciding
whether a whole block should be excluded from the narrative corpus (headers,
footers, page numbers, decorative fragments) is a classification concern,
handled by `block_classification` and `narrative_construction`, not here.
"""

import re
import unicodedata

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HYPHEN_LINEBREAK_RE = re.compile(r"([A-Za-z])-[ \t]*\n[ \t]*([A-Za-z])")
_MULTI_BLANK_LINE_RE = re.compile(r"\n{3,}")
_HORIZONTAL_WS_RE = re.compile(r"[ \t]+")
_WS_AROUND_NEWLINE_RE = re.compile(r"[ \t]*\n[ \t]*")

_PARAGRAPH_PLACEHOLDER = "\x00PARA\x00"


def normalize_unicode(text: str) -> str:
    """Apply NFKC Unicode normalization."""
    return unicodedata.normalize("NFKC", text)


def strip_control_characters(text: str) -> str:
    """Remove null bytes and control characters, preserving newlines and tabs."""
    return _CONTROL_CHAR_RE.sub("", text)


def repair_hyphenation(text: str) -> str:
    """Conservatively join words split across a line break by a hyphen.

    Joins when the character before the hyphen and the character
    immediately after the line break are both lowercase letters, e.g.
    "finan-\\ncial" -> "financial". Leaves the hyphen and line break
    untouched otherwise -- including when the letter after the break is
    uppercase (a proper-noun compound like "South-\\nAfrican") or when
    either side of the hyphen is non-alphabetic (a numeric range like
    "2023-\\n2024", or a symbol).
    """

    def _join(match: re.Match[str]) -> str:
        before, after = match.group(1), match.group(2)
        if before.islower() and after.islower():
            return before + after
        return match.group(0)

    return _HYPHEN_LINEBREAK_RE.sub(_join, text)


def join_wrapped_lines(text: str) -> str:
    """Join single line breaks (mid-paragraph wraps) into spaces.

    A run of two or more consecutive newlines is treated as an intentional
    paragraph break and collapsed to exactly one blank line. A single
    newline is treated as a line-wrap artifact of the PDF layout and
    replaced with a space.
    """
    text = _MULTI_BLANK_LINE_RE.sub(_PARAGRAPH_PLACEHOLDER, text)
    text = text.replace("\n\n", _PARAGRAPH_PLACEHOLDER)
    text = text.replace("\n", " ")
    text = text.replace(_PARAGRAPH_PLACEHOLDER, "\n\n")
    return text


def collapse_whitespace(text: str) -> str:
    """Collapse repeated horizontal whitespace and trim it around newlines."""
    text = _HORIZONTAL_WS_RE.sub(" ", text)
    text = _WS_AROUND_NEWLINE_RE.sub("\n", text)
    return text


def clean_text(text: str) -> str:
    """Run the full conservative cleaning pipeline in a fixed order."""
    text = normalize_unicode(text)
    text = strip_control_characters(text)
    text = repair_hyphenation(text)
    text = join_wrapped_lines(text)
    text = collapse_whitespace(text)
    return text.strip()
