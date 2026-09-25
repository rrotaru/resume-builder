"""Shared pieces: errors, workspace files, dates and the kinds of evidence."""
from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

from rcore import schema, stages, validation, wsio

STAGE, TMP = "04-projects", "04-projects.tmp"
EVIDENCE = "02-evidence/evidence.jsonl"
DECISIONS = "decisions/projects.json"
METRICS = "decisions/metrics.json"
RAW = "01-raw"

# Kinds in the order signals list them. Performance reviews are never clustered.
KINDS = ("pr", "mr", "commit", "review", "issue", "ticket", "epic")
AUTHORED_KINDS = ("pr", "mr", "commit")
OPEN_KINDS = ("pr", "mr", "issue", "ticket", "epic")


class AnalyzeError(Exception):
    """A problem that stops an analyze script (exit 1). Holds one or more lines."""

    def __init__(self, lines):
        self.lines = [lines] if isinstance(lines, str) else list(lines)
        super().__init__("; ".join(self.lines))


def plural(count: int, noun: str, many: str | None = None) -> str:
    """"1 item", "2 items"."""
    return f"{count} {noun if count == 1 else many or noun + 's'}"


def shorten(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


# Workspace files -------------------------------------------------------------

def load_config(workspace: Path) -> dict:
    """Read and validate config.json. Raises AnalyzeError."""
    workspace = Path(workspace)
    if not (workspace / "config.json").is_file():
        raise AnalyzeError(f"{workspace / 'config.json'} not found; run /resume-builder:init first")
    data, error = wsio.load(workspace, "config.json")
    if error:
        raise AnalyzeError(error)
    errors = schema.validate(data, schema.load_schema("config"))
    if errors:
        raise AnalyzeError([f"config.json: {e}" for e in errors])
    return data


_TIMESTAMP = re.compile(r"^(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}Z$")


def _is_timestamp(value) -> bool:
    match = _TIMESTAMP.match(value) if isinstance(value, str) else None
    try:
        return match is not None and bool(date.fromisoformat(match.group(1)))
    except ValueError:
        return False


def load_evidence(workspace: Path) -> list[dict]:
    """The committed evidence, validated, with UTC timestamps as resume-collect writes them. Raises AnalyzeError."""
    if not (Path(workspace) / EVIDENCE).is_file():
        raise AnalyzeError(f"{EVIDENCE} not found; run /resume-builder:collect first")
    errors = validation.validate_paths(workspace, [EVIDENCE])
    records = [] if errors else wsio.read_jsonl(Path(workspace) / EVIDENCE)
    for n, record in enumerate(records, start=1):
        for name in ("created_at", "closed_at"):
            value = record.get(name)
            if (name == "created_at" or value is not None) and not _is_timestamp(value):
                errors.append(f"{EVIDENCE}: record {n}: {name} {value!r} is not YYYY-MM-DDTHH:MM:SSZ")
    if errors:
        raise AnalyzeError(errors + [f"{EVIDENCE} is not valid; run /resume-builder:collect again"])
    return records


def evidence_hash(workspace: Path) -> str:
    return stages.hash_path(Path(workspace) / EVIDENCE)


def load_list(workspace: Path, rel: str, schema_name: str, missing_ok: bool = True) -> list:
    """A JSON list file checked against its schema; [] when missing and missing_ok. Raises AnalyzeError."""
    path = Path(workspace) / rel
    if not path.is_file():
        if missing_ok:
            return []
        raise AnalyzeError(f"{rel}: not found")
    data, error = wsio.load(workspace, rel)
    if error:
        raise AnalyzeError(error)
    errors = schema.validate(data, schema.load_schema(schema_name))
    if errors:
        raise AnalyzeError([f"{rel}: {e}" for e in errors])
    return data


def save_json(path: Path, data) -> None:
    """Write JSON through a temporary file and replace the target atomically."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    wsio.write_json(tmp, data)
    os.replace(tmp, path)


# Evidence --------------------------------------------------------------------

def day(timestamp: str) -> str:
    """The UTC date (YYYY-MM-DD) of an evidence timestamp."""
    return timestamp[:10]


def month(timestamp: str) -> str:
    return timestamp[:7]


def days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def last_timestamp(item: dict) -> str:
    """The later of created_at and closed_at."""
    closed = item.get("closed_at")
    return max(item["created_at"], closed) if isinstance(closed, str) and closed else item["created_at"]


def is_authored(item: dict) -> bool:
    """Authored work: a pull request, merge request or commit the engineer wrote."""
    return item["kind"] in AUTHORED_KINDS and item["engineer_role"] == "author"


def is_reported(item: dict) -> bool:
    return item["engineer_role"] == "reporter" or (item["kind"] == "issue" and item["engineer_role"] == "author")


def is_perf_review(item: dict) -> bool:
    return item["kind"] == "perf_review"
