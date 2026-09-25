"""Text of a resume file (PDF, DOCX, TXT, Markdown) and the formats import accepts.

The reader itself is rcore.documents, shared with resume-collect's review
ingest. This module adds the JSON Resume format and re-exports the rest.
"""
from __future__ import annotations

from pathlib import Path

from rcore.documents import (  # noqa: F401 - re-exported for extract_text.py and the tests
    LINKS_HEADER,
    ExtractError,
    Extracted,
    NoText,
    check_magic,
    decode_text,
    extract,
    normalize_lines,
)
from rcore.documents import FORMATS as TEXT_FORMATS

FORMATS = {**TEXT_FORMATS, ".json": "json"}
ACCEPTED = "PDF, DOCX, TXT, Markdown or JSON Resume (.json)"


def format_of(path: Path) -> str:
    fmt = FORMATS.get(Path(path).suffix.lower())
    if fmt is None:
        raise ExtractError(f"{path}: unsupported format {Path(path).suffix or '(no extension)'!r}; "
                           f"save it as {ACCEPTED}")
    return fmt
