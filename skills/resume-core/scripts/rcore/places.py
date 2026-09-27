"""A bullet's place on the resume: the profile entry it goes under.

work_ref is an index into the effective profile's work: the job the bullet
goes under. A bullet with work_ref null that cites a resume: or wizard:
pointer into /projects/<i> goes under the profile project projects[i]. A
bullet with neither has no place (a project no job overlaps). resume-write
checks these rules; resume-ats puts each bullet under its place.
"""
from __future__ import annotations

import re

_PLACE = re.compile(r"^(?:resume|wizard):/(work|projects)/(0|[1-9][0-9]*)(?:/|$)")


def pointer_place(ref: str) -> tuple[str, int] | None:
    """('work', 1) for resume:/work/1/highlights/0, ('projects', 0) for a profile project; else None."""
    match = _PLACE.match(ref)
    return (match.group(1), int(match.group(2))) if match else None


def place(bullet: dict) -> tuple[str, int] | None:
    """Where a bullet goes: ('work', i), ('projects', i), or None when it has no place."""
    if bullet.get("work_ref") is not None:
        return "work", bullet["work_ref"]
    for ref in bullet.get("sources") or []:
        found = pointer_place(ref)
        if found and found[0] == "projects":
            return found
    return None
