"""Load a JSON Resume file into a profile, exactly and repeatably.

- The file must hold a JSON object (UTF-8, BOM allowed).
- Top-level "$schema" and "meta" are dropped: they describe the file, not the engineer.
- Keys starting with "x-" are dropped at any depth, so a file cannot bring its
  own x-lines or x-highlights.
- Values that are "" or null are dropped (templates use them for "no value").
- Dates (startDate, endDate, date, releaseDate) must be YYYY, YYYY-MM or
  YYYY-MM-DD naming a real date. A timestamp is cut to its date. Anything else
  is an error: a date is never dropped, because a job without its endDate
  would render as current.
- Order, other sections and unknown fields are kept. The result must match
  resume.schema.json.
"""
from __future__ import annotations

import json
import re

from rcore import schema

from .dates import is_iso_date

DATE_KEYS = frozenset({"startDate", "endDate", "date", "releaseDate"})
DROPPED_TOP_LEVEL = ("$schema", "meta")
_TIMESTAMP = re.compile(r"(\d{4}-\d{2}-\d{2})T.*")


def _escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


class _Loader:
    def __init__(self):
        self.notes: list[str] = []
        self.errors: list[str] = []
        self.empty = 0

    def date(self, value, pointer: str):
        if isinstance(value, str):
            timestamp = _TIMESTAMP.fullmatch(value)
            if timestamp and is_iso_date(timestamp.group(1)):
                return timestamp.group(1)
            if is_iso_date(value):
                return value
        self.errors.append(f"{pointer}: date {value!r} is not YYYY, YYYY-MM or YYYY-MM-DD; fix it in the file")
        return value

    def clean(self, value, pointer: str = ""):
        if isinstance(value, dict):
            out = {}
            for key, child in value.items():
                child_pointer = f"{pointer}/{_escape(key)}"
                if (pointer == "" and key in DROPPED_TOP_LEVEL) or key.startswith("x-"):
                    self.notes.append(f"dropped {child_pointer}")
                elif child is None or child == "":
                    self.empty += 1
                elif key in DATE_KEYS:
                    out[key] = self.date(child, child_pointer)
                else:
                    out[key] = self.clean(child, child_pointer)
            return out
        if isinstance(value, list):
            out = []
            for i, child in enumerate(value):
                if child is None or child == "":
                    self.empty += 1
                else:
                    out.append(self.clean(child, f"{pointer}/{i}"))
            return out
        return value


def load(data: bytes) -> tuple[dict | None, list[str], list[str]]:
    """Map a JSON Resume file's bytes to a profile. Returns (profile, notes, errors).

    profile is None when there are errors.
    """
    try:
        document = json.loads(data.decode("utf-8-sig"))
    except UnicodeDecodeError:
        return None, [], ["not UTF-8 text; save it as UTF-8"]
    except json.JSONDecodeError as exc:
        return None, [], [f"invalid JSON: {exc}"]
    if not isinstance(document, dict):
        return None, [], ["a JSON Resume file must hold a JSON object"]
    loader = _Loader()
    profile = loader.clean(document)
    if loader.empty:
        loader.notes.append(f"dropped {loader.empty} empty value{'s' if loader.empty != 1 else ''}")
    if loader.errors:
        return None, loader.notes, loader.errors
    errors = schema.validate(profile, schema.load_schema("resume"))
    if errors:
        return None, loader.notes, errors
    return profile, loader.notes, []
