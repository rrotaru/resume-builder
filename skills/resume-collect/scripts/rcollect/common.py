"""Shared pieces: config and the data notice, raw pages, timestamps, text, the Draft record."""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rcore import schema, wsio

RAW, RAW_TMP = "01-raw", "01-raw.tmp"
EXCERPT_LENGTH = 500
MAX_REPORTED = 10

NOTICE = """\
Before anything is collected: resume-builder sends your work data to the AI model
provider that runs this assistant. That includes the titles, descriptions and
metadata of your pull requests, merge requests, code reviews, issues and tickets,
the messages of your commits in the local repositories you name, and the full
text of any performance reviews you provide. Your employer's policies may limit
where this data may go. Everything collected is also stored in the workspace
folder on this computer. Continue only if you may share this data."""

# Stronger roles win when two copies of one item merge.
ROLE_RANK = {"author": 0, "assignee": 1, "reviewer": 2, "reporter": 3, "subject": 4}


def plural(count: int, noun: str) -> str:
    """"1 item", "2 items"."""
    return f"{count} {noun}{'' if count == 1 else 's'}"


class CollectError(Exception):
    """A problem that stops a collect script (exit 1)."""


# Config ----------------------------------------------------------------------

def load_config(workspace: Path, need_notice: bool = True) -> dict:
    """Read and validate config.json. Raises CollectError, also when the notice is not accepted."""
    workspace = Path(workspace)
    if not (workspace / "config.json").is_file():
        raise CollectError(f"{workspace / 'config.json'} not found; run /resume-builder:init first")
    data, error = wsio.load(workspace, "config.json")
    if error:
        raise CollectError(error)
    errors = schema.validate(data, schema.load_schema("config"))
    if errors:
        raise CollectError("config.json is not valid: " + "; ".join(errors))
    if need_notice and not data.get("data_notice_acknowledged_at"):
        raise CollectError("the data notice has not been accepted: run configure.py notice, show it "
                           "to the engineer, and run configure.py notice --accept only if they agree")
    return data


def source_entry(cfg: dict, source: str) -> dict | None:
    return next((s for s in cfg.get("sources", []) if s.get("type") == source), None)


def raw_folder(workspace: Path) -> str:
    """01-raw.tmp while a collection is in progress, else the committed 01-raw."""
    return RAW_TMP if (Path(workspace) / RAW_TMP).is_dir() else RAW


def require_raw_tmp(workspace: Path) -> Path:
    tmp = Path(workspace) / RAW_TMP
    if not tmp.is_dir():
        raise CollectError(f"{RAW_TMP}/ not found; run stage.py begin 01-raw first")
    return tmp


# Raw pages -------------------------------------------------------------------

@dataclass
class Page:
    line: int
    items: list
    query: str | None = None
    error: str | None = None


def read_pages(path: Path) -> list[Page]:
    """Read a raw JSONL file. A line that is not a page becomes a Page with an error.

    Lines are split on "\\n" only, so a U+2028 inside a string does not break one.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise CollectError(f"{path}: not UTF-8 text") from exc
    except OSError as exc:
        raise CollectError(f"{path}: cannot be read ({exc.strerror})") from exc
    pages = []
    for number, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            pages.append(Page(number, [], error=f"invalid JSON: {exc.msg}"))
            continue
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            pages.append(Page(number, [], error='not a page: expected an object with an "items" array'))
            continue
        query = data.get("query") if isinstance(data.get("query"), str) else None
        error = data.get("error") if isinstance(data.get("error"), str) else None
        if error:
            error = f"export row {data.get('row')}: {error}"
        pages.append(Page(number, data["items"], query, error))
    return pages


def dumps_line(data) -> str:
    """One JSONL line, with U+0085, U+2028 and U+2029 escaped as wsio.write_jsonl does."""
    text = json.dumps(data, ensure_ascii=False)
    return text.replace("\x85", "\\u0085").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def write_pages(path: Path, pages: list[dict]) -> None:
    Path(path).write_text("".join(dumps_line(p) + "\n" for p in pages), encoding="utf-8")


# Values ----------------------------------------------------------------------

def first(item, *paths):
    """The first value found at a dotted path that is not None or empty."""
    for path in paths:
        node = item
        for key in path.split("."):
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                node = None
                break
        if node is not None and node != "" and node != [] and node != {}:
            return node
    return None


def as_list(value) -> list:
    """A list, or GraphQL {"nodes": [...]}, as a list; anything else as []."""
    if isinstance(value, dict) and isinstance(value.get("nodes"), list):
        return value["nodes"]
    return value if isinstance(value, list) else []


def names(value, *keys: str) -> list[str]:
    """Strings from a list of strings or objects (reading the first of keys), in order, unique."""
    out = []
    for entry in as_list(value):
        name = entry if isinstance(entry, str) else first(entry, *keys) if isinstance(entry, dict) else None
        if isinstance(name, str):
            name = clean(name)
            if name and name not in out:
                out.append(name)
    return out


def same(a, b) -> bool:
    return isinstance(a, str) and isinstance(b, str) and a.strip().casefold() == b.strip().casefold() != ""


def clean(text) -> str:
    """Whitespace runs as one space, ends trimmed."""
    return " ".join(str(text).split()) if text is not None else ""


_COMMENT = re.compile(r"<!--.*?(?:-->|\Z)", re.DOTALL)


def excerpt(text) -> str:
    """The body without HTML comments, whitespace collapsed, cut to 500 characters."""
    if not isinstance(text, str):
        return ""
    return clean(_COMMENT.sub(" ", text))[:EXCERPT_LENGTH]


# Timestamps ------------------------------------------------------------------

_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?)?"
                  r"\s*(Z|[+-]\d{2}:?\d{2})?", re.IGNORECASE)
_JIRA = re.compile(r"(\d{1,2})/([A-Za-z]{3})/(\d{4}|\d{2})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp][Mm])?")
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def _offset(text: str | None) -> timezone:
    if not text or text.upper() == "Z":
        return timezone.utc
    sign = 1 if text[0] == "+" else -1
    digits = text[1:].replace(":", "")
    hours, minutes = int(digits[:2]), int(digits[2:])
    if hours > 23 or minutes > 59:
        raise ValueError(text)
    return timezone(sign * timedelta(hours=hours, minutes=minutes))


def parse_timestamp(value) -> str | None:
    """A timestamp as UTC YYYY-MM-DDTHH:MM:SSZ, or None if it is not one of the accepted forms.

    Accepted: ISO 8601 (T or space, optional seconds and fraction, Z or an
    offset), a bare date, and Jira's d/Mon/yy h:mm AM. No offset means UTC.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    try:
        match = _ISO.fullmatch(text)
        if match:
            year, month, day, hour, minute, second, _, offset = match.groups()
            moment = datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0),
                              int(second or 0), tzinfo=_offset(offset))
        else:
            match = _JIRA.fullmatch(text)
            if not match:
                return None
            day, month_name, year, hour, minute, second, meridiem = match.groups()
            month = _MONTHS.get(month_name.lower())
            year = int(year) + (2000 if len(year) == 2 else 0)
            hour = int(hour)
            if meridiem:
                if not 1 <= hour <= 12 or month is None:
                    return None
                hour = hour % 12 + (12 if meridiem.lower() == "pm" else 0)
            if month is None:
                return None
            moment = datetime(year, month, int(day), hour, int(minute), int(second or 0), tzinfo=timezone.utc)
    except ValueError:
        return None
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def in_range(created: str, closed: str | None, time_range: dict) -> bool:
    """True when [created, closed or open-ended] overlaps the time range (UTC dates)."""
    start, end = time_range.get("start"), time_range.get("end")
    if end and created[:10] > end:
        return False
    return not (start and closed and closed[:10] < start)


