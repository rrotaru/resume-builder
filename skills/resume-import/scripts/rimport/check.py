"""Faithfulness check: the imported profile says only what the resume says.

For a text import (PDF, DOCX, TXT, Markdown), 03-profile/profile.json is the
model's reading of 03-profile/resume.txt:

- resume.txt must still hash to source.json text_sha256.
- The top level holds only basics and JSON Resume sections; each object holds
  only JSON Resume fields for its section; every value is a non-empty string
  (arrays such as highlights and keywords hold strings).
- Every entry of a section carries x-lines {first, last} inside resume.txt,
  and within a section first never decreases, so entries keep the text's order.
- Every value appears in its scope (match.py): an entry's lines for entry
  values, the whole text for basics and for URLs. Dates must be real and
  stated in the scope at that precision or finer (dates.py), and startDate is
  not after endDate.
- A work, volunteer, education or projects entry with a startDate and no
  endDate renders as ongoing, so its lines must say so (present, current, ...).

For a JSON Resume import, the profile must equal jsonresume.load() of the
source file, and the file must still hash to source.json sha256.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from rcore import validation, wsio
from rcore.profile import ARRAY_FIELDS, BASICS, DATE_FIELDS, LOCATION, PROFILE_ITEM, SECTIONS

from . import jsonresume
from .dates import finest, is_iso_date, stated_dates
from .match import appears, normalize

URL_FIELDS = frozenset({"url", "image"})
OPEN_SECTIONS = frozenset({"work", "volunteer", "education", "projects"})
ONGOING = re.compile(r"(?<![^\W_])(?:present|current|currently|now|today|ongoing|to\s+date|since)(?![^\W_])")
LINES = "x-lines"
FIX = ("fix: copy each value exactly as resume.txt writes it (only letter case may change), "
       "or leave it out for the wizard to ask. Never edit resume.txt.")


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def _short(value: str) -> str:
    return repr(value if len(value) <= 60 else value[:57] + "...")


def _kind(field: str) -> str:
    if field in URL_FIELDS:
        return "url"
    return "phone" if field == "phone" else "text"


class _TextCheck:
    def __init__(self, text: str, label: str):
        self.lines = text.splitlines()
        self.whole = normalize(text)
        self.label = label
        self.problems: list[str] = []

    def problem(self, pointer: str, message: str) -> None:
        self.problems.append(f"{self.label}: {pointer}: {message}")

    def scope(self, lines: tuple[int, int] | None) -> tuple[str, str]:
        """(normalized text, description) for an entry's lines, or the whole text."""
        if lines is None:
            return self.whole, "resume.txt"
        first, last = lines
        return normalize("\n".join(self.lines[first - 1:last])), f"resume.txt lines {first}-{last}"

    # Structure -------------------------------------------------------------

    def fields(self, obj: dict, allowed: tuple[str, ...], pointer: str, what: str) -> None:
        for key in obj:
            if key not in allowed:
                self.problem(f"{pointer}/{_escape(key)}", f"not a {what} field (allowed: {', '.join(allowed)})")

    def string(self, value, pointer: str) -> bool:
        if value is None:
            self.problem(pointer, "is null; leave the field out instead")
        elif not isinstance(value, str):
            self.problem(pointer, f"must be a string, not {type(value).__name__}")
        elif not value.strip():
            self.problem(pointer, "is empty; leave the field out instead")
        else:
            return True
        return False

    def values(self, field: str, value, pointer: str):
        """Yield (pointer, string) for a field's value, reporting values of the wrong type."""
        if field in ARRAY_FIELDS:
            if not isinstance(value, list):
                self.problem(pointer, "must be an array of strings")
                return
            for i, item in enumerate(value):
                if self.string(item, f"{pointer}/{i}"):
                    yield f"{pointer}/{i}", item
        elif self.string(value, pointer):
            yield pointer, value

    # Values ------------------------------------------------------------------

    def value(self, field: str, value: str, pointer: str, lines: tuple[int, int] | None) -> None:
        if field in DATE_FIELDS:
            self.date(value, pointer, lines)
            return
        text, where = self.scope(None if field in URL_FIELDS else lines)
        if not appears(value, text, _kind(field)):
            self.problem(pointer, f"{_short(value)} is not in {where}")

    def date(self, value: str, pointer: str, lines: tuple[int, int] | None) -> None:
        if not is_iso_date(value):
            self.problem(pointer, f"{_short(value)} is not a real date written YYYY, YYYY-MM or YYYY-MM-DD")
            return
        text, where = self.scope(lines)
        stated = stated_dates(text)
        if value not in stated:
            given = ", ".join(finest(stated)) or "none"
            self.problem(pointer, f"{_short(value)} is not a date {where} give (they give {given})")

    def obj(self, obj: dict, allowed: tuple[str, ...], pointer: str, what: str,
            lines: tuple[int, int] | None) -> None:
        self.fields(obj, allowed, pointer, what)
        for field, value in obj.items():
            if field in allowed:
                for child, text in self.values(field, value, f"{pointer}/{_escape(field)}"):
                    self.value(field, text, child, lines)

    # Sections ----------------------------------------------------------------

    def basics(self, basics) -> None:
        if not isinstance(basics, dict):
            self.problem("/basics", "must be an object")
            return
        self.fields(basics, BASICS, "/basics", "basics")
        for field, value in basics.items():
            pointer = f"/basics/{field}"
            if field == "location":
                if isinstance(value, dict):
                    self.obj(value, LOCATION, pointer, "basics.location", None)
                else:
                    self.problem(pointer, "must be an object")
            elif field == "profiles":
                if not isinstance(value, list):
                    self.problem(pointer, "must be an array of objects")
                    continue
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        self.obj(item, PROFILE_ITEM, f"{pointer}/{i}", "basics.profiles", None)
                    else:
                        self.problem(f"{pointer}/{i}", "must be an object")
            elif field in BASICS:
                for child, text in self.values(field, value, pointer):
                    self.value(field, text, child, None)

    def entry_lines(self, entry: dict, pointer: str) -> tuple[int, int] | None:
        lines = entry.get(LINES)
        if lines is None:
            self.problem(pointer, "x-lines is missing; give the lines of resume.txt this entry was read from")
            return None
        first, last = lines["first"], lines["last"]
        if first > last:
            self.problem(pointer, f"x-lines {first}-{last} ends before it starts")
        elif last > len(self.lines):
            self.problem(pointer, f"x-lines {first}-{last} is outside resume.txt (lines 1-{len(self.lines)})")
        else:
            return first, last
        return None

    def section(self, name: str, entries: list) -> None:
        allowed = SECTIONS[name] + (LINES,)
        previous: tuple[int, tuple[int, int]] | None = None
        for i, entry in enumerate(entries):
            pointer = f"/{name}/{i}"
            lines = self.entry_lines(entry, pointer)
            if lines is not None:
                if previous is not None and lines[0] < previous[1][0]:
                    j, (first, last) = previous
                    self.problem(pointer, f"x-lines {lines[0]}-{lines[1]} come before /{name}/{j} "
                                          f"(lines {first}-{last}); keep entries in the order of resume.txt")
                previous = (i, lines)
            self.fields(entry, allowed, pointer, name)
            if lines is None:
                continue
            for field, value in entry.items():
                if field in SECTIONS[name]:
                    for child, text in self.values(field, value, f"{pointer}/{_escape(field)}"):
                        self.value(field, text, child, lines)
            self.span(name, entry, pointer, lines)

    def span(self, name: str, entry: dict, pointer: str, lines: tuple[int, int]) -> None:
        start, end = entry.get("startDate"), entry.get("endDate")
        if is_iso_date(start) and is_iso_date(end):
            common = min(len(start), len(end))
            if start[:common] > end[:common]:
                self.problem(pointer, f"startDate {start!r} is after endDate {end!r}")
        if name in OPEN_SECTIONS and "startDate" in entry and "endDate" not in entry:
            text, where = self.scope(lines)
            if not ONGOING.search(text):
                self.problem(pointer, f"no endDate, but {where} do not say it is ongoing "
                                      "(present, current, now, ...)")

    def run(self, profile: dict) -> list[str]:
        for key, value in profile.items():
            if key == "basics":
                self.basics(value)
            elif key in SECTIONS:
                self.section(key, value)
            else:
                self.problem(f"/{_escape(key)}", "not a JSON Resume section "
                                                 f"(allowed: basics, {', '.join(SECTIONS)})")
        return self.problems


