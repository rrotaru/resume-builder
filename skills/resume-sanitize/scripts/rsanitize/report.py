"""What the sanitize scripts print."""
from __future__ import annotations

from rcore import terms

from .common import plural, shorten
from .detect import KINDS, detect
from .proposals import describe_places
from .texts import ScanTexts, Text


def likely_terms(texts: list[Text], skip: set[str]) -> list[tuple[str, str, list[str]]]:
    """(kind, term, places) for each likely term in texts whose key is not in skip.

    Hits are grouped by rcore.terms.key, keeping the first kind and spelling
    seen, and sorted by kind (detect.KINDS order), most places first, then term.
    """
    groups: dict[str, tuple[str, str, list[str]]] = {}
    for text in texts:
        for hit in detect(text.text, text.names):
            key = terms.key(hit.term)
            if not key or key in skip:
                continue
            kind, term, found = groups.setdefault(key, (hit.kind, hit.term, []))
            place = text.place_at(hit.start)
            if place not in found:
                found.append(place)
    return sorted(groups.values(), key=lambda g: (KINDS.index(g[0]), -len(g[2]), g[1].casefold(), g[1]))


def likely_lines(found: list[tuple[str, str, list[str]]]) -> list[str]:
    return [f"  {kind:<8}  {term!r}  {describe_places(where)}" for kind, term, where in found]


def scan_header(scanned: ScanTexts, projects: list[dict]) -> list[str]:
    parts = [plural(scanned.projects, "project"), f"{plural(scanned.project_items, 'evidence item')} in projects",
             plural(scanned.reviews, "performance review")]
    if scanned.profile:
        parts.append("03-profile/profile.json")
    lines = [f"scanned: {', '.join(parts)}"]
    for project in sorted(projects, key=lambda p: p["rank"]):
        lines.append(f" {project['rank']}. {project['id']}  {project['internal_name']}")
        if project["summary"]:
            lines.append(f"    {project['summary']}")
        if project["rank_reasons"]:
            lines.append(f"    reasons: {'; '.join(project['rank_reasons'])}")
    return lines


def replacements(counts) -> str:
    total = sum(counts.values())
    if not total:
        return "replaced nothing: no denied term appears"
    detail = ", ".join(f"{term!r} {n}" for term, n in counts.most_common())
    return f"replaced {plural(total, 'match', 'matches')}: {detail}"


def changes(bullets_before: list[dict], bullets_after: list[dict], stories: str, story_lines: list[int],
            profile_changes: dict[str, str], bullets_label: str, stories_label: str, profile_label: str) -> list[str]:
    changed = [(a["id"], a["text"]) for b, a in zip(bullets_before, bullets_after) if a["text"] != b["text"]]
    lines = [f"{bullets_label}: {len(changed)} of {plural(len(bullets_after), 'bullet')} changed"]
    lines += [f"  {bid}: {text}" for bid, text in changed]
    story_text = stories.splitlines()
    lines.append(f"{stories_label}: {plural(len(story_lines), 'line')} changed")
    lines += [f"  {n}: {story_text[n - 1] if n <= len(story_text) else ''}" for n in story_lines]
    lines.append(f"{profile_label}: {plural(len(profile_changes), 'prose field')} changed")
    lines += [f"  {pointer}: {shorten(text, 120)}" for pointer, text in profile_changes.items()]
    return lines
