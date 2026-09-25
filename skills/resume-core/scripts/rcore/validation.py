"""Schema validation for workspace files, mapped by path."""
from __future__ import annotations

import fnmatch
import json
from collections import Counter
from pathlib import Path

from . import schema, wsio

# (path pattern relative to the workspace, schema name, file format).
# "*" matches exactly one path segment.
FILE_SCHEMAS: list[tuple[str, str, str]] = [
    ("config.json", "config", "json"),
    ("decisions/terms.json", "terms", "json"),
    ("decisions/projects.json", "project-decisions", "json"),
    ("decisions/metrics.json", "metrics", "json"),
    ("decisions/profile.json", "resume", "json"),
    ("decisions/attestations.json", "attestations", "json"),
    ("*/_stage.json", "stage", "json"),
    ("02-evidence/evidence.jsonl", "evidence", "jsonl"),
    ("03-profile/profile.json", "resume", "json"),
    ("04-projects/projects.json", "projects", "json"),
    ("05-terms/candidates.json", "term-candidates", "json"),
    ("06-bullets/bullets.json", "bullets", "json"),
    ("07-sanitized/bullets.json", "bullets", "json"),
    ("07-sanitized/profile.json", "resume", "json"),
    ("07-sanitized/new-terms.json", "term-candidates", "json"),
    ("08-ats/general/resume.json", "resume", "json"),
    ("08-ats/jobs/*/resume.json", "resume", "json"),
    ("08-ats/jobs/*/flags.json", "flags", "json"),
]


def _matches(rel: str, pattern: str) -> bool:
    parts, pattern_parts = rel.split("/"), pattern.split("/")
    return len(parts) == len(pattern_parts) and all(
        fnmatch.fnmatchcase(p, q) for p, q in zip(parts, pattern_parts)
    )


def logical_path(rel: str) -> str:
    """Map a path inside '<stage>.tmp/' to the path it will have once committed."""
    first, sep, rest = rel.partition("/")
    if first.endswith(".tmp"):
        first = first[: -len(".tmp")]
    return first + sep + rest


def schema_for(rel: str) -> tuple[str, str] | None:
    """Return (schema name, format) for a workspace-relative path, or None."""
    logical = logical_path(rel)
    for pattern, name, fmt in FILE_SCHEMAS:
        if _matches(logical, pattern):
            return name, fmt
    return None


def _duplicate_ids(records: list) -> list[str]:
    ids = [r["id"] for r in records if isinstance(r, dict) and isinstance(r.get("id"), str)]
    return sorted(i for i, n in Counter(ids).items() if n > 1)


def validate_file(path: Path, rel: str) -> list[str]:
    """Validate one file against the schema its path maps to. Unmapped files pass."""
    mapping = schema_for(rel)
    if mapping is None:
        return []
    name, fmt = mapping
    spec = schema.load_schema(name)
    try:
        if fmt == "jsonl":
            records = wsio.read_jsonl(path)
            errors = []
            for lineno, record in enumerate(records, start=1):
                errors += [f"{rel}: record {lineno}: {e}" for e in schema.validate(record, spec)]
            data = records
        else:
            data = wsio.read_json(path)
            errors = [f"{rel}: {e}" for e in schema.validate(data, spec)]
    except UnicodeDecodeError:
        return [f"{rel}: not UTF-8 text"]
    except (ValueError, json.JSONDecodeError) as exc:
        return [f"{rel}: {exc}"]
    if isinstance(data, list):
        errors += [f"{rel}: duplicate id {i!r}" for i in _duplicate_ids(data)]
    return errors


def validate_paths(workspace: Path, rels: list[str]) -> list[str]:
    """Validate files and directories given relative to the workspace."""
    workspace = Path(workspace)
    errors: list[str] = []
    for rel in rels:
        target = workspace / rel
        if target.is_dir():
            for path in sorted(p for p in target.rglob("*") if p.is_file()):
                errors += validate_file(path, path.relative_to(workspace).as_posix())
        elif target.is_file():
            errors += validate_file(target, rel)
        else:
            errors.append(f"{rel}: not found")
    return errors


def validate_workspace(workspace: Path) -> list[str]:
    """Validate every committed file in the workspace (skips *.tmp and *.old folders)."""
    workspace = Path(workspace)
    rels = sorted(
        p.name for p in workspace.iterdir()
        if not p.name.endswith((".tmp", ".old"))
    )
    return validate_paths(workspace, rels)
