"""The model's bullets (06-bullets.tmp/bullets.json): checks, IDs and each bullet's place.

A bullet cites evidence only of its own project, or a performance review. It
cites a metric only of its own project, and then its form is xyz_quantified
and its text states the metric's value. Every number in its text appears in
its sources. It names one place on the resume: work_ref, the job it goes under
(for a project bullet, a job whose dates overlap the project's months), or a
pointer into a profile projects entry. Together the bullets cover every
project, every metric of a current project, and every highlight of the
imported resume. IDs are assigned here: a bullet whose text is unchanged since
the last committed run keeps its ID.
"""
from __future__ import annotations

import copy
import re

from rcore import numbers, schema, sources

from .common import DRAFT, shorten
from .material import Material, is_review, pointer_place, project_span, x_field

FIELDS = ("id", "project_id", "work_ref", "text", "form", "sources")
FIX = (f"fix: edit {DRAFT}: cite only a project's own evidence, performance reviews, its metrics and the "
       "profile; write only numbers the sources state; give each bullet its place; and cover every project, "
       "metric and resume highlight (see SKILL.md)")
_NUMBERED = re.compile(r"^b_([0-9]+)$")


def draft_schema() -> dict:
    """bullets.schema.json with id optional and unchecked: write.py assigns IDs."""
    spec = copy.deepcopy(schema.load_schema("bullets"))
    spec["items"]["required"] = [key for key in spec["items"]["required"] if key != "id"]
    spec["items"]["properties"]["id"] = {}
    return spec


def place(bullet: dict) -> str | None:
    """Where a checked bullet goes: '/work/0', '/projects/0', or None when it has no place."""
    if bullet["work_ref"] is not None:
        return f"/work/{bullet['work_ref']}"
    for ref in bullet["sources"]:
        found = pointer_place(ref)
        if found and found[0] == "projects":
            return f"/projects/{found[1]}"
    return None


def _source_problems(where: str, bullet: dict, material: Material) -> list[str]:
    problems, seen = [], set()
    project = material.by_id.get(bullet["project_id"])
    for k, ref in enumerate(bullet["sources"]):
        at = f"{where}/sources/{k}"
        if ref in seen:
            problems.append(f"{at}: {ref} is listed twice")
            continue
        seen.add(ref)
        reason = sources.source_error(ref, material.known)
        if reason:
            problems.append(f"{at}: {ref}: {reason}")
            continue
        field = x_field(ref)
        if field:
            problems.append(f"{at}: {ref} points into {field}, which is not resume text")
        elif ref.startswith("ev_"):
            problems += _evidence_problem(at, ref, bullet, project, material)
        elif ref.startswith("metric:"):
            problems += _metric_problem(at, where, ref, bullet, material)
    if project is not None and not any(ref in project["evidence_ids"] for ref in bullet["sources"]):
        problems.append(f"{where}/sources: cites none of {project['id']}'s evidence; a project bullet cites at "
                        "least one item of its project")
    return problems


def _evidence_problem(at: str, ref: str, bullet: dict, project: dict | None, material: Material) -> list[str]:
    if is_review(material.evidence[ref]) or (project is not None and ref in project["evidence_ids"]):
        return []
    owner = material.owner.get(ref)
    if owner is None:
        return [f"{at}: {ref} is in no project and is not a performance review"]
    if bullet["project_id"] is None:
        return [f"{at}: {ref} is evidence of {owner}; a bullet without a project cites only performance reviews "
                "and the profile"]
    return [f"{at}: {ref} is evidence of {owner}, not of this bullet's project {bullet['project_id']}"]


def _metric_problem(at: str, where: str, ref: str, bullet: dict, material: Material) -> list[str]:
    metric = material.metric(ref[len("metric:"):])
    if bullet["project_id"] is None:
        return [f"{at}: {ref}: a bullet without a project cannot cite a metric"]
    if metric["project_id"] != bullet["project_id"]:
        gone = "" if metric["project_id"] in material.by_id else \
            " (not a project in 04-projects/projects.json; the wizard re-links or removes it)"
        return [f"{at}: {ref} belongs to {metric['project_id']}{gone}, not to this bullet's project "
                f"{bullet['project_id']}"]
    if not numbers.states_value(bullet["text"], metric["value"]):
        return [f"{where}/text: does not state {metric['value']}, the value of {ref}"]
    return []


def _form_problems(where: str, bullet: dict) -> list[str]:
    cites_metric = any(ref.startswith("metric:") for ref in bullet["sources"])
    if bullet["form"] == "xyz_quantified" and not cites_metric:
        return [f"{where}/form: xyz_quantified needs a metric: source; without one the form is xyz"]
    if bullet["form"] == "xyz" and cites_metric:
        return [f"{where}/form: the bullet cites a metric, so its form is xyz_quantified"]
    return []


def _number_problems(where: str, bullet: dict, material: Material) -> list[str]:
    texts = [t for ref in bullet["sources"] for t in material.source_texts(ref)]
    return [f"{where}/text: the number '{n}' is in none of its sources"
            for n in numbers.unsupported(bullet["text"], texts)]


