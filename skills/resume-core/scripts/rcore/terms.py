"""Terms check: no denylisted term from decisions/terms.json appears in output text."""
from __future__ import annotations

import re
from pathlib import Path

from . import wsio


def load_denylist(workspace: Path) -> list[str]:
    """Terms with a replacement are denied; terms with replacement null are allowed."""
    path = Path(workspace) / "decisions" / "terms.json"
    if not path.is_file():
        return []
    return [t["term"] for t in wsio.read_json(path) if t["replacement"] is not None]


def compile_terms(terms: list[str]) -> list[tuple[str, re.Pattern]]:
    """Case-insensitive, whole-word patterns (no letter/digit/underscore on either side)."""
    return [
        (term, re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE))
        for term in terms
    ]


def scan_json(doc, patterns, label: str) -> list[str]:
    errors = []
    for pointer, text in wsio.iter_strings(doc):
        for term, pattern in patterns:
            if pattern.search(text):
                errors.append(f"{label}:{pointer or '/'}: contains denylisted term {term!r}")
    return errors


def scan_text(text: str, patterns, label: str) -> list[str]:
    errors = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for term, pattern in patterns:
            if pattern.search(line):
                errors.append(f"{label}:{lineno}: contains denylisted term {term!r}")
    return errors


def check_file(workspace: Path, rel: str, patterns=None) -> list[str]:
    """Scan a .json, .jsonl or text file for denylisted terms."""
    workspace = Path(workspace)
    patterns = compile_terms(load_denylist(workspace)) if patterns is None else patterns
    path = workspace / rel
    if path.suffix == ".json":
        return scan_json(wsio.read_json(path), patterns, rel)
    if path.suffix == ".jsonl":
        return scan_json(wsio.read_jsonl(path), patterns, rel)
    return scan_text(path.read_text(encoding="utf-8"), patterns, rel)
