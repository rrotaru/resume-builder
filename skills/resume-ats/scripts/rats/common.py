"""Shared pieces: errors, workspace files, versions and slugs, and reading the inputs."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rcore import validation, wsio
from rcore.profile import overlay

STAGE, TMP = "08-ats", "08-ats.tmp"
BULLETS = "07-sanitized/bullets.json"
SANITIZED_PROFILE = "07-sanitized/profile.json"
PROFILE = "03-profile/profile.json"
WIZARD_PROFILE = "decisions/profile.json"
TERMS = "decisions/terms.json"
METRICS = "decisions/metrics.json"
PROJECTS = "04-projects/projects.json"
EVIDENCE = "02-evidence/evidence.jsonl"
RAW = "01-raw"
CONFIG = "config.json"
# What 08-ats records, in this order, each that exists. Never decisions/attestations.json.
INPUTS = (BULLETS, SANITIZED_PROFILE, PROFILE, WIZARD_PROFILE, TERMS, METRICS, PROJECTS, EVIDENCE, RAW, CONFIG)

GENERAL = "general"
RESUME, KEYWORDS, REPORT, FLAGS, JD = "resume.json", "keywords.json", "report.json", "flags.json", "jd.txt"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# The command that writes each input, for error lines.
WRITERS = {BULLETS: "/resume-builder:sanitize", SANITIZED_PROFILE: "/resume-builder:sanitize",
           PROFILE: "/resume-builder:import", WIZARD_PROFILE: "/resume-builder:wizard",
           TERMS: "/resume-builder:wizard", METRICS: "/resume-builder:wizard",
           PROJECTS: "/resume-builder:analyze", EVIDENCE: "/resume-builder:collect",
           CONFIG: "/resume-builder:collect"}


class AtsError(Exception):
    """A problem that stops a script (exit 1). Holds one or more lines."""

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


@dataclass(frozen=True)
class Version:
    """The general resume, or a job version named by its slug."""
    name: str

    @property
    def is_job(self) -> bool:
        return self.name != GENERAL

    @property
    def folder(self) -> str:
        return f"jobs/{self.name}" if self.is_job else GENERAL

    def draft(self, file: str = "") -> str:
        """A path in the draft, relative to the workspace: 08-ats.tmp/jobs/<slug>/resume.json."""
        return f"{TMP}/{self.folder}" + (f"/{file}" if file else "")

    def committed(self, file: str = "") -> str:
        return f"{STAGE}/{self.folder}" + (f"/{file}" if file else "")


def slug_error(slug: str) -> str | None:
    """Why a job slug is not usable, or None."""
    if not SLUG.fullmatch(slug):
        return f"{slug!r} is not a job slug: use lower-case letters, digits and '-', starting with a letter or digit"
    if slug == GENERAL:
        return "'general' is the general resume; give the job another slug with --job"
    return None


def slug_from(path: Path) -> str:
    """'fintech-sre' from 'Fintech SRE.txt': lower case, each run of other characters as '-'."""
    return re.sub(r"[^a-z0-9]+", "-", Path(path).stem.lower()).strip("-")


def version(name: str) -> Version:
    """The version a command-line name gives. Raises AtsError for a bad slug."""
    if name == GENERAL:
        return Version(GENERAL)
    error = slug_error(name)
    if error:
        raise AtsError(error)
    return Version(name)


def draft_versions(workspace: Path) -> list[Version]:
    """The versions in the draft: general (if its folder exists), then each job folder in name order."""
    root = Path(workspace) / TMP
    found = [Version(GENERAL)] if (root / GENERAL).is_dir() else []
    jobs = root / "jobs"
    if jobs.is_dir():
        found += [Version(p.name) for p in sorted(jobs.iterdir()) if p.is_dir()]
    return found


def committed_versions(workspace: Path) -> list[str]:
    root = Path(workspace) / STAGE
    names = [GENERAL] if (root / GENERAL).is_dir() else []
    jobs = root / "jobs"
    if jobs.is_dir():
        names += [p.name for p in sorted(jobs.iterdir()) if p.is_dir()]
    return names


def load(workspace: Path, rel: str, missing: str | None = None):
    """A workspace file validated against its schema.

    Returns None when the file is missing and missing is None; otherwise a
    missing file raises AtsError with the message missing. Raises AtsError
    when the file does not validate or cannot be read.
    """
    workspace = Path(workspace)
    if not (workspace / rel).is_file():
        if missing is None:
            return None
        raise AtsError(missing)
    errors = validation.validate_paths(workspace, [rel])
    if errors:
        raise AtsError(errors + [f"{rel} is not valid; fix it with {WRITERS[rel]}"])
    data, error = wsio.load(workspace, rel, validation.schema_for(rel)[1])
    if error:
        raise AtsError(error)
    return data


@dataclass
class Inputs:
    bullets: list[dict]  # 07-sanitized/bullets.json
    sanitized_profile: dict | None  # 07-sanitized/profile.json
    profile: dict | None  # 03-profile/profile.json
    wizard: dict  # decisions/profile.json, {} when there is none
    terms: list[dict]  # decisions/terms.json
    metrics: list[dict]
    projects: list[dict]
    evidence: list[dict]
    config: dict | None

    @property
    def effective(self) -> dict:
        """The imported profile with the wizard's answers laid over it."""
        return overlay(self.profile or {}, self.wizard)

    @property
    def target_role(self) -> str:
        role = (self.config or {}).get("target_role")
        return role.strip() if isinstance(role, str) else ""


def load_inputs(workspace: Path) -> Inputs:
    """Read and validate what ats reads. Raises AtsError."""
    bullets = load(workspace, BULLETS, f"{BULLETS} not found; run /resume-builder:write, then "
                                       "/resume-builder:sanitize (apply) first")
    terms = load(workspace, TERMS, f"{TERMS} not found; run init_workspace.py (resume-core) first")
    return Inputs(
        bullets=bullets,
        sanitized_profile=load(workspace, SANITIZED_PROFILE),
        profile=load(workspace, PROFILE),
        wizard=load(workspace, WIZARD_PROFILE) or {},
        terms=terms,
        metrics=load(workspace, METRICS) or [],
        projects=load(workspace, PROJECTS) or [],
        evidence=load(workspace, EVIDENCE) or [],
        config=load(workspace, CONFIG),
    )


def recorded_inputs(workspace: Path) -> list[str]:
    """The inputs 08-ats records: each of INPUTS that exists."""
    return [rel for rel in INPUTS if (Path(workspace) / rel).exists()]