def _place_problems(where: str, bullet: dict, material: Material) -> list[str]:
    problems = []
    work_ref, project = bullet["work_ref"], material.by_id.get(bullet["project_id"])
    cited = [(k, ref, pointer_place(ref)) for k, ref in enumerate(bullet["sources"])]
    jobs = [(k, ref, found[1]) for k, ref, found in cited if found and found[0] == "work"]
    profile_projects = [(k, ref, found[1]) for k, ref, found in cited if found and found[0] == "projects"]
    if work_ref is not None and work_ref >= len(material.jobs):
        count = f"it has {len(material.jobs)}" if material.jobs else "the profile has no jobs"
        problems.append(f"{where}/work_ref: {work_ref} is not a job in the profile ({count})")
        return problems
    if profile_projects:
        first_k, _, first = profile_projects[0]
        for k, ref, i in profile_projects[1:]:
            if i != first:
                problems.append(f"{where}/sources/{k}: {ref} is in /projects/{i}, but /sources/{first_k} is in "
                                f"/projects/{first}; a bullet goes in one place")
        for k, ref, i in jobs:
            problems.append(f"{where}/sources/{k}: {ref} is in /work/{i}, but the bullet cites the profile project "
                            f"/projects/{first}; a bullet goes in one place")
        if work_ref is not None:
            problems.append(f"{where}/work_ref: must be null: the bullet cites the profile project /projects/{first}")
        return problems
    for k, ref, i in jobs:
        if work_ref != i:
            problems.append(f"{where}/sources/{k}: {ref} is in /work/{i}, so work_ref must be {i}")
    if project is None:
        if bullet["project_id"] is None and work_ref is None and not jobs:
            problems.append(f"{where}: a bullet without a project needs a place: a work_ref, or a resume: pointer "
                            "into /projects/<i>")
        return problems
    overlapping = material.jobs_for(project)
    choices = ", ".join(f"/work/{i}" for i in overlapping)
    what = f"{project['id']} ({project_span(project)})"
    if work_ref is None:
        if overlapping:
            problems.append(f"{where}/work_ref: null, but {choices} overlaps {what}; set work_ref to "
                            f"{'it' if len(overlapping) == 1 else 'one of them'}")
    elif work_ref not in overlapping:
        use = f"use {choices}" if overlapping else "no job overlaps it: use null"
        problems.append(f"{where}/work_ref: {material.job_label(work_ref)} does not overlap {what}; {use}")
    return problems


def _completeness(bullets: list[dict], material: Material) -> list[str]:
    cited = {ref for b in bullets for ref in b["sources"]}
    with_bullets = {b["project_id"] for b in bullets}
    problems = [f"{DRAFT}: {p['id']} {shorten(p['internal_name'])!r} has no bullet"
                for p in material.projects if p["id"] not in with_bullets]
    problems += [f"{DRAFT}: metric:{m['id']} ({m['project_id']}) is cited by no bullet"
                 for m in material.metrics if m["project_id"] in material.by_id and f"metric:{m['id']}" not in cited]
    problems += [f"{DRAFT}: {ref} is cited by no bullet" for ref in material.required_pointers() if ref not in cited]
    return problems


def check(draft, material: Material) -> list[str]:
    """Problems with the model's bullets, one line each."""
    errors = schema.validate(draft, draft_schema())
    if errors:
        return [f"{DRAFT}: {e}" for e in errors]
    problems, texts = [], {}
    for b, bullet in enumerate(draft):
        where, text = f"{DRAFT}: /{b}", bullet["text"]
        if text.splitlines() != [text]:
            problems.append(f"{where}/text: holds a line break; a bullet is one line")
        if text != text.strip():
            problems.append(f"{where}/text: begins or ends with a space")
        if text in texts:
            problems.append(f"{where}/text: same text as /{texts[text]}")
        texts.setdefault(text, b)
        if not bullet["sources"]:
            problems.append(f"{where}/sources: a bullet needs at least one source")
        if bullet["project_id"] is not None and bullet["project_id"] not in material.by_id:
            problems.append(f"{where}/project_id: {bullet['project_id']} is not a project in "
                            "04-projects/projects.json")
        problems += _source_problems(where, bullet, material)
        problems += _form_problems(where, bullet)
        problems += _number_problems(where, bullet, material)
        problems += _place_problems(where, bullet, material)
    return problems + _completeness(draft, material)


def assign_ids(draft: list[dict], previous: list[dict]) -> list[dict]:
    """The checked bullets as written to bullets.json: IDs assigned, sources sorted, keys in schema order.

    A bullet whose text equals a previous bullet's takes its ID (each once, in
    file order). The others get b_<n>, counting on from the highest previous number.
    """
    by_text: dict[str, str] = {}
    for bullet in previous:
        by_text.setdefault(bullet["text"], bullet["id"])
    taken: set[str] = set()
    ids: list[str | None] = []
    for bullet in draft:
        old = by_text.get(bullet["text"])
        ids.append(old if old is not None and old not in taken else None)
        if ids[-1] is not None:
            taken.add(old)
    top = max((int(m.group(1)) for m in (_NUMBERED.match(b["id"]) for b in previous) if m), default=0)
    records = []
    for bullet, bullet_id in zip(draft, ids):
        if bullet_id is None:
            top += 1
            bullet_id = f"b_{top}"
        record = {**bullet, "id": bullet_id, "sources": sorted(bullet["sources"])}
        records.append({key: record[key] for key in FIELDS})
    return records
