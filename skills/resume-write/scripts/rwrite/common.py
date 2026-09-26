"""Shared pieces: errors, workspace files and reading the inputs."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rcore import validation, wsio
from rcore.profile import overlay

STAGE, TMP = "06-bullets", "06-bullets.tmp"
PROJECTS = "04-projects/projects.json"
EVIDENCE = "02-evidence/evidence.jsonl"
RAW = "01-raw"
PROFILE = "03-profile/profile.json"
WIZARD_PROFILE = "decisions/profile.json"
METRICS = "decisions/metrics.json"
COMMITTED = f"{STAGE}/bullets.json"
DRAFT = f"{TMP}/bullets.json"
STORIES = f"{TMP}/stories.md"

# The command that writes each input, for error lines.
WRITERS = {PROJECTS: "/resume-builder:analyze", EVIDENCE: "/resume-builder:collect",
           PROFILE: "/resume-builder:import", WIZARD_PROFILE: "/resume-builder:wizard",
           METRICS: "/resume-builder:wizard"}


class WriteError(Exception):
    """A problem that stops write.py (exit 1). Holds one or more lines."""

    def __init__(self, lines):
        self.lines = [lines] if isinstance(lines, str) else list(lines)
        super().__init__("; ".join(self.lines))


def plural(count: int, noun: str, many: str | None = None) -> str:
    """"1 bullet", "2 bullets"."""
    return f"{count} {noun if count == 1 else many or noun + 's'}"


def shorten(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def one_line(text: str) -> str:
    """text with every run of whitespace, line breaks included, as one space."""
    return " ".join(text.split())


def load(workspace: Path, rel: str, missing: str | None = None):
    """A workspace file validated against its schema.

    Returns None when the file is missing and missing is None; otherwise a
    missing file raises WriteError with the message missing. Raises WriteError
    when the file does not validate or cannot be read.
    """
    workspace = Path(workspace)
    if not (workspace / rel).is_file():
        if missing is None:
            return None
        raise WriteError(missing)
    errors = validation.validate_paths(workspace, [rel])
    if errors:
        raise WriteError(errors + [f"{rel} is not valid; fix it with {WRITERS[rel]}"])
    data, error = wsio.load(workspace, rel, validation.schema_for(rel)[1])
    if error:
        raise WriteError(error)
    return data


@dataclass
class Inputs:
    projects: list[dict]
    evidence: list[dict]
    profile: dict | None  # 03-profile/profile.json; None when there is none
    wizard: dict  # decisions/profile.json, {} when there is none
    metrics: list[dict]  # decisions/metrics.json, [] when there is none

    @property
    def effective(self) -> dict:
        """The imported profile with the wizard's answers laid over it."""
        return overlay(self.profile or {}, self.wizard)


def load_inputs(workspace: Path) -> Inputs:
    """Read and validate what write reads. Raises WriteError."""
    projects = load(workspace, PROJECTS, f"{PROJECTS} not found; run /resume-builder:analyze first")
    evidence = load(workspace, EVIDENCE, f"{EVIDENCE} not found; run /resume-builder:collect first")
    profile = load(workspace, PROFILE)
    wizard = load(workspace, WIZARD_PROFILE)
    metrics = load(workspace, METRICS)
    return Inputs(projects, evidence, profile, wizard or {}, metrics or [])
