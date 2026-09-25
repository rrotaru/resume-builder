"""Output check: every written file still holds the name, every heading and every
bullet, in order, and no denied term.

A missing text means the PDF text layer or the DOCX lost something an ATS
needs. The terms scan covers text the writers add themselves (headings, month
names, "Present") and anything a writer bug introduces.
"""
from __future__ import annotations

import re

from rcore import terms

from .model import Document

_SPACE = re.compile(r"\s+")


def _squash(text: str) -> str:
    """Drop all whitespace and case, so line wrapping in a PDF does not matter."""
    return _SPACE.sub("", text).casefold()


def missing(doc: Document, text: str) -> list[str]:
    """Checked texts of doc that do not appear in text, in reading order."""
    haystack, position, absent = _squash(text), 0, []
    for needle in doc.checked_texts():
        squashed = _squash(needle)
        found = haystack.find(squashed, position)
        if found < 0:
            absent.append(needle)
        else:
            position = found + len(squashed)
    return absent


def check(doc: Document, texts: dict[str, str], patterns: terms.Patterns) -> list[str]:
    """texts maps an output file's label to its extracted text."""
    problems = []
    for label, text in texts.items():
        problems += [f"{label}: missing {needle!r}" for needle in missing(doc, text)]
        problems += terms.scan_text(text, patterns, label)
    return problems
