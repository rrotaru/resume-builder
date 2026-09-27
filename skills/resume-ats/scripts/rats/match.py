"""How a keyword or a technical term is found in a text, for keyword coverage and the claim diff.

- Both are NFKC-normalized and format characters (category Cf) are removed.
- A keyword is split into words at runs of whitespace, "_", dashes, "/", "."
  and "·". In the text the words may be joined by any run of those, or by
  nothing: "Node.js" matches "NodeJS", "CI/CD" matches "CI CD".
- Whole words: no letter or digit before the match, and no letter, digit,
  "+" or "#" after it, so "C" is not found in "C++" or "C#", and "Go" is
  found in "Go-based".
- A keyword ending in a letter also matches with "s" or "es" added.
- Case is ignored, except in a keyword of at most three letters and digits
  that holds a capital letter ("Go", "AWS", "SLO", "US"), which must match
  its case, so "Go" is not found in "go live".
"""
from __future__ import annotations

import functools
import re
import sys
import unicodedata

_DASHES = "".join(chr(c) for c in range(sys.maxunicode + 1) if unicodedata.category(chr(c)) == "Pd")
_SEPARATOR = "[\\s" + re.escape("_" + _DASHES + "−/.·") + "]"
_SPLIT = re.compile(_SEPARATOR + "+")


def normalize(text: str) -> str:
    """NFKC, with format characters (category Cf, such as zero-width spaces) removed."""
    text = unicodedata.normalize("NFKC", text)
    return "".join(c for c in text if unicodedata.category(c) != "Cf")


def words(phrase: str) -> list[str]:
    return [w for w in _SPLIT.split(normalize(phrase)) if w]


def case_sensitive(phrase: str) -> bool:
    """True for a short capitalized keyword (Go, AWS, SLO), which must match its case."""
    alnum = [c for c in normalize(phrase) if c.isalnum()]
    return len(alnum) <= 3 and any(c.isupper() for c in alnum)


@functools.lru_cache(maxsize=4096)
def pattern(phrase: str) -> re.Pattern | None:
    """The compiled pattern for a keyword, or None when it has no word."""
    parts = words(phrase)
    if not parts:
        return None
    body = (_SEPARATOR + "*").join(re.escape(w) for w in parts)
    last = parts[-1][-1]
    if last.isalpha():
        body += "(?:s|es)?"
    after = r"(?![^\W_]|[+#])" if last.isalnum() else r"(?![^\W_])"
    flags = 0 if case_sensitive(phrase) else re.IGNORECASE
    return re.compile(r"(?<![^\W_])(?:" + body + ")" + after, flags)


def spans(text: str, phrase: str) -> list[tuple[int, int]]:
    """Where phrase is found in text, which must already be normalized."""
    compiled = pattern(phrase)
    return [m.span() for m in compiled.finditer(text)] if compiled else []


def mentions(text: str, phrase: str) -> bool:
    """True when phrase is found in text, which must already be normalized."""
    compiled = pattern(phrase)
    return compiled is not None and compiled.search(text) is not None


def key(phrase: str) -> str:
    """Two spellings the rule treats as the same keyword share a key."""
    joined = " ".join(words(phrase))
    return joined if case_sensitive(phrase) else joined.casefold()
