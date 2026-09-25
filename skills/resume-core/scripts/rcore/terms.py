"""Terms check: no denylisted term from decisions/terms.json appears in output text.

Matching is strict. Terms and scanned text are both normalized (NFKC, zero-width
characters removed, casefolded). A term's words may be separated by any run of
whitespace, hyphens or underscores, or by nothing, and a trailing "s" or "es"
still matches. A match must not have a letter, digit or underscore on either side.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from . import schema, wsio

TERMS_FILE = "decisions/terms.json"
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"))
_SEPARATOR = r"[\s\-_]"


def normalize(text: str) -> str:
    """NFKC, then remove zero-width characters, then casefold."""
    return unicodedata.normalize("NFKC", text).translate(_ZERO_WIDTH).casefold()


def _read_denylist(workspace: Path) -> tuple[list[str], list[str]]:
    if not (Path(workspace) / TERMS_FILE).is_file():
        return [], [f"{TERMS_FILE}: not found; run init_workspace.py"]
    data, error = wsio.load(workspace, TERMS_FILE)
    if error:
        return [], [error]
    problems = schema.validate(data, schema.load_schema("terms"))
    if problems:
        return [], [f"{TERMS_FILE}: {p}" for p in problems]
    return [t["term"] for t in data if t["replacement"] is not None], []


def load_denylist(workspace: Path) -> list[str]:
    """Terms with a replacement are denied; terms with replacement null are allowed.

    Fails closed: raises ValueError if decisions/terms.json is missing or invalid.
    """
    denied, errors = _read_denylist(workspace)
    if errors:
        raise ValueError("\n".join(errors))
    return denied


def load_patterns(workspace: Path) -> tuple[list[tuple[str, re.Pattern]], list[str]]:
    """Return (compiled patterns, errors). Errors are non-empty when terms.json is unusable."""
    denied, errors = _read_denylist(workspace)
    return compile_terms(denied), errors


def _term_regex(term: str) -> str:
    normalized = normalize(term)
    words = [w for w in re.split(_SEPARATOR + "+", normalized) if w]
    body = (_SEPARATOR + "*").join(map(re.escape, words)) if words else re.escape(normalized)
    return r"(?<!\w)" + body + r"(?:s|es)?(?!\w)"


def compile_terms(terms: list[str]) -> list[tuple[str, re.Pattern]]:
    """Patterns that match normalized text (see the module docstring for the rules)."""
    return [(term, re.compile(_term_regex(term))) for term in terms]


def scan_json(doc, patterns, label: str) -> list[str]:
    errors = []
    for pointer, text in wsio.iter_strings(doc):
        normalized = normalize(text)
        for term, pattern in patterns:
            if pattern.search(normalized):
                errors.append(f"{label}:{pointer or '/'}: contains denylisted term {term!r}")
    return errors


def scan_text(text: str, patterns, label: str) -> list[str]:
    """Scan the whole text at once, so a term broken across lines is still found.

    Reports the 1-based line where each match starts.
    """
    normalized = normalize(text)
    hits = set()
    for index, (term, pattern) in enumerate(patterns):
        for match in pattern.finditer(normalized):
            hits.add((normalized.count("\n", 0, match.start()) + 1, index, term))
    return [f"{label}:{line}: contains denylisted term {term!r}" for line, _, term in sorted(hits)]


def check_file(workspace: Path, rel: str, patterns=None) -> list[str]:
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
