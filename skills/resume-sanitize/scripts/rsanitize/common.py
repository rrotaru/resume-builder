"""Shared pieces: errors, workspace files and reading the inputs."""
from __future__ import annotations

from pathlib import Path

from rcore import terms, validation, wsio

SCAN_STAGE, SCAN_TMP = "05-terms", "05-terms.tmp"
APPLY_STAGE, APPLY_TMP = "07-sanitized", "07-sanitized.tmp"
PROJECTS = "04-projects/projects.json"
EVIDENCE = "02-evidence/evidence.jsonl"
RAW = "01-raw"
PROFILE = "03-profile/profile.json"
WIZARD_PROFILE = "decisions/profile.json"
TERMS = terms.TERMS_FILE
CANDIDATES = "05-terms/candidates.json"
BULLETS = "06-bullets/bullets.json"
STORIES = "06-bullets/stories.md"


class SanitizeError(Exception):
    """A problem that stops a sanitize script (exit 1). Holds one or more lines."""

    def __init__(self, lines):
        self.lines = [lines] if isinstance(lines, str) else list(lines)
        super().__init__("; ".join(self.lines))


def plural(count: int, noun: str, many: str | None = None) -> str:
    """"1 place", "2 places"."""
    return f"{count} {noun if count == 1 else many or noun + 's'}"


def shorten(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def load(workspace: Path, rel: str, missing: str | None = None):
    """A workspace file, validated against its schema (JSON, JSONL or text).

    Returns None when the file is missing and missing is None; otherwise a
    missing file raises SanitizeError with the message missing. Raises
    SanitizeError when the file does not validate or cannot be read.
    """
    workspace = Path(workspace)
    if not (workspace / rel).is_file():
        if missing is None:
            return None
        raise SanitizeError(missing)
    mapping = validation.schema_for(rel)
    errors = validation.validate_paths(workspace, [rel]) if mapping else []
    if errors:
        raise SanitizeError(errors)
    data, error = wsio.load(workspace, rel, mapping[1] if mapping else "text")
    if error:
        raise SanitizeError(error)
    return data


def load_terms(workspace: Path) -> list[dict]:
    """decisions/terms.json entries, validated as the terms check does. Raises SanitizeError."""
    entries, errors = terms.read_entries(workspace)
    if errors:
        raise SanitizeError(errors + [f"{TERMS} must be valid; fix it with /resume-builder:wizard"])
    return entries


def decided_keys(entries: list[dict]) -> set[str]:
    return {terms.key(e["term"]) for e in entries}


def patterns_for(entries: list[dict]) -> terms.Patterns:
    """Denied and allowed patterns from decisions/terms.json entries."""
    return terms.compile_terms([e["term"] for e in entries if e["replacement"] is not None],
                               [e["term"] for e in entries if e["replacement"] is None])


def allowed_terms(entries: list[dict]) -> list[str]:
    return [e["term"] for e in entries if e["replacement"] is None]
