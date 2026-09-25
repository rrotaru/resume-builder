"""Terms check: no denylisted term from decisions/terms.json appears in output text.

Matching is strict. Terms and scanned text are both normalized (NFKC, invisible
format characters removed, casefolded). A term's words may be separated by any
run of separator characters (whitespace, underscore, dashes, minus, full stop,
slash, middle dot), or by nothing. A trailing "s" or "es" still matches for
terms of 5 or more characters. A match must not have a letter, digit or
underscore on either side.

Allowed terms (replacement null) are matched literally: normalized, whole-word,
with no separator flexibility and no plural. A denied match lying entirely
inside an allowed match is not reported.
"""
from __future__ import annotations

import bisect
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from . import schema, wsio

TERMS_FILE = "decisions/terms.json"
_GRAPHEME_JOINER = "\u034f"
# Whitespace, underscore, every dash (category Pd), minus sign, full stop, slash, middle dot.
_DASHES = "".join(
    chr(c) for c in range(sys.maxunicode + 1) if unicodedata.category(chr(c)) == "Pd"
)
_SEPARATOR = "[\\s" + re.escape("_" + _DASHES + "\u2212./\u00b7") + "]"
_PLURAL_MIN_LENGTH = 5


def _strip_invisible(text: str) -> str:
    return "".join(
        c for c in text if c != _GRAPHEME_JOINER and unicodedata.category(c) != "Cf"
    )


def normalize(text: str) -> str:
    """NFKC, remove format characters (category Cf) and U+034F, then casefold."""
    return _strip_invisible(unicodedata.normalize("NFKC", _strip_invisible(text))).casefold()


@dataclass
class Patterns:
    """Compiled denied terms, each (term, pattern), and allowed-term patterns."""
    denied: list[tuple[str, re.Pattern]] = field(default_factory=list)
    allowed: list[re.Pattern] = field(default_factory=list)


def _read_terms(workspace: Path) -> tuple[list[str], list[str], list[str]]:
    """Return (denied, allowed, errors)."""
    if not (Path(workspace) / TERMS_FILE).is_file():
        return [], [], [f"{TERMS_FILE}: not found; run init_workspace.py"]
    data, error = wsio.load(workspace, TERMS_FILE)
    if error:
        return [], [], [error]
    problems = schema.validate(data, schema.load_schema("terms"))
    if problems:
        return [], [], [f"{TERMS_FILE}: {p}" for p in problems]
    denied = [t["term"] for t in data if t["replacement"] is not None]
    allowed = [t["term"] for t in data if t["replacement"] is None]
    return denied, allowed, []


def load_denylist(workspace: Path) -> list[str]:
    """Terms with a replacement are denied; terms with replacement null are allowed.

    Fails closed: raises ValueError if decisions/terms.json is missing or invalid.
    """
    denied, _, errors = _read_terms(workspace)
    if errors:
        raise ValueError("\n".join(errors))
    return denied


def load_patterns(workspace: Path) -> tuple[Patterns, list[str]]:
    """Return (compiled patterns, errors). Errors are non-empty when terms.json is unusable."""
    denied, allowed, errors = _read_terms(workspace)
    return compile_terms(denied, allowed), errors


def _term_regex(term: str) -> str:
    normalized = normalize(term)
    words = [w for w in re.split(_SEPARATOR + "+", normalized) if w]
    body = (_SEPARATOR + "*").join(map(re.escape, words)) if words else re.escape(normalized)
    plural = r"(?:s|es)?" if sum(map(len, words)) >= _PLURAL_MIN_LENGTH else ""
    return body + plural


def _all_matches(pattern: re.Pattern, text: str) -> list[tuple[int, int]]:
    """Spans of the whole-word match at every start position, overlapping ones included."""
    return [m.span(1) for m in pattern.finditer(text)]


def _whole_word(body: str) -> re.Pattern:
    # The lookahead finds a match at every start, so overlapping matches are not skipped.
    return re.compile(r"(?<!\w)(?=(" + body + r")(?!\w))")


def compile_terms(terms: list[str], allowed: list[str] | tuple = ()) -> Patterns:
    """Patterns that match normalized text (see the module docstring for the rules)."""
    return Patterns(
        denied=[(term, _whole_word(_term_regex(term))) for term in terms],
        allowed=[_whole_word(re.escape(normalize(term))) for term in allowed if normalize(term)],
    )


def _reported_starts(normalized: str, patterns: Patterns) -> list[tuple[int, int, str]]:
    """(start, term index, term) of each denied match not inside an allowed match."""
    allowed = [span for p in patterns.allowed for span in _all_matches(p, normalized)]
    hits = []
    for index, (term, pattern) in enumerate(patterns.denied):
        for start, end in _all_matches(pattern, normalized):
            if not any(a <= start and end <= b for a, b in allowed):
                hits.append((start, index, term))
    return hits


def scan_json(doc, patterns: Patterns, label: str) -> list[str]:
    errors = []
    for pointer, text in wsio.iter_strings(doc):
        found = sorted({(index, term) for _, index, term in _reported_starts(normalize(text), patterns)})
        errors += [f"{label}:{pointer or '/'}: contains denylisted term {term!r}" for _, term in found]
    return errors


def _line_starts(text: str) -> list[int]:
    """Offsets where each line begins, using the same boundaries as str.splitlines()."""
    starts, offset = [0], 0
    for line in text.splitlines(keepends=True):
        offset += len(line)
        starts.append(offset)
    return starts


def scan_text(text: str, patterns: Patterns, label: str) -> list[str]:
    """Scan the whole text at once, so a term broken across lines is still found.

    Reports the 1-based line where each match starts.
    """
    normalized = normalize(text)
    starts = _line_starts(normalized)
    hits = {
        (bisect.bisect_right(starts, start), index, term)
        for start, index, term in _reported_starts(normalized, patterns)
    }
    return [f"{label}:{line}: contains denylisted term {term!r}" for line, _, term in sorted(hits)]


def check_file(workspace: Path, rel: str, patterns: Patterns | None = None) -> list[str]:
    """Scan a .json, .jsonl or text file for denylisted terms."""
    workspace = Path(workspace)
    if patterns is None:
        patterns, errors = load_patterns(workspace)
        if errors:
            return errors
    suffix = Path(rel).suffix
    fmt = {".json": "json", ".jsonl": "jsonl"}.get(suffix, "text")
    data, error = wsio.load(workspace, rel, fmt)
    if error:
        return [error]
    if fmt == "text":
        return scan_text(data, patterns, rel)
    return scan_json(data, patterns, rel)
