"""The committed versions in 08-ats/, each job's flags, and the attestations that accept them.

A flag's status follows the rules check_flags.py applies (rcore.flags.check_job),
so an open flag here is exactly a line that render's flags check prints.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from rcore import flags, ids, wsio

from .common import ATS, ATTESTATIONS, BuildError, load

GENERAL = "general"
SUMMARY = flags.SUMMARY_ID
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ACCEPTED = {"accept": "accepted", "edit": "edited"}


def folder(version: str) -> str:
    return f"{ATS}/{GENERAL}" if version == GENERAL else f"{ATS}/jobs/{version}"


def committed_versions(workspace: Path) -> list[str]:
    """general, when committed, then each committed job in slug order."""
    workspace = Path(workspace)
    found = [GENERAL] if (workspace / ATS / GENERAL / "resume.json").is_file() else []
    jobs = workspace / ATS / "jobs"
    if jobs.is_dir():
        found += sorted(p.name for p in jobs.iterdir() if p.is_dir())
    return found


def load_attestations(workspace: Path) -> list[dict]:
    return load(workspace, ATTESTATIONS, [])


@dataclass
class Job:
    """A committed job version: its resume, its claim diff and the texts the flags check reads."""
    slug: str
    resume: dict
    flags: dict
    texts: dict[str, str] = field(default_factory=dict)  # bullet_id (or summary) -> text, summary first

    def text_hash(self, bullet_id: str) -> str | None:
        text = self.texts.get(bullet_id)
        return None if text is None else ids.text_sha256(text)

    def flag(self, bullet_id: str) -> dict | None:
        return next((f for f in self.flags["flags"] if f["bullet_id"] == bullet_id), None)


def load_job(workspace: Path, slug: str) -> Job:
    """A committed job version, validated. Raises BuildError."""
    if not SLUG.fullmatch(slug) or slug == GENERAL:
        raise BuildError(f"{slug!r} is not a job slug (lower-case letters, digits and '-', not 'general')")
    base = folder(slug)
    missing = [f"{base}/{name}" for name in ("resume.json", "flags.json") if not (Path(workspace) / base / name).is_file()]
    if missing:
        raise BuildError([f"{rel}: not found" for rel in missing]
                         + [f"{slug} is not a committed job version; draft and commit it with resume-ats"])
    resume = load(workspace, f"{base}/resume.json")
    claim_diff = load(workspace, f"{base}/flags.json")
    texts = {}
    summary = resume.get("basics", {}).get("summary")
    if isinstance(summary, str):
        texts[SUMMARY] = summary
    for _, highlight in wsio.resume_highlights(resume):
        texts[highlight["bullet_id"]] = highlight["text"]  # the last of a repeated ID, as check_flags.py reads it
    return Job(slug, resume, claim_diff, texts)


@dataclass
class FlagState:
    bullet_id: str
    status: str             # accepted, edited, flagged, changed after the claim diff, not in resume.json, used twice
    text: str | None
    reasons: list[str]
    is_open: bool


def attested(attestations: list[dict], slug: str, bullet_id: str, digest: str | None) -> dict | None:
    return next((a for a in attestations if (a["job_slug"], a["bullet_id"], a["text_sha256"]) ==
                 (slug, bullet_id, digest)), None)


def flag_states(job: Job, attestations: list[dict]) -> list[FlagState]:
    """Each flagged bullet and each problem check_flags.py reports, in its order: used twice, gone, then texts."""
    states = []
    counts = Counter(h["bullet_id"] for _, h in wsio.resume_highlights(job.resume))
    states += [FlagState(b, "used twice", job.texts.get(b), [], True) for b, n in counts.items() if n > 1]
    flagged = {f["bullet_id"]: f for f in job.flags["flags"]}
    checked = job.flags["checked"]
    states += [FlagState(b, "not in resume.json", None, flagged[b]["reasons"] if b in flagged else [], True)
               for b in sorted(set(flagged) | set(checked)) if b not in job.texts]
    for bullet_id, text in job.texts.items():
        digest = ids.text_sha256(text)
        flag = flagged.get(bullet_id)
        reasons = flag["reasons"] if flag else []
        record = attested(attestations, job.slug, bullet_id, digest)
        if record is not None:
            if flag is not None:
                states.append(FlagState(bullet_id, ACCEPTED[record["action"]], text, reasons, False))
        elif flag is not None and flag["text_sha256"] == digest:
            states.append(FlagState(bullet_id, "flagged", text, reasons, True))
        elif flag is None and checked.get(bullet_id) == digest:
            continue
        else:
            states.append(FlagState(bullet_id, "changed after the claim diff", text, reasons, True))
    return states


def fix(slug: str, state: FlagState) -> str:
    """The open item for an open flag state, with what resolves it."""
    recheck = "re-check it: stage.py begin 08-ats --from-current, then ats.py --commit (resume-ats)"
    if state.status == "flagged":
        return (f"{slug} {state.bullet_id} is flagged: accept it (attest.py accept {slug} {state.bullet_id}), "
                f"or revert or edit it (resume-ats: ats.py --revise {slug})")
    if state.status == "used twice":
        return f"{slug} {state.bullet_id} is used twice in resume.json: draft it again (resume-ats: ats.py --job {slug})"
    return f"{slug} {state.bullet_id} {state.status}: {recheck}"
