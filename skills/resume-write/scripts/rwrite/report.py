"""What write.py prints: the material to write about, warnings and notes, and the committed bullets."""
from __future__ import annotations

from collections import Counter

from rcore.profile import describe

from .common import METRICS, PROFILE, PROJECTS, one_line, plural, shorten
from .material import Material, project_span, span
from .stories import told


def header(material: Material) -> str:
    items = sum(1 for p in material.projects for e in p["evidence_ids"] if e in material.evidence)
    metrics = sum(1 for m in material.metrics if m["project_id"] in material.by_id)
    return (f"write: {plural(len(material.projects), 'project')} "
            f"({plural(len(told(material.projects)), 'story', 'stories')}), "
            f"{plural(items, 'evidence item')} in projects, {plural(len(material.reviews), 'performance review')}, "
            f"{plural(metrics, 'metric')}; profile: {plural(len(material.jobs), 'job')}, "
            f"{plural(len(material.profile_projects), 'project')}")


def _imported(material: Material, section: str, index: int) -> dict:
    entries = (material.inputs.profile or {}).get(section)
    entry = entries[index] if isinstance(entries, list) and index < len(entries) else None
    return entry if isinstance(entry, dict) else {}


def _texts(material: Material, section: str, index: int, fields: tuple[str, ...]) -> list[str]:
    """The resume text of an imported entry: its highlights, else the first of fields it has."""
    entry = _imported(material, section, index)
    highlights = entry.get("highlights")
    if isinstance(highlights, list) and highlights:
        return [f"    resume:/{section}/{index}/highlights/{j}  {one_line(text)}"
                for j, text in enumerate(highlights) if isinstance(text, str)]
    for name in fields:
        if isinstance(entry.get(name), str) and entry[name].strip():
            return [f"    resume:/{section}/{index}/{name}  {one_line(entry[name])}"]
    return []


def jobs(material: Material) -> list[str]:
    if not material.jobs:
        return ["jobs: none in the profile"]
    lines = ["jobs:"]
    for i, job in enumerate(material.jobs):
        projects = [p["id"] for p in material.projects if i in material.jobs_for(p)]
        lines.append(f"  /work/{i}  {describe('work', job)}  {span(job) or 'no dates'}  "
                     f"projects: {', '.join(projects) or 'none'}")
        lines += _texts(material, "work", i, ("summary",))
    return lines


def profile_projects(material: Material) -> list[str]:
    if not material.profile_projects:
        return []
    lines = ["profile projects:"]
    for i, entry in enumerate(material.profile_projects):
        dates = span(entry)
        lines.append(f"  /projects/{i}  {describe('projects', entry)}" + (f"  {dates}" if dates else ""))
        lines += _texts(material, "projects", i, ("description",))
    return lines


def _job_line(material: Material, project: dict) -> str:
    overlapping = material.jobs_for(project)
    if not overlapping:
        return "    job: none in the profile"
    if len(overlapping) == 1:
        return f"    job: /work/{overlapping[0]}"
    return f"    jobs: {' or '.join(f'/work/{i}' for i in overlapping)} (it overlaps each; choose one)"


def projects(material: Material) -> list[str]:
    lines = ["projects:"] if material.projects else ["projects: none"]
    for p in material.projects:
        marks = "  story" if p["metric_prompt"] else ""
        lines.append(f"{p['rank']:>2}. {p['id']}  {p['internal_name']}  "
                     f"[{p['role']}, {p['scope']}, {project_span(p)}]{marks}")
        lines.append(f"    {p['summary'] or '(no summary)'}")
        if p["rank_reasons"]:
            lines.append(f"    reasons: {'; '.join(p['rank_reasons'])}")
        lines.append(_job_line(material, p))
        for m in material.metrics_of(p["id"]):
            lines.append(f"    metric:{m['id']}  {m['statement']}  (value {m['value']}, unit {m['unit']})")
        for item in material.items_of(p):
            evidence_id = item["id"]
            lines.append(f"    {evidence_id}  {item['kind']}, {item['engineer_role']}, {item['created_at'][:10]}  "
                         f"{one_line(item['title'])}")
            if item.get("excerpt"):
                lines.append(f"      {one_line(item['excerpt'])}")
    return lines


def reviews(material: Material) -> list[str]:
    if not material.reviews:
        return ["performance reviews: none"]
    return ["performance reviews:"] + [
        f"  {r['id']}  {r['created_at'][:10]}  {one_line(r['title'])}  "
        + (f"full text at {r['raw_ref']}" if r.get("raw_ref") else "no raw record: only its excerpt")
        for r in material.reviews]


def gone_metric_warnings(material: Material) -> list[str]:
    return [f"{METRICS} {m['id']}: {m['project_id']} is not a project in {PROJECTS}; the wizard re-links or "
            "removes it" for m in material.gone_metrics()]


def begin_warnings(material: Material) -> list[str]:
    warnings = []
    if material.inputs.profile is None:
        warnings.append(f"{PROFILE} not found: no jobs or profile projects to put bullets under; "
                        "run /resume-builder:import")
    warnings += gone_metric_warnings(material)
    warnings += [f"{p['id']} {shorten(p['internal_name'])!r} ({project_span(p)}) falls in no job of the profile; "
                 "resume-ats cannot place its bullets until the job is added with /resume-builder:wizard"
                 for p in material.homeless()]
    return warnings + material.raw_warnings


def notes(material: Material) -> list[str]:
    return [f"{p['id']} {shorten(p['internal_name'])!r} has a metric prompt and no metric in {METRICS}: its "
            "bullets use the xyz form; if the engineer has not been through the wizard, run /resume-builder:wizard "
            "first" for p in told(material.projects) if not material.metrics_of(p["id"])]


def unplaced_warnings(records: list[dict], places: list[str | None], material: Material) -> list[str]:
    counts = Counter(r["project_id"] for r, where in zip(records, places) if where is None)
    warnings = []
    for p in material.projects:
        n = counts.get(p["id"])
        if n:
            warnings.append(f"{plural(n, 'bullet')} of {p['id']} {shorten(p['internal_name'])!r} "
                            f"({project_span(p)}) {'has' if n == 1 else 'have'} no place: no job of the profile "
                            f"overlaps it; resume-ats cannot place {'it' if n == 1 else 'them'} until the job is "
                            "added with /resume-builder:wizard")
    return warnings


def committed(records: list[dict], places: list[str | None], material: Material) -> list[str]:
    lines = []
    for record, where in zip(records, places):
        project = f"  {record['project_id']}" if record["project_id"] else ""
        lines.append(f"  {record['id']}  {where or 'no place'}{project}  {record['form']}  {record['text']}")
    lines += [f"  story  {p['id']}  {p['internal_name']}" for p in told(material.projects)]
    return lines
