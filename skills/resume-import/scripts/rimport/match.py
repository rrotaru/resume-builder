"""Whether a profile value appears in a text.

Text and value are normalized the same way: Unicode NFKC, format characters
(category Cf) removed, dashes (category Pd and U+2212) read as "-", curly
quotes read as straight ones, and case folded. Then the value's characters,
with whitespace ignored, must occur in order in the text with nothing but
whitespace between them, starting and ending at a word boundary wherever the
value starts or ends with a letter or digit. So "Senior Software Engineer"
matches "Senior Software\\nEngineer", and "Go" does not match inside "Google".

URLs ignore their scheme, a leading "www." and a trailing "/". Phone numbers
compare their digits, separated in the text only by spaces, ( ) . - + or /.
"""
from __future__ import annotations

import re
import unicodedata

_SINGLE_QUOTES = "‘’‚‛′"
_DOUBLE_QUOTES = "“”„‟″"
# Not preceded / not followed by a letter or digit ([^\W_] is \w without "_").
_START = r"(?<![^\W_])"
_END = r"(?![^\W_])"
_URL_PREFIX = re.compile(r"^(?:https?://|mailto:)?(?:www\.)?")
_PHONE_SEPARATORS = r"[\s().+/-]*"


def normalize(text: str) -> str:
    out = []
    for char in unicodedata.normalize("NFKC", text):
        category = unicodedata.category(char)
        if category == "Cf":
            continue
        if category == "Pd" or char == "−":
            out.append("-")
        elif char in _SINGLE_QUOTES:
            out.append("'")
        elif char in _DOUBLE_QUOTES:
            out.append('"')
        else:
            out.append(char)
    return "".join(out).casefold()


def _text_pattern(value: str) -> str | None:
    chars = [c for c in value if not c.isspace()]
    if not chars:
        return None
    body = r"\s*".join(re.escape(c) for c in chars)
    return (_START if chars[0].isalnum() else "") + body + (_END if chars[-1].isalnum() else "")


def _phone_pattern(value: str) -> str | None:
    digits = re.findall(r"\d", value)
    if len(digits) < 3:
        return _text_pattern(value)
    return r"(?<!\d)" + _PHONE_SEPARATORS.join(digits) + r"(?!\d)"


def _url_value(value: str) -> str:
    return _URL_PREFIX.sub("", value).rstrip("/")


def appears(value: str, text: str, kind: str = "text") -> bool:
    """True if value appears in text. kind is "text", "url" or "phone".

    text must already be normalized (see normalize); value is normalized here.
    """
    value = normalize(value)
    if kind == "url":
        pattern = _text_pattern(_url_value(value))
    elif kind == "phone":
        pattern = _phone_pattern(value)
    else:
        pattern = _text_pattern(value)
    return pattern is not None and re.search(pattern, text) is not None
