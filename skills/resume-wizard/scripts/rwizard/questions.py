"""The open questions, in the order the wizard asks them.

1. moved:<entry>      an answer whose imported entry changed, or that has no anchor
2. metric-gone:<id>   a metric whose project is not in 04-projects/projects.json
3. term:<term>        a candidate or new term decisions/terms.json does not decide
4. fact:<pointer>     a fact field a tailored resume may copy that holds a denied term
5. profile:<pointer>  a missing profile field
6. metric:<project>   a project with metric_prompt and no metric

Each group can change the next: a moved answer changes which entry the profile
questions see, and a term decision can put a denied term in a fact field. Only
profile and metric questions can be skipped (except the name, which render needs).
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path

from rcore import facts
from rcore import profile as core_profile
from rcore import terms as core_terms

from . import metrics as metrics_mod
from .common import (CANDIDATES, METRICS, NEW_TERMS, PROFILE, PROJECT_DECISIONS, PROJECTS, SOURCE, WIZARD_PROFILE,
                     load, load_terms, patterns_for, plural, shorten)
from .profile import Moved, moved_answers
from .state import State, load_state


@dataclass
class Question:
    key: str
    text: str
    answer: str
    details: list[str] = field(default_factory=list)
    skippable: bool = False
    skipped: bool = False


@dataclass
class Context:
    """Everything the questions are computed from, validated."""
    imported: dict
    wizard: dict
    state: State
    entries: list[dict]
    metrics: list[dict]
    decisions: list[dict]
    projects: list[dict] | None
    candidates: list[dict] | None
    new_terms: list[dict]
    source_format: str | None
    has_profile: bool

    @property
    def effective(self) -> dict:
        return core_profile.overlay(self.imported, self.wizard)


def context(workspace: Path) -> Context:
    """Read and validate every file the wizard reads. Raises WizardError."""
    imported = load(workspace, PROFILE)
    source = load(workspace, SOURCE)
    return Context(
        imported=imported if imported is not None else {},
        wizard=load(workspace, WIZARD_PROFILE, {}),
        state=load_state(workspace),
        entries=load_terms(workspace),
        metrics=load(workspace, METRICS, []),
        decisions=load(workspace, PROJECT_DECISIONS, []),
        projects=load(workspace, PROJECTS),
        candidates=load(workspace, CANDIDATES),
        new_terms=load(workspace, NEW_TERMS, []),
        source_format=source.get("format") if isinstance(source, dict) else None,
        has_profile=imported is not None,
    )


def _moved(ctx: Context, found: list[Moved]) -> list[Question]:
    questions = []
    for m in found:
        array = m.entry.rsplit("/", 1)[0]
        options = []
        if m.suggest is not None:
            why = (f"'{core_profile.describe(m.section, m.was)}' is now {array}/{m.suggest}" if m.was is not None
                   else "a new entry again")
            options.append(f"answer.py move {m.entry} {array}/{m.suggest} ({why})")
        options += [f"answer.py confirm {m.entry}", f"answer.py unset {m.entry}"]
        answer = ", ".join(options[:-1]) + " or " + options[-1]
        questions.append(Question(f"moved:{m.entry}", m.describe(), answer))
    return questions


def _metrics_gone(ctx: Context) -> list[Question]:
    if ctx.projects is None:
        return []
    current = {p["id"] for p in ctx.projects}
    questions = []
    for metric in ctx.metrics:
        if metric["project_id"] in current:
            continue
        text = f"{shorten(metric['statement'])!r}: {metrics_mod.why_gone(metric['project_id'], ctx.decisions)}"
        near = metrics_mod.closest(metric, ctx.projects)
        if near is not None:
            project, shared, size = near
            text += f"; closest is {project['id']} {project['internal_name']!r} ({shared} of its {size} items)"
        commands = f"answer.py relink-metric {metric['id']} PJ or answer.py remove-metric {metric['id']}"
        questions.append(Question(f"metric-gone:{metric['id']}", text, commands))
    return questions


def _places(found: list[str]) -> str:
    shown = ", ".join(found[:3]) + (f" and {len(found) - 3} more" if len(found) > 3 else "")
    return f"in {plural(len(found), 'place')}: {shown}" if found else "found nowhere now"


def _terms(ctx: Context) -> list[Question]:
    decided = {core_terms.key(e["term"]) for e in ctx.entries}
    seen: set[str] = set()
    questions = []
    for proposals, origin in ((ctx.candidates or [], ""), (ctx.new_terms, "; a new term from 07-sanitized")):
        for proposal in proposals:
            key = core_terms.key(proposal["term"])
            if key in decided or key in seen:
                continue
            seen.add(key)
            term = shlex.quote(proposal["term"])
            questions.append(Question(
                f"term:{proposal['term']}",
                f"{proposal['kind']}, proposed {proposal['proposed_replacement']!r}; "
                f"{_places(proposal['found_in'])}{origin}",
                f"answer.py term {term} --replacement TEXT or answer.py term {term} --allow"))
    return questions


def fact_hits(effective: dict, entries: list[dict]) -> tuple[list[tuple[str, str, list[str]]], list[str]]:
    """(pointer, value, denied terms) for fact fields holding a denied term, and notes for keywords."""
    patterns = patterns_for(entries)
    hits, notes = [], []
    for pointer, value in facts.fact_values(effective):
        found = core_terms.terms_in(value, patterns)
        if not found:
            continue
        names = ", ".join(repr(t) for t in found)
        if "/keywords/" in pointer:
            notes.append(f"{pointer} {value!r} holds the denied term {names}; a keyword cannot be replaced, so "
                         "resume-ats leaves it out")
        else:
            hits.append((pointer, value, found))
    return hits, notes


def _facts(ctx: Context, hits) -> list[Question]:
    return [Question(f"fact:{pointer}",
                     f"{value!r} holds the denied term {', '.join(repr(t) for t in found)}",
                     f"answer.py profile {pointer} VALUE")
            for pointer, value, found in hits]


WORK = {"name": "employer", "position": "title", "startDate": "start date",
        "endDate": "end date (skip it if the job is current)"}
EDUCATION = {"institution": "school", "studyType": "degree (BS, MS, ...)", "area": "field of study",
             "endDate": "graduation date"}
CERTIFICATES = {"name": "name", "issuer": "issuer", "date": "date"}


def _profile(ctx: Context) -> list[Question]:
    effective = ctx.effective
    basics = effective.get("basics") if isinstance(effective.get("basics"), dict) else {}
    found: list[Question] = []

    def ask(pointer: str, text: str, answer: str | None = None, skippable: bool = True) -> None:
        answer = answer or f"answer.py profile {pointer} VALUE"
        key = f"profile:{pointer}"
        if skippable:
            answer += f" or answer.py skip {key}"
        found.append(Question(key, text, answer, skippable=skippable,
                              skipped=skippable and ctx.state.is_skipped(key, ctx.imported)))

    if not basics.get("name"):
        ask("/basics/name", "full name (the resume cannot render without one)", skippable=False)
    if not basics.get("email"):
        ask("/basics/email", "email address")
    if not basics.get("phone"):
        ask("/basics/phone", "phone number")
    location = basics.get("location") if isinstance(basics.get("location"), dict) else {}
    if not location.get("city"):
        ask("/basics/location", "location: city, and region or country code",
            "answer.py profile /basics/location/city VALUE (and /basics/location/region, "
            "/basics/location/countryCode)")
    if not basics.get("profiles") and not basics.get("url"):
        ask("/basics/profiles", "links: a LinkedIn or GitHub profile, or a personal site",
            "answer.py profile /basics/profiles/-/network VALUE, then /basics/profiles/N/username and "
            "/basics/profiles/N/url; or answer.py profile /basics/url VALUE")

    def entries(section: str) -> list:
        value = effective.get(section)
        return [e for e in value if isinstance(e, dict)] if isinstance(value, list) else []

    for i, job in enumerate(entries("work")):
        label = core_profile.describe("work", job)
        for name in ("name", "position", "startDate") + (("endDate",) if ctx.source_format == "json" else ()):
            if not job.get(name):
                ask(f"/work/{i}/{name}", f"{WORK[name]} of /work/{i} '{label}'")
    schools = entries("education")
    if not schools:
        ask("/education", "education: a degree, school or bootcamp",
            "answer.py profile /education/-/institution VALUE, then /education/N/studyType, /education/N/area "
            "and /education/N/endDate")
    for i, school in enumerate(schools):
        label = core_profile.describe("education", school)
        for name, what in EDUCATION.items():
            if not school.get(name):
                ask(f"/education/{i}/{name}", f"{what} of /education/{i} '{label}'")
    certificates = entries("certificates")
    if not certificates:
        ask("/certificates", "certifications",
            "answer.py profile /certificates/-/name VALUE, then /certificates/N/issuer and /certificates/N/date")
    for i, cert in enumerate(certificates):
        label = core_profile.describe("certificates", cert)
        for name, what in CERTIFICATES.items():
            if not cert.get(name):
                ask(f"/certificates/{i}/{name}", f"{what} of /certificates/{i} '{label}'")
    return found


def _metric_prompts(ctx: Context) -> list[Question]:
    if ctx.projects is None:
        return []
    with_metric = {m["project_id"] for m in ctx.metrics}
    questions = []
    for project in sorted(ctx.projects, key=lambda p: p["rank"]):
        if not project["metric_prompt"] or project["id"] in with_metric:
            continue
        key = f"metric:{project['id']}"
        details = [project["summary"]] if project["summary"] else []
        if project["rank_reasons"]:
            details.append(f"reasons: {'; '.join(project['rank_reasons'])}")
        questions.append(Question(
            key,
            f"rank {project['rank']} {project['internal_name']!r} [{project['role']}, {project['scope']}, "
            f"{project['start']} to {project['end']}]",
            f"answer.py metric {project['id']} --value N --unit UNIT --statement TEXT or answer.py skip {key}",
            details, skippable=True, skipped=ctx.state.is_skipped(key, ctx.imported)))
    return questions


def compute(ctx: Context) -> tuple[list[Question], list[str]]:
    """(questions in asking order, skipped ones included and marked; note: and notice: lines)."""
    notes = []
    if not ctx.has_profile:
        notes.append(f"{PROFILE} not found: profile questions use {WIZARD_PROFILE} only; "
                     "run /resume-builder:import to import a resume")
    if ctx.projects is None:
        notes.append(f"{PROJECTS} not found: no metric questions; run /resume-builder:analyze")
    if ctx.candidates is None:
        notes.append(f"{CANDIDATES} not found: no term questions from the scan; run the sanitize scan "
                     "(/resume-builder:sanitize)")
    hits, keyword_notes = fact_hits(ctx.effective, ctx.entries)
    notes = [f"note: {line}" for line in notes + keyword_notes] + core_terms.allowed_notices(ctx.entries)
    questions = (_moved(ctx, moved_answers(ctx.imported, ctx.wizard, ctx.state)) + _metrics_gone(ctx)
                 + _terms(ctx) + _facts(ctx, hits) + _profile(ctx) + _metric_prompts(ctx))
    return questions, notes


def open_questions(workspace: Path) -> list[Question]:
    questions, _ = compute(context(workspace))
    return [q for q in questions if not q.skipped]

