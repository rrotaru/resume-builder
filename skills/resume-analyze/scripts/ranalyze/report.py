"""What signals.py and match_projects.py print."""
from __future__ import annotations

from .clusters import counts
from .common import is_perf_review, plural, shorten
from .decisions import Outcome, closest, describe


def _kinds(kinds: dict) -> str:
    return ", ".join(f"{kind} {n}" for kind, n in kinds.items())


def _mentions(reviews: list[str]) -> str:
    return f"review mentions: {', '.join(reviews)}" if reviews else "review mentions: none"


def signals(data: dict, evidence_count: int) -> list[str]:
    clusters = data["clusters"]
    larger = sum(1 for c in clusters if len(c["evidence_ids"]) > 1)
    lines = [f"02-evidence: {plural(evidence_count, 'item')}, {plural(len(clusters), 'cluster')} "
             f"({larger} with two or more items), {plural(len(data['reviews']), 'performance review')}"]
    for c in clusters:
        size = len(c["evidence_ids"])
        if size == 1:
            role = next((name for name in ("authored", "reviewed", "assigned", "reported") if c[name]), "")
            kind = next(iter(c["kinds"]))
            extra = f"; {_mentions(c['review_mentions'])}" if c["review_mentions"] else ""
            lines.append(f"{c['id']}  1 item, {c['start']}: {kind}{', ' + role if role else ''}{extra}; "
                         f"{c['label']!r}")
            continue
        stats = c["stats"]
        lines += [
            f"{c['id']}  {size} items, {c['start']} to {c['end']} ({plural(c['days'], 'day')}): {_kinds(c['kinds'])}",
            f"    authored {c['authored']}, reviewed {c['reviewed']}, assigned {c['assigned']}, reported "
            f"{c['reported']}; +{stats['additions']}/-{stats['deletions']} lines in {plural(stats['files'], 'file')}",
            f"    repos: {', '.join(c['repos']) or 'none'}; Jira: {', '.join(c['jira_projects']) or 'none'}; "
            f"{plural(c['contributors'], 'contributor')}; epics: {len(c['epics'])} (created "
            f"{len(c['epics_created'])}); {'authored first' if c['authored_first'] else 'not authored first'}; "
            f"open items: {c['open_items']}; {_mentions(c['review_mentions'])}",
            f"    {c['label']!r}",
        ]
    for r in data["reviews"]:
        reached = f"links to {', '.join(r['clusters'])}" if r["clusters"] else "links to no cluster"
        lines.append(f"review {r['id']} {r['date']} {r['title']!r}: {reached}; full text at {r['raw_ref']}")
    return lines


def checkpoint(records: list[dict], outcome: Outcome, evidence: list[dict], mentioned: dict,
               prompts: int, carried: int, new: int) -> list[str]:
    """The projects for checkpoint 2, then exclusions, unassigned evidence and decision counts."""
    by_id = {item["id"]: item for item in evidence}
    lines = [f"{plural(len(records), 'project')}; metric prompts for the top {prompts}",
             f"IDs: {carried} {'group' if carried == 1 else 'groups'} carried from the last run, {new} new"]
    for record, project in zip(records, outcome.projects, strict=True):
        counted = counts([by_id[e] for e in record["evidence_ids"]], mentioned)
        size = len(record["evidence_ids"])
        lines += [
            f"{record['rank']:2}. {record['id']}  {record['internal_name']}  [{record['role']}, {record['scope']}, "
            f"{record['start']} to {record['end']}]{'  metric prompt' if record['metric_prompt'] else ''}",
            f"    {record['summary'] or '(no summary: record one with decide.py rename --summary)'}",
            f"    {plural(size, 'item')}: {counted['authored']} authored, {counted['reviewed']} reviewed, "
            f"{counted['assigned']} assigned, {counted['reported']} reported; "
            f"{_mentions(counted['review_mentions'])}",
            f"    reasons: {'; '.join(record['rank_reasons']) or 'none'}",
            f"    id: {project.origin}",
        ]
        if project.applied:
            lines.append(f"    decisions: {', '.join(project.applied)}")
    for project, number in outcome.excluded:
        lines.append(f"excluded: {project.id} {shorten(project.internal_name)!r} (decision {number})")
    grouped = {e for r in records for e in r["evidence_ids"]}
    left = [item for item in evidence if item["id"] not in grouped]
    reviews = sum(1 for item in left if is_perf_review(item))
    lines.append(f"not in any project: {len(left)} of {plural(len(evidence), 'item')}"
                 + (f", including {plural(reviews, 'performance review')}" if reviews else ""))
    lines.append(f"decisions: {outcome.applied} applied, {len(outcome.orphans)} orphaned")
    return lines


def orphans(outcome: Outcome) -> list[str]:
    lines = []
    for orphan in outcome.orphans:
        near = closest(orphan.decision, outcome.projects)
        hint = (f"; closest is {near[0].id} {shorten(near[0].internal_name)!r} ({near[1]} of its {near[2]} items)"
                if near else "; no current project shares its items")
        lines += [f"orphaned: decision {orphan.number} ({describe(orphan.decision)}): {orphan.reason}{hint}",
                  f"  fix: re-link it to a project with decide.py relink {orphan.number} PJ, or discard it with "
                  f"decide.py discard {orphan.number}"]
    return lines
