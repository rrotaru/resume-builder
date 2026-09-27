"""Checkpoint 4: the final review's sections and its open items."""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from rcore import facts, profile, terms, wsio

from . import jobs
from .common import (BULLETS, BULLETS_BEFORE, NEW_TERMS, PROFILE, SANITIZED_PROFILE, STORIES, STORIES_BEFORE,
                     BuildError, load, load_text, patterns, term_entries)

PLACES_SHOWN = 3


@dataclass
class Fact:
    pointer: str
    value: str
    term: str

    @property
    def is_keyword(self) -> bool:
        return "/keywords/" in self.pointer


@dataclass
class Version:
    name: str
    used: int
    total: int
    report: dict
    left_out: list[tuple[str, str, str]]           # bullet ID, reason, text
    flags: list[jobs.FlagState] | None = None      # None for the general resume


@dataclass
class Review:
    stages: list[tuple[str, str, str]] = field(default_factory=list)   # stage, state, note
    new_terms: list[dict] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    bullets: list[tuple[str, str, str]] = field(default_factory=list)  # ID, was, now
    bullet_total: int = 0
    stories: list[tuple[int, str | None, str | None]] = field(default_factory=list)
    prose: list[tuple[str, str, str]] = field(default_factory=list)    # pointer, was, now
    facts: list[Fact] = field(default_factory=list)
    versions: list[Version] = field(default_factory=list)
    items: list[str] = field(default_factory=list)


# The parts progress.py also counts -----------------------------------------------------------

def undecided_new_terms(workspace: Path, entries: list[dict]) -> list[dict]:
    """Terms in 07-sanitized/new-terms.json that decisions/terms.json does not decide."""
    decided = {terms.key(e["term"]) for e in entries}
    return [t for t in load(workspace, NEW_TERMS, []) if terms.key(t["term"]) not in decided]


def denied_facts(workspace: Path, entries: list[dict]) -> list[Fact]:
    """Fact fields of the effective profile a tailored resume may copy that hold a denied term."""
    compiled = patterns(entries)
    return [Fact(pointer, value, term) for pointer, value in facts.fact_values(profile.effective_profile(workspace))
            for term in terms.terms_in(value, compiled)]


def flag_items(workspace: Path) -> list[tuple[str, list[jobs.FlagState]]]:
    """Each committed job with the state of its flags."""
    attestations = jobs.load_attestations(workspace)
    found = []
    for slug in jobs.committed_versions(workspace):
        if slug != jobs.GENERAL:
            found.append((slug, jobs.flag_states(jobs.load_job(workspace, slug), attestations)))
    return found


def term_item(term: dict) -> str:
    return (f"new term {term['term']!r}: decide it with the wizard (resume-wizard), then run sanitize apply and ats "
            "again")


def fact_item(fact: Fact) -> str:
    return (f"{fact.pointer} {fact.value!r} holds the denied term {fact.term!r}: set a replacement value with the "
            "wizard (resume-wizard, a fact: question), then run write, sanitize apply and ats again")


def open_items(workspace: Path) -> list[str]:
    """The open items that are not about stages: new terms, facts holding a denied term and open flags."""
    entries = term_entries(workspace)
    items = [term_item(t) for t in undecided_new_terms(workspace, entries)]
    items += [fact_item(f) for f in denied_facts(workspace, entries) if not f.is_keyword]
    for slug, states in flag_items(workspace):
        items += [jobs.fix(slug, s) for s in states if s.is_open]
    return items


# The whole review ----------------------------------------------------------------------------

def _changed_bullets(workspace: Path) -> tuple[list[tuple[str, str, str]], int]:
    before = {b["id"]: b["text"] for b in load(workspace, BULLETS_BEFORE, [])}
    after = load(workspace, BULLETS, [])
    return [(b["id"], before[b["id"]], b["text"]) for b in after
            if b["id"] in before and before[b["id"]] != b["text"]], len(after)


def _changed_story_lines(workspace: Path) -> list[tuple[int, str | None, str | None]]:
    before, after = load_text(workspace, STORIES_BEFORE), load_text(workspace, STORIES)
    if before is None or after is None:
        return []
    old, new = before.splitlines(), after.splitlines()
    changed = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        for k in range(max(i2 - i1, j2 - j1)):
            was = old[i1 + k] if i1 + k < i2 else None
            now = new[j1 + k] if j1 + k < j2 else None
            changed.append((j1 + k + 1 if now is not None else i1 + k + 1, was, now))
    return changed


def _changed_prose(workspace: Path) -> list[tuple[str, str, str]]:
    before, after = load(workspace, PROFILE, {}), load(workspace, SANITIZED_PROFILE, {})
    changed = []
    for pointer, now in wsio.iter_strings(after):
        try:
            was = wsio.resolve_pointer(before, pointer)
        except KeyError:
            continue
        if was != now:
            changed.append((pointer, was, now))
    return changed


def _version(workspace: Path, name: str, total: dict[str, str], attestations: list[dict]) -> Version:
    base = jobs.folder(name)
    report = load(workspace, f"{base}/report.json")
    resume = load(workspace, f"{base}/resume.json")
    if report is None or resume is None:
        raise BuildError(f"{base}/: resume.json or report.json is missing; commit 08-ats again with resume-ats")
    used = sum(1 for _ in wsio.resume_highlights(resume))
    left_out = [(b["bullet_id"], b["reason"], total.get(b["bullet_id"], "")) for b in report["left_out"]]
    states = None if name == jobs.GENERAL else jobs.flag_states(jobs.load_job(workspace, name), attestations)
    return Version(name, used, len(total), report, left_out, states)


def review(workspace: Path, steps) -> Review:
    """Checkpoint 4's material. steps are progress.py's steps. Raises BuildError."""
    workspace = Path(workspace)
    versions = jobs.committed_versions(workspace)
    if not (workspace / "08-ats" / "_stage.json").is_file() or not versions:
        raise BuildError("nothing to review: 08-ats is not committed; build it with resume-ats first (progress.py "
                         "names the next step)")
    entries = term_entries(workspace)
    found = Review()
    for step in steps:
        stage = STAGE_FOR.get(step.name)
        if stage and step.state not in ("fresh", "none"):
            found.stages.append((stage, step.state, step.note))
            found.items.append(f"{stage} is {step.state}: finish the steps progress.py names first")
    found.new_terms = undecided_new_terms(workspace, entries)
    found.items += [term_item(t) for t in found.new_terms]
    found.notices = terms.allowed_notices(workspace)
    found.bullets, found.bullet_total = _changed_bullets(workspace)
    found.stories = _changed_story_lines(workspace)
    found.prose = _changed_prose(workspace)
    found.facts = denied_facts(workspace, entries)
    found.items += [fact_item(f) for f in found.facts if not f.is_keyword]
    texts = {b["id"]: b["text"] for b in load(workspace, BULLETS, [])}
    attestations = jobs.load_attestations(workspace)
    for name in versions:
        version = _version(workspace, name, texts, attestations)
        found.versions.append(version)
        found.items += [jobs.fix(name, s) for s in version.flags or [] if s.is_open]
    return found


# The stage behind each step the review looks at (not render: the review comes before it).
STAGE_FOR = {"collect": "02-evidence", "import": "03-profile", "analyze": "04-projects", "scan": "05-terms",
             "write": "06-bullets", "apply": "07-sanitized", "ats": "08-ats"}
