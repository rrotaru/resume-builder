"""Pre-render gate: the resume-core checks in a fixed order, each problem with its fix.

1. Validation of every file render reads. If it reports anything, stop:
   the later checks assume schema-valid files.
2. Render preconditions (basics.name).
3. Sources, including the fact-field rules.
4. Terms, on each resume and on 07-sanitized/stories.md.
5. Flags, on each job version.

Steps 2 to 5 all run, so one render reports every problem. Each problem's
line is the line the standalone script prints.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rcore import flags, sources, terms, validation, wsio

STORIES = "07-sanitized/stories.md"
UNSANITIZED_STORIES = "06-bullets/stories.md"
# Files the checks read, validated and hashed when they exist.
SHARED_INPUTS = (
    "config.json",
    "decisions/terms.json",
    "decisions/profile.json",
    "decisions/metrics.json",
    "decisions/attestations.json",
    "02-evidence/evidence.jsonl",
    "03-profile/profile.json",
)
SHARED = "shared"
ATS = "/resume-builder:ats"
WIZARD = "/resume-builder:wizard"
_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")


@dataclass(frozen=True)
class Target:
    name: str  # "general" or a job slug

    @property
    def is_job(self) -> bool:
        return self.name != "general"

    @property
    def folder(self) -> str:
        return f"jobs/{self.name}" if self.is_job else "general"

    @property
    def resume(self) -> str:
        return f"08-ats/{self.folder}/resume.json"

    @property
    def flags(self) -> str | None:
        return f"08-ats/{self.folder}/flags.json" if self.is_job else None

    @property
    def ats(self) -> str:
        """The command that rebuilds this version."""
        return f"{ATS} for job {self.name}" if self.is_job else ATS


@dataclass(frozen=True)
class Problem:
    group: str  # a target name, or "shared"
    line: str
    fix: str


def discover(workspace: Path, requested: list[str] | None = None) -> tuple[list[Target], list[str]]:
    """Targets to render: the requested ones, or general (if present) and every job folder."""
    workspace = Path(workspace)
    if requested:
        bad = [name for name in requested if name != "general" and not _NAME.fullmatch(name)]
        if bad:
            return [], [f"{name}: not a target (use general or a job slug)" for name in bad]
        return [Target(name) for name in dict.fromkeys(requested)], []
    targets = []
    if (workspace / "08-ats" / "general" / "resume.json").is_file():
        targets.append(Target("general"))
    jobs = workspace / "08-ats" / "jobs"
    if jobs.is_dir():
        targets += [Target(p.name) for p in sorted(jobs.iterdir()) if p.is_dir()]
    if not targets:
        return [], [f"nothing to render; run {ATS}"]
    return targets, []


def inputs(workspace: Path, targets: list[Target]) -> list[str]:
    """Every file render reads: each target's files, plus the shared files that exist."""
    workspace = Path(workspace)
    rels = []
    for target in targets:
        rels += [target.resume] + ([target.flags] if target.flags else [])
    rels += [rel for rel in (*SHARED_INPUTS, STORIES) if (workspace / rel).is_file()]
    return list(dict.fromkeys(rels))


def _owner(rel: str, targets: list[Target]) -> str:
    """The command that writes a file."""
    for target in targets:
        if rel in (target.resume, target.flags):
            return target.ats
    if rel.startswith("08-ats/"):
        return ATS
    if rel.startswith("decisions/"):
        return WIZARD
    if rel.startswith("03-profile/"):
        return "/resume-builder:import"
    return "/resume-builder:collect"  # 02-evidence/ and config.json


def _validate(workspace: Path, targets: list[Target]) -> list[Problem]:
    problems = []
    for target in targets:
        for rel in (target.resume, target.flags):
            if rel:
                problems += [Problem(target.name, line, _owner(rel, targets))
                             for line in validation.validate_paths(workspace, [rel])]
    for rel in SHARED_INPUTS:
        if (workspace / rel).is_file():
            problems += [Problem(SHARED, line, _owner(rel, targets))
                         for line in validation.validate_paths(workspace, [rel])]
    return problems


def _preconditions(workspace: Path, target: Target) -> list[Problem]:
    resume, _ = wsio.load(workspace, target.resume)
    name = resume.get("basics", {}).get("name") if isinstance(resume, dict) else None
    if isinstance(name, str) and name.strip():
        return []
    return [Problem(target.name, f"{target.resume}: basics.name is required to render",
                    f"{WIZARD} to add the name, then {target.ats}")]


def _source_fix(line: str, target: Target) -> str:
    detail = line[len(target.resume) + 2:]
    if detail.startswith("bullet "):
        return f"{target.ats}; if the bullet itself is wrong, /resume-builder:write first"
    if sources.LABEL_ERROR in detail:
        return f"{target.ats}, with basics.label set to the target role or the profile's label"
    if "highlights" in detail or sources.SCHEMA_ERROR in detail:
        return target.ats
    return f"{target.ats} to copy the profile value; if the profile is wrong, {WIZARD} first"


def _terms_fix(line: str, rel: str, target: Target) -> str:
    pointer = line[len(rel) + 1:].split(": contains denylisted term", 1)[0]
    if "/highlights/" in pointer or "/x-highlights/" in pointer or pointer == "/basics/summary":
        return ("/resume-builder:sanitize, then " + target.ats
                + "; for a false positive, an allowed term the engineer agrees to")
    return f"{WIZARD} to set a replacement value at {pointer}, then {target.ats}"


def _flags_fix(line: str, target: Target) -> str:
    if " is flagged (" in line:
        return "accept, revert or edit it at checkpoint 4 (/resume-builder:build resumes there)"
    return f"{target.ats} (re-runs the claim diff)"


def run(workspace: Path, targets: list[Target]) -> list[Problem]:
    """Run the gate. An empty list means every target may render."""
    workspace = Path(workspace)
    problems = _validate(workspace, targets)
    if problems:
        return problems

    for target in targets:
        problems += _preconditions(workspace, target)

    known = sources.load_known(workspace)
    problems += [Problem(SHARED, line, _owner(line.split(":", 1)[0], targets)) for line in known.errors]
    for target in targets:
        problems += [Problem(target.name, line, _source_fix(line, target))
                     for line in sources.check_file(workspace, target.resume, known)]

    patterns, errors = terms.load_patterns(workspace)
    if errors:
        problems += [Problem(SHARED, line, f"{WIZARD} to fix decisions/terms.json") for line in errors]
    else:
        for target in targets:
            problems += [Problem(target.name, line, _terms_fix(line, target.resume, target))
                         for line in terms.check_file(workspace, target.resume, patterns)]
        if (workspace / STORIES).is_file():
            problems += [Problem(SHARED, line, f"/resume-builder:sanitize to rewrite {STORIES}")
                         for line in terms.check_file(workspace, STORIES, patterns)]

    for target in targets:
        if target.is_job:
            problems += [Problem(target.name, line, _flags_fix(line, target))
                         for line in flags.check_job(workspace, target.name)]
    return problems
