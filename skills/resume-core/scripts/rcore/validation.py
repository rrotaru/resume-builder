"""Schema validation for workspace files, mapped by path."""
from __future__ import annotations

import fnmatch
import json
import os
import posixpath
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
    ("decisions/wizard.json", "wizard-state", "json"),
    ("*/_stage.json", "stage", "json"),
    ("02-evidence/evidence.jsonl", "evidence", "jsonl"),
    ("03-profile/profile.json", "resume", "json"),
    ("03-profile/source.json", "profile-source", "json"),
    ("04-projects/signals.json", "signals", "json"),
    ("04-projects/groups.json", "project-groups", "json"),
    ("04-projects/projects.json", "projects", "json"),
    ("05-terms/candidates.json", "term-candidates", "json"),
    ("06-bullets/bullets.json", "bullets", "json"),
    ("07-sanitized/bullets.json", "bullets", "json"),
    ("07-sanitized/profile.json", "resume", "json"),
    ("07-sanitized/new-terms.json", "term-candidates", "json"),
    ("08-ats/general/resume.json", "tailored-resume", "json"),
    ("08-ats/general/keywords.json", "ats-keywords", "json"),
    ("08-ats/general/report.json", "ats-report", "json"),
    ("08-ats/jobs/*/resume.json", "tailored-resume", "json"),
    ("08-ats/jobs/*/keywords.json", "ats-keywords", "json"),
    ("08-ats/jobs/*/report.json", "ats-report", "json"),
    ("08-ats/jobs/*/flags.json", "flags", "json"),
]


def _matches(rel: str, pattern: str) -> bool:
    """Match one path segment per pattern segment, ignoring case (a case-insensitive
    file system opens '08-ATS/...' as the real file)."""
    parts, pattern_parts = rel.lower().split("/"), pattern.lower().split("/")
    return len(parts) == len(pattern_parts) and all(
        fnmatch.fnmatchcase(p, q) for p, q in zip(parts, pattern_parts)
    )


def logical_path(rel: str) -> str:
    """Map a path inside '<stage>.tmp/' to the path it will have once committed."""
    first, sep, rest = rel.partition("/")
    if first.endswith(".tmp"):
        first = first[: -len(".tmp")]
    return first + sep + rest


def workspace_relative(workspace, rel) -> str | None:
    """Resolve a path given relative to (or inside) the workspace.

    Backslashes are read as "/". The path is resolved with os.path.realpath
    (so "..", "." and symlinks are followed) and made relative to the real
    workspace, with "/" separators ("." for the workspace itself). Returns
    None when the path resolves outside the workspace.
    """
    spelled = str(rel).replace("\\", "/")
    root = os.path.realpath(workspace)
    try:
        path = os.path.relpath(os.path.realpath(os.path.join(root, spelled)), root)
    except ValueError:  # a different drive on Windows
        return None
    path = path.replace(os.sep, "/")
    if path == ".." or path.startswith("../") or os.path.isabs(path):
        return None
    return path


def outside_error(rel) -> str:
    return f"{rel}: outside the workspace"


def schema_for(rel: str) -> tuple[str, str] | None:
    """Return (schema name, format) for a workspace-relative path, or None.

    The path is normalized first, so "./a", "a//b" and "a/../a" spellings map
    the same way as the plain path. Backslashes are read as "/" and case is
    ignored.
    """
    logical = logical_path(posixpath.normpath(str(rel).replace("\\", "/")).lower())
    for pattern, name, fmt in FILE_SCHEMAS:
        if _matches(logical, pattern):
            return name, fmt
    return None


def _duplicate_ids(records: list) -> list[str]:
    ids = [r["id"] for r in records if isinstance(r, dict) and isinstance(r.get("id"), str)]
    return sorted(i for i, n in Counter(ids).items() if n > 1)


def validate_file(path: Path, rel: str, logical: str | None = None) -> list[str]:
    """Validate one file against the schema its path maps to. Unmapped files pass.

    rel labels the errors; logical (default rel) is the resolved
    workspace-relative path used to choose the schema.
    """
    mapping = schema_for(rel if logical is None else logical)
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
    """Validate files and directories given relative to the workspace.

    Paths are resolved (see workspace_relative). A path outside the workspace
    is an error, and so is a named file that no schema maps to. Files found
    while walking a named directory pass when unmapped (01-raw has no schema).
    """
    return _validate(Path(workspace), rels, named_files_need_schema=True)


def _validate(workspace: Path, rels: list[str], named_files_need_schema: bool) -> list[str]:
    errors: list[str] = []
    for rel in rels:
        normalized = workspace_relative(workspace, rel)
        if normalized is None:
            errors.append(outside_error(rel))
            continue
        target = workspace / normalized
        if target.is_dir():
            for path in sorted(p for p in target.rglob("*") if p.is_file()):
                errors += validate_file(path, path.relative_to(workspace).as_posix())
        elif target.is_file():
            if schema_for(normalized) is None:
                if named_files_need_schema:
                    errors.append(f"{rel}: no schema for this path")
                continue
            label = normalized if os.path.isabs(str(rel)) else str(rel)
            errors += validate_file(target, label, logical=normalized)
        else:
            errors.append(f"{rel}: not found")
    return errors


def validate_workspace(workspace: Path) -> list[str]:
    """Validate every committed file in the workspace (skips *.tmp and *.old folders).

    Unmapped files pass, as in a directory walk.
    """
    workspace = Path(workspace)
    rels = sorted(
        p.name for p in workspace.iterdir()
        if not p.name.endswith((".tmp", ".old"))
    )
    return _validate(workspace, rels, named_files_need_schema=False)
