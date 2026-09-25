"""Performance reviews: reading the files in reviews_dir, and turning them into evidence."""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath

from rcore import documents

from . import refs
from .common import Draft, Result, clean, excerpt, iterate, raw_ref

SOURCE = "review"
_NAME_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")


def review_files(root: Path) -> tuple[list[Path], list[Path]]:
    """(supported files, unsupported files) under root, recursively, in path order, skipping hidden ones."""
    supported, unsupported = [], []
    for path in sorted(p for p in Path(root).rglob("*") if p.is_file()):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        (supported if path.suffix.lower() in documents.FORMATS else unsupported).append(path)
    return supported, unsupported


def file_date(path: Path) -> tuple[str, str]:
    """(YYYY-MM-DD, "name" or "modified"): the first real date in the name, else the modification date."""
    for year, month, day in _NAME_DATE.findall(Path(path).name):
        try:
            return date(int(year), int(month), int(day)).isoformat(), "name"
        except ValueError:
            continue
    modified = datetime.fromtimestamp(Path(path).stat().st_mtime, tz=timezone.utc)
    return modified.date().isoformat(), "modified"


def read_review(root: Path, path: Path) -> dict:
    """One raw review item. Raises documents.ExtractError (or NoText) when the file has no usable text."""
    data = path.read_bytes()
    fmt = documents.FORMATS[path.suffix.lower()]
    text = documents.extract(data, fmt, str(path)).text
    day, source = file_date(path)
    return {"file": path.relative_to(root).as_posix(), "path": str(path.resolve()),
            "sha256": "sha256:" + hashlib.sha256(data).hexdigest(), "format": fmt,
            "date": day, "date_from": source, "text": text}


def normalize(pages, rel: str, label: str) -> Result:
    result = Result(SOURCE, label)
    for page, index, item in iterate(pages, result):
        name, text, day = item.get("file"), item.get("text"), item.get("date")
        valid_day = isinstance(day, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", day)
        problem = ("no file name" if not isinstance(name, str) or not name
                   else "no text" if not isinstance(text, str)
                   else f"date {day!r} is not YYYY-MM-DD" if not valid_day else None)
        if problem:
            result.bad_row(page.line, problem, index)
            continue
        lines = [line for line in text.split("\n") if line.strip()]
        title = clean(lines[0]) if lines else ""
        rest = text.split(lines[0], 1)[1] if lines else ""
        pure = PurePosixPath(name)
        draft = Draft(
            source=SOURCE, kind="perf_review", native_key=str(pure.with_suffix("")), title=title,
            engineer_role="subject", created_at=f"{day}T00:00:00Z", raw_ref=raw_ref(rel, page.line, index),
            excerpt=excerpt(rest),
        )
        draft.refs = refs.find(text)
        result.keep(draft, None, None)
    return result
