"""Shared pieces: errors, the files the wizard reads and writes, atomic writes."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

from rcore import schema, terms, validation, wsio

PROFILE = "03-profile/profile.json"
SOURCE = "03-profile/source.json"
PROJECTS = "04-projects/projects.json"
CANDIDATES = "05-terms/candidates.json"
NEW_TERMS = "07-sanitized/new-terms.json"
WIZARD_PROFILE = "decisions/profile.json"
TERMS = terms.TERMS_FILE
METRICS = "decisions/metrics.json"
PROJECT_DECISIONS = "decisions/projects.json"
STATE = "decisions/wizard.json"
UNCHANGED = "decisions/ unchanged"


class WizardError(Exception):
    """A problem that stops a wizard script (exit 1). Holds one or more lines."""

    def __init__(self, lines):
        self.lines = [lines] if isinstance(lines, str) else list(lines)
        super().__init__("; ".join(self.lines))


def plural(count: int, noun: str, many: str | None = None) -> str:
    return f"{count} {noun if count == 1 else many or noun + 's'}"


def shorten(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def compact(value) -> str:
    """A value as one line of JSON, shortened: {"endDate": "2022-12"}."""
    return shorten(json.dumps(value, ensure_ascii=False), 80)


def load(workspace: Path, rel: str, default=None):
    """A workspace file validated against its schema; a copy of default when it is missing.

    Raises WizardError when the file cannot be read or does not validate.
    """
    workspace = Path(workspace)
    if not (workspace / rel).is_file():
        return copy.deepcopy(default)
    errors = validation.validate_paths(workspace, [rel])
    if errors:
        raise WizardError(errors)
    data, error = wsio.load(workspace, rel, validation.schema_for(rel)[1])
    if error:
        raise WizardError(error)
    return data


def load_terms(workspace: Path) -> list[dict]:
    """decisions/terms.json entries ([] when missing), valid as the terms check requires. Raises WizardError."""
    if not (Path(workspace) / TERMS).is_file():
        return []
    entries, errors = terms.read_entries(workspace)
    if errors:
        raise WizardError(errors + [f"fix {TERMS} with answer.py term or answer.py remove-term"])
    return entries


def patterns_for(entries: list[dict]) -> terms.Patterns:
    return terms.compile_terms([e["term"] for e in entries if e["replacement"] is not None],
                               [e["term"] for e in entries if e["replacement"] is None])


def check_schema(data, name: str, rel: str) -> None:
    """Raise WizardError when data does not match schemas/<name>.schema.json."""
    errors = schema.validate(data, schema.load_schema(name))
    if errors:
        raise WizardError([f"the change would make {rel} invalid:"] + [f"{rel}: {e}" for e in errors])


def save_json(workspace: Path, rel: str, data) -> None:
    """Write JSON through a temporary file and replace the target atomically."""
    path = Path(workspace) / rel
    tmp = path.with_name(path.name + ".tmp")
    wsio.write_json(tmp, data)
    os.replace(tmp, path)