def check_text(profile: dict, text: str, label: str) -> list[str]:
    """Problems with a schema-valid profile read from text (see the module docstring)."""
    return _TextCheck(text, label).run(profile)


def check_json(profile: dict, source: dict, label: str) -> list[str]:
    """A JSON Resume import must equal the loader's mapping of the unchanged source file."""
    path = Path(source["path"])
    try:
        data = path.read_bytes()
    except OSError as exc:
        return [f"{path}: cannot be read ({exc.strerror}); run extract_text.py again"]
    if sha256(data) != source["sha256"]:
        return [f"{path}: changed since extract_text.py ran; run it again"]
    mapped, _, errors = jsonresume.load(data)
    if errors:
        return [f"{path}: {error}" for error in errors]
    if json.dumps(mapped, sort_keys=True) != json.dumps(profile, sort_keys=True):
        return [f"{label}: differs from the JSON Resume mapping; do not edit it, run extract_text.py again"]
    return []


def check_stage(workspace: Path, stage_dir: str) -> tuple[list[str], bool]:
    """Check 03-profile.tmp/ or 03-profile/. Returns (problems, whether FIX applies)."""
    workspace = Path(workspace)
    folder = workspace / stage_dir
    if not folder.is_dir():
        return [f"{stage_dir}: not found; run extract_text.py first"], False
    errors = validation.validate_paths(workspace, [f"{stage_dir}/source.json", f"{stage_dir}/profile.json"])
    if errors:
        return errors, False
    source = wsio.read_json(folder / "source.json")
    profile = wsio.read_json(folder / "profile.json")
    label = f"{stage_dir}/profile.json"
    if source["format"] == "json":
        return check_json(profile, source, label), False
    text_path = folder / "resume.txt"
    if not text_path.is_file():
        return [f"{stage_dir}/resume.txt: not found; run extract_text.py again"], False
    data = text_path.read_bytes()
    if sha256(data) != source["text_sha256"]:
        return [f"{stage_dir}/resume.txt: changed after extraction; run extract_text.py again"], False
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [f"{stage_dir}/resume.txt: not UTF-8 text; run extract_text.py again"], False
    return check_text(profile, text, label), True


def describe_sections(profile: dict) -> str:
    """'basics, work 2, education 1' for a summary line."""
    parts = []
    for key, value in profile.items():
        parts.append(f"{key} {len(value)}" if isinstance(value, list) else key)
    return ", ".join(parts) or "nothing"
