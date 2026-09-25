"""Export files (CSV, JSON, JSONL) turned into raw pages, one item per page."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from .common import CollectError

FORMATS = {".csv": "csv", ".json": "json", ".jsonl": "jsonl", ".ndjson": "jsonl"}


def _decode(data: bytes, path: Path) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CollectError(f"{path}: not UTF-8 text; export it as UTF-8") from exc


def _page_items(value) -> tuple[list, str | None] | None:
    """(items, query) of a page object: {"items": [...]} or Jira's {"issues": [...]}."""
    if isinstance(value, dict):
        for key in ("items", "issues"):
            if isinstance(value.get(key), list):
                query = value.get("query") if isinstance(value.get("query"), str) else None
                return value[key], query
    return None


def _csv_pages(text: str, export: str) -> list[dict]:
    reader = csv.reader(io.StringIO(text, newline=""))
    header: list[str] | None = None
    pages = []
    try:
        start = reader.line_num + 1
        for record in reader:
            if not any(cell.strip() for cell in record):
                start = reader.line_num + 1
                continue
            if header is None:
                header = [cell.strip() for cell in record]
                counts = {h: header.count(h) for h in header}
            else:
                row: dict = {}
                for name, value in zip(header, record):
                    if counts[name] > 1:
                        row.setdefault(name, [])
                        if value.strip():
                            row[name].append(value)
                    else:
                        row[name] = value
                pages.append({"export": export, "row": start, "items": [row]})
            start = reader.line_num + 1
    except csv.Error as exc:
        raise CollectError(f"{export}: line {reader.line_num}: not valid CSV ({exc})") from exc
    if header is None:
        raise CollectError(f"{export}: empty CSV file")
    return pages


def _json_pages(text: str, export: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CollectError(f"{export}: not valid JSON ({exc})") from exc
    page = _page_items(data)
    if page is not None:
        groups = [page]
    elif isinstance(data, list) and data and all(_page_items(v) is not None for v in data):
        groups = [_page_items(v) for v in data]
    elif isinstance(data, list):
        groups = [(data, None)]
    else:
        raise CollectError(f'{export}: expected an array of items, a page object ("items" or "issues"), '
                           "or an array of pages")
    pages, row = [], 0
    for items, query in groups:
        for item in items:
            row += 1
            pages.append({**({"query": query} if query else {}), "export": export, "row": row, "items": [item]})
    return pages


def _jsonl_pages(text: str, export: str) -> list[dict]:
    pages = []
    for number, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            pages.append({"export": export, "row": number, "error": f"invalid JSON: {exc.msg}", "items": []})
            continue
        page = _page_items(value)
        items, query = page if page is not None else (value if isinstance(value, list) else [value], None)
        for item in items:
            pages.append({**({"query": query} if query else {}), "export": export, "row": number,
                          "items": [item]})
    return pages


def load(path: Path, source: str) -> list[dict]:
    """Raw pages for an export file. Raises CollectError when the file cannot be used at all."""
    path = Path(path)
    fmt = FORMATS.get(path.suffix.lower())
    if fmt is None:
        raise CollectError(f"{path}: unsupported export format {path.suffix or '(no extension)'!r}; "
                           "use .json, .jsonl or (for Jira) .csv")
    if fmt == "csv" and source != "jira":
        raise CollectError(f"{path}: CSV exports are read for Jira only; export {source} as JSON")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CollectError(f"{path}: cannot be read ({exc.strerror})") from exc
    text = _decode(data, path)
    export = str(path)
    if fmt == "csv":
        return _csv_pages(text, export)
    if fmt == "json":
        return _json_pages(text, export)
    return _jsonl_pages(text, export)
