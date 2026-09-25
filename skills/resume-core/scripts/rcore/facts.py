"""Fact-field check: every non-bullet field of a tailored resume is copied from the profile.

Bullets (basics.summary, highlights, x-highlights) and source metadata are
checked elsewhere. Every other field is a fact and must come from the
effective profile (see profile.py):

- basics: each field equals the profile's value; each location key equals the
  profile's location key; each profiles item equals some profile item in every
  field it has. basics.label has its own rule in sources.py.
- work, projects, education, certificates and skills: each entry matches one
  profile entry P of the same section. Every fact field the entry has, P has
  with the same value. A date (startDate, endDate, date) may be shortened
  (2023-01-15 as 2023-01 or 2023) but not lengthened. The entry has a date
  field exactly when P has it, so dropping endDate cannot turn a past job into
  a current one. keywords holds only items of P's keywords. Other fields may
  be left out. All fields of one entry must match the same P.

Values compare exactly, including their JSON types. Unknown fields are
treated as facts, so the check fails closed on input that skipped validation.
"""
from __future__ import annotations

import json

SECTIONS = ("work", "projects", "education", "certificates", "skills")
DATE_FIELDS = ("startDate", "endDate", "date")
# Entry fields that are bullets; the source and flags checks cover them.
BULLET_FIELDS = frozenset({"highlights", "x-highlights"})
# basics fields that are not facts, or have their own rule (label).
BASICS_SKIP = frozenset({"label", "summary", "x-summary-sources"})


def _same(a, b) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def _date_ok(value, profile_value) -> bool:
    return (isinstance(value, str) and isinstance(profile_value, str)
            and (value == profile_value or profile_value.startswith(value + "-")))


def _differences(entry: dict, candidate: dict) -> list[tuple]:
    """Why entry does not match candidate, as (kind, field, value, profile value) tuples."""
    found = []
    for field, value in entry.items():
        if field in BULLET_FIELDS:
            continue
        if field == "keywords" and isinstance(value, list) and isinstance(candidate.get(field), list):
            found += [("keyword", field, k, None) for k in value
                      if not any(_same(k, p) for p in candidate[field])]
        elif field not in candidate:
            found.append(("absent", field, value, None))
        elif field in DATE_FIELDS:
            if not _date_ok(value, candidate[field]):
                found.append(("differs", field, value, candidate[field]))
        elif not _same(value, candidate[field]):
            found.append(("differs", field, value, candidate[field]))
    for field in DATE_FIELDS:
        if field in candidate and field not in entry:
            found.append(("missing", field, None, candidate[field]))
    return found


def _describe(kind: str, field: str, value, profile_value, where: str, closest: str) -> str:
    if kind == "keyword":
        return f"{where}: keyword {value!r} is not in the profile (closest entry {closest})"
    if kind == "absent":
        return f"{where}: {field} {value!r} is not in the profile (closest entry {closest} has no {field})"
    if kind == "missing":
        return f"{where}: {field} is missing (closest entry {closest} has {profile_value!r})"
    return (f"{where}: {field} {value!r} does not match the profile "
            f"(closest entry {closest} has {profile_value!r})")


def _check_entries(entries, candidates, path: str, section: str, label: str) -> list[str]:
    """Match each entry to one candidate; report differences from the closest one."""
    if not isinstance(entries, list):
        return [f"{label}: {path}: must be an array"]
    candidates = candidates if isinstance(candidates, list) else []
    usable = [(j, c) for j, c in enumerate(candidates) if isinstance(c, dict)]
    errors = []
    for i, entry in enumerate(entries):
        where = f"{label}: {path}/{i}"
        if not isinstance(entry, dict):
            errors.append(f"{where}: must be an object")
            continue
        if not usable:
            errors.append(f"{where}: the profile has no {section} entries")
            continue
        results = [(len(diffs), j, diffs) for j, c in usable for diffs in [_differences(entry, c)]]
        _, j, diffs = min(results, key=lambda r: (r[0], r[1]))
        errors += [_describe(*d, where, f"{path}/{j}") for d in diffs]
    return errors


def _check_value(value, profile_value, present: bool, where: str) -> list[str]:
    if not present:
        return [f"{where}: {value!r} is not in the profile"]
    if not _same(value, profile_value):
        return [f"{where}: {value!r} does not match the profile ({profile_value!r})"]
    return []


def _check_basics(basics, profile_basics, label: str) -> list[str]:
    if not isinstance(basics, dict):
        return [f"{label}: /basics: must be an object"]
    profile_basics = profile_basics if isinstance(profile_basics, dict) else {}
    errors = []
    for field, value in basics.items():
        if field in BASICS_SKIP:
            continue
        if field == "profiles":
            errors += _check_entries(value, profile_basics.get("profiles"), "/basics/profiles",
                                     "basics.profiles", label)
        elif field == "location" and isinstance(value, dict) and isinstance(profile_basics.get(field), dict):
            location = profile_basics[field]
            for key, part in value.items():
                errors += _check_value(part, location.get(key), key in location,
                                       f"{label}: /basics/location/{key}")
        else:
            errors += _check_value(value, profile_basics.get(field), field in profile_basics,
                                   f"{label}: /basics/{field}")
    return errors


def check(resume: dict, effective: dict, label: str) -> list[str]:
    """Return one line per fact field in resume that is not copied from the effective profile."""
    errors = []
    if "basics" in resume:
        errors += _check_basics(resume["basics"], effective.get("basics"), label)
    for section in SECTIONS:
        if section in resume:
            errors += _check_entries(resume[section], effective.get(section), f"/{section}", section, label)
    return errors
