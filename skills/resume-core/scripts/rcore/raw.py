"""The raw record at an evidence item's raw_ref, for the text it holds.

resume-collect keeps each fetched page as one line of 01-raw/<source>.jsonl,
and raw_ref points at an item's record: 01-raw/reviews.jsonl:1#/items/0. A
performance review's excerpt holds only its first 500 characters, so readers
that need the whole review (resume-sanitize's scan, resume-write's number
check) read the record's text here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import wsio

_RAW_REF = re.compile(r"^(01-raw/[^:]+):([1-9][0-9]*)#(/.*)$")


class RawReader:
    """Reads raw records at raw_ref (01-raw/<file>:<line>#/items/<i>), each file once."""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self.files: dict[str, list[str] | str] = {}

    def _lines(self, rel: str):
        if rel not in self.files:
            try:
                self.files[rel] = (self.workspace / rel).read_text(encoding="utf-8").split("\n")
            except FileNotFoundError:
                self.files[rel] = "not found"
            except (OSError, UnicodeDecodeError) as exc:
                self.files[rel] = f"cannot be read ({exc.__class__.__name__})"
        return self.files[rel]

    def text(self, raw_ref) -> tuple[str | None, str | None]:
        """(the record's text, None), or (None, why it could not be read)."""
        match = _RAW_REF.match(raw_ref) if isinstance(raw_ref, str) else None
        if match is None:
            return None, "is not a raw reference"
        lines = self._lines(match.group(1))
        if isinstance(lines, str):
            return None, f"{match.group(1)} {lines}"
        number = int(match.group(2))
        if number > len(lines) or not lines[number - 1].strip():
            return None, f"{match.group(1)} has no line {number}"
        try:
            record = wsio.resolve_pointer(json.loads(lines[number - 1]), match.group(3))
        except (ValueError, KeyError):
            return None, "does not resolve"
        text = record.get("text") if isinstance(record, dict) else None
        if not isinstance(text, str):
            return None, "has no text"
        return text, None
