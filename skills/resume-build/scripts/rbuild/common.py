"""Shared pieces: errors, the workspace files build reads, and reading them validated."""
from __future__ import annotations

import copy
import datetime
from pathlib import Path

from rcore import terms, validation, wsio

CONFIG = "config.json"
DECISIONS = "decisions"
DECISION_FILES = ("terms.json", "projects.json", "metrics.json", "profile.json", "attestations.json",
                  "wizard.json")
ATTESTATIONS = "decisions/attestations.json"
TERMS = terms.TERMS_FILE
SOURCE = "03-profile/source.json"
PROFILE = "03-profile/profile.json"
BULLETS_BEFORE, STORIES_BEFORE = "06-bullets/bullets.json", "06-bullets/stories.md"
BULLETS, STORIES = "07-sanitized/bullets.json", "07-sanitized/stories.md"
SANITIZED_PROFILE, NEW_TERMS = "07-sanitized/profile.json", "07-sanitized/new-terms.json"
ATS = "08-ats"

# The command that writes each file build reads, for error lines.
WRITERS = {CONFIG: "resume-init and resume-collect's configure.py", ATTESTATIONS: "attest.py",
           TERMS: "resume-wizard's answer.py", SOURCE: "resume-import", ATS: "resume-ats"}


class BuildError(Exception):
    """A problem that stops a build script (exit 1). Holds one or more lines."""

    def __init__(self, lines):
        self.lines = [lines] if isinstance(lines, str) else list(lines)
        super().__init__("; ".join(self.lines))


def plural(count: int, noun: str, many: str | None = None) -> str:
    """"1 item", "2 items"."""
    return f"{count} {noun if count == 1 else many or noun + 's'}"


def today() -> datetime.date:
    """The current date. Tests replace it to fix the date."""
    return datetime.date.today()


def writer_of(rel: str) -> str:
    first = rel.split("/", 1)[0]
    return WRITERS.get(rel) or WRITERS.get(first) or "the step that writes it"


def load(workspace: Path, rel: str, default=None):
    """A workspace file, validated against its schema; a copy of default when it is missing.

    Raises BuildError naming the file and what writes it when it cannot be read
    or does not validate.
    """
    workspace = Path(workspace)
    if not (workspace / rel).is_file():
        return copy.deepcopy(default)
    errors = validation.validate_paths(workspace, [rel])
    data = None
    if not errors:
        data, error = wsio.load(workspace, rel, validation.schema_for(rel)[1])
        errors = [error] if error else []
    if errors:
        raise BuildError(errors + [f"{rel} is not valid; it is written by {writer_of(rel)}"])
    return data


def load_text(workspace: Path, rel: str) -> str | None:
    """A text file of the workspace, or None when it is missing or not UTF-8."""
    data, error = wsio.load(workspace, rel, "text")
    return None if error else data


def term_entries(workspace: Path) -> list[dict]:
    """decisions/terms.json entries, as the terms check reads them ([] when missing). Raises BuildError."""
    if not (Path(workspace) / TERMS).is_file():
        return []
    entries, errors = terms.read_entries(workspace)
    if errors:
        raise BuildError(errors + [f"{TERMS} is not valid; fix it with resume-wizard's answer.py term or "
                                   "answer.py remove-term"])
    return entries


def patterns(entries: list[dict]) -> terms.Patterns:
    return terms.compile_terms([e["term"] for e in entries if e["replacement"] is not None],
                               [e["term"] for e in entries if e["replacement"] is None])
