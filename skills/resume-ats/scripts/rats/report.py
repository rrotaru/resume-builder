"""What the scripts print, and each version's report.json."""
from __future__ import annotations

from rcore import stages
from rcore.profile import describe

from . import coverage, draft
from .common import Version, plural, shorten
from .material import SECTIONS, Material

WIDTH = 3  # where-items shown per keyword


def span(entry: dict) -> str:
    """'2019-06 to 2022-12', '2023-01 to present', or '' for an entry without dates."""
    start, end = entry.get("startDate"), entry.get("endDate")
    if start is None and end is None:
        return ""
    return f"{start or '?'} to {end or 'present'}"


def stale_warnings(workspace) -> list[str]:
    status = stages.status(workspace)
    return [f"{stage} is stale (its inputs changed since it was built): its bullets may not reflect the latest "
            "decisions; rebuild it first (see SKILL.md)" for stage in ("06-bullets", "07-sanitized")
            if status.get(stage) == "stale"]


def homeless_warnings(material: Material) -> list[str]:
    lines = []
    for bullet in material.bullets:
        why = material.homeless.get(bullet["id"])
        if why is None:
            continue
        project = material.projects.get(bullet["project_id"]) if bullet["project_id"] else None
        who = f" ({project['id']} {shorten(project['internal_name'])!r})" if project else ""
        then = ("it is left out until the job is added with /resume-builder:wizard" if "overlaps" in why
                else "it is left out")
        lines.append(f"{bullet['id']}{who} has no place: {why}; {then}")
    return lines


def denied_fact_warnings(material: Material) -> list[str]:
    return [f"{pointer} {value!r} holds the denied term {', '.join(repr(t) for t in held)}; facts are copied "
            "exactly, so the commit refuses it until the engineer sets a replacement value with "
            "/resume-builder:wizard" for pointer, value, held in draft.denied_facts(material)]


def withheld_notes(material: Material) -> list[str]:
    return [f"{pointer} {keyword!r} holds the denied term {', '.join(repr(t) for t in held)}; a keyword cannot be "
            "replaced, so it is left out" for pointer, keyword, held in draft.withheld(material)]


def places(material: Material) -> list[str]:
    lines = ["places:"]
    for section in SECTIONS:
        for i, entry in enumerate(material.entries(section)):
            if not isinstance(entry, dict):
                continue
            dates = span(entry)
            lines.append(f"  /{section}/{i}  {describe(section, entry)}" + (f"  {dates}" if dates else ""))
            placed = [b for b in material.bullets if material.place(b) == (section, i)]
            for bullet in placed:
                project = f"  {bullet['project_id']}" if bullet["project_id"] else ""
                lines.append(f"    {bullet['id']}{project}  {bullet['form']}  {bullet['text']}")
            if not placed:
                lines.append("    (no bullets)")
    return lines if len(lines) > 1 else ["places: none; the profile has no jobs or projects (run "
                                         "/resume-builder:import, or add a job with /resume-builder:wizard)"]


def length_line(length: dict) -> str:
    return (f"experience: {length['experience_months']} months: {plural(length['pages'], 'page')}, "
            f"{length['line_budget']} lines")


def next_line(version: Version) -> str:
    if version.is_job:
        return (f"next: read {version.draft('jd.txt')}, write {version.draft('keywords.json')} (the posting's "
                f"keywords, as it spells them), run keywords.py {version.name}, then tailor resume.json and run "
                "ats.py --commit")
    return (f"next: write {version.draft('keywords.json')} (the target role's keywords), run keywords.py general, "
            "then select, order and reword the bullets in resume.json and run ats.py --commit")


def keyword_lines(name: str, report: list[dict]) -> list[str]:
    counts = coverage.counts(report)
    lines = [f"keywords for {name}: {counts[coverage.COVERED]} covered, {counts[coverage.WITH]} missing with "
             f"evidence, {counts[coverage.WITHOUT]} missing without evidence"]
    labels = {coverage.COVERED: "covered", coverage.WITH: "missing with evidence",
              coverage.WITHOUT: "missing without evidence"}
    for item in report:
        where = item["where"][:WIDTH] + ([f"and {len(item['where']) - WIDTH} more"]
                                         if len(item["where"]) > WIDTH else [])
        lines.append(f"  {labels[item['status']]}  {item['keyword']}" + (f"  {', '.join(where)}" if where else ""))
    return lines


def keyword_summary(report: list[dict]) -> str:
    counts = coverage.counts(report)
    return (f"keywords: {counts[coverage.COVERED]} covered, {counts[coverage.WITH]} missing with evidence, "
            f"{counts[coverage.WITHOUT]} missing without evidence")


def bullet_count(resume: dict, material: Material) -> str:
    used = sum(len(e.get("x-highlights", [])) for s in SECTIONS for e in resume.get(s, []))
    return f"{used} of {plural(len(material.bullets), 'bullet')}"


def left_out(resume: dict, material: Material) -> list[dict]:
    used = {h["bullet_id"] for s in SECTIONS for e in resume.get(s, []) for h in e.get("x-highlights", [])}
    return [{"bullet_id": b["id"], "reason": "no place" if b["id"] in material.homeless else "not selected"}
            for b in material.bullets if b["id"] not in used]


def report_json(resume: dict, material: Material, keywords: list[dict], length: dict, warnings: list[str]) -> dict:
    return {"length": length, "keywords": keywords, "left_out": left_out(resume, material), "warnings": warnings}


def revise_lines(resume: dict, material: Material) -> list[str]:
    lines = []
    for section in SECTIONS:
        for i, entry in enumerate(resume.get(section, [])):
            for j, highlight in enumerate(entry.get("x-highlights", [])):
                lines.append(f"  /{section}/{i}/x-highlights/{j}  {highlight['bullet_id']}  {highlight['text']}")
                bullet = material.by_id.get(highlight["bullet_id"])
                if bullet and bullet["text"] != highlight["text"]:
                    lines.append(f"      was: {bullet['text']}")
    return lines or ["  (no bullets)"]


def flag_lines(flags: dict) -> list[str]:
    return [f"  {flag['bullet_id']}  {reason}" for flag in flags["flags"] for reason in flag["reasons"]]