# Drafts ----------------------------------------------------------------------

@dataclass
class Draft:
    """An evidence item before IDs and links, plus what linking needs."""

    source: str
    kind: str
    native_key: str
    title: str
    engineer_role: str
    created_at: str
    raw_ref: str
    url: str | None = None
    excerpt: str = ""
    closed_at: str | None = None
    state: str | None = None
    stats: dict | None = None
    labels: list[str] = field(default_factory=list)
    refs: set = field(default_factory=set)          # (source, native_key) this item mentions
    merge_shas: set = field(default_factory=set)    # PR/MR: its merge or squash commit
    squash_of: tuple | None = None                  # commit: the PR its "(#n)" subject names
    sha: str | None = None                          # commit hash

    def record(self, evidence_id: str, links: list[str]) -> dict:
        item = {
            "id": evidence_id, "source": self.source, "kind": self.kind, "native_key": self.native_key,
            "url": self.url, "title": self.title, "excerpt": self.excerpt,
            "engineer_role": self.engineer_role, "created_at": self.created_at,
            "closed_at": self.closed_at, "state": self.state, "labels": list(self.labels),
            "links": links, "raw_ref": self.raw_ref,
        }
        if self.stats is not None:
            item["stats"] = dict(self.stats)
        return item


@dataclass
class Result:
    """What one normalizer made of one raw file."""

    source: str
    label: str                                       # the file read, for messages
    drafts: list[Draft] = field(default_factory=list)
    bad: list[str] = field(default_factory=list)     # "<file>:<line>: <reason>"
    items: int = 0
    not_mine: int = 0
    out_of_range: int = 0
    queries: list[str] = field(default_factory=list)
    others: Counter = field(default_factory=Counter)  # identities on items that were not the engineer's

    def bad_row(self, line: int, reason: str, index: int | None = None) -> None:
        where = f"{self.label}:{line}" + (f"#/items/{index}" if index is not None else "")
        self.bad.append(f"{where}: {reason}")

    def keep(self, draft: Draft, closed_or_point: str | None, time_range: dict | None) -> None:
        """Add a draft owned by the engineer, unless it falls outside the time range."""
        if time_range is not None and not in_range(draft.created_at, closed_or_point, time_range):
            self.out_of_range += 1
            return
        self.drafts.append(draft)


def raw_ref(rel: str, line: int, index: int) -> str:
    return f"{rel}:{line}#/items/{index}"


def iterate(pages: list[Page], result: Result):
    """Yield (page, index, item) for every item, recording page errors as bad rows."""
    for page in pages:
        if page.query and page.query not in result.queries:
            result.queries.append(page.query)
        if page.error:
            result.bad_row(page.line, page.error)
            continue
        for index, item in enumerate(page.items):
            result.items += 1
            if not isinstance(item, dict):
                result.bad_row(page.line, "not an object", index)
                continue
            yield page, index, item
