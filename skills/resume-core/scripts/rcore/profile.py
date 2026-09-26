"""The profile: JSON Resume vocabulary, entry identities, and the effective profile.

03-profile/profile.json is the base and decisions/profile.json is laid over it:
- two objects merge key by key;
- two arrays whose items are all objects merge by index: wizard item i merges
  onto imported item i, wizard items past the end are added, and {} leaves an
  imported item unchanged;
- two other arrays (such as keywords) combine: imported items, then wizard
  items not already present;
- in every other case the wizard's value replaces the imported one.

A missing or unreadable file, or one that is not a JSON object, counts as {}.
The fact-field check and the basics.label check compare against this profile;
wizard: source references still point into the raw decisions/profile.json.

Also here, shared by resume-import, resume-sanitize and resume-wizard: the
JSON Resume sections and fields, which fields are prose, and the fields that
say which entry an array item is (re-import warnings and wizard anchors).
"""
from __future__ import annotations

import copy
import datetime
import re
from pathlib import Path

from . import wsio

IMPORTED = "03-profile/profile.json"
WIZARD = "decisions/profile.json"

# JSON Resume fields, by section.
BASICS = ("name", "label", "image", "email", "phone", "url", "summary", "location", "profiles")
LOCATION = ("address", "postalCode", "city", "countryCode", "region")
PROFILE_ITEM = ("network", "username", "url")
SECTIONS = {
    "work": ("name", "position", "url", "location", "description", "startDate", "endDate",
             "summary", "highlights"),
    "volunteer": ("organization", "position", "url", "startDate", "endDate", "summary", "highlights"),
    "education": ("institution", "url", "area", "studyType", "startDate", "endDate", "score", "courses"),
    "awards": ("title", "date", "awarder", "summary"),
    "certificates": ("name", "date", "issuer", "url"),
    "publications": ("name", "publisher", "releaseDate", "url", "summary"),
    "skills": ("name", "level", "keywords"),
    "languages": ("language", "fluency"),
    "interests": ("name", "keywords"),
    "references": ("name", "reference"),
    "projects": ("name", "description", "highlights", "keywords", "startDate", "endDate", "url",
                 "roles", "entity", "type"),
}
ARRAY_FIELDS = frozenset({"highlights", "keywords", "courses", "roles"})
DATE_FIELDS = frozenset({"startDate", "endDate", "date", "releaseDate"})
# Prose: sentences rather than facts. Sanitize rewrites these; the wizard never writes them.
# basics.summary, and these fields of any entry of a section.
PROSE_FIELDS = frozenset({"summary", "description", "highlights", "reference"})

# The fields that say which entry an array item is, in the order they are shown.
IDENTITY = {
    "work": ("position", "name"),
    "volunteer": ("position", "organization"),
    "education": ("studyType", "area", "institution"),
    "certificates": ("name", "issuer"),
    "awards": ("title",),
    "languages": ("language",),
    "profiles": ("network", "username"),
}
DEFAULT_IDENTITY = ("name",)

_ISO_DATE = re.compile(r"\d{4}(?:-\d{2}(?:-\d{2})?)?")


def is_date(value) -> bool:
    """True for a real date written as YYYY, YYYY-MM or YYYY-MM-DD."""
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        return False
    parts = [int(p) for p in value.split("-")]
    try:
        datetime.date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
    except ValueError:
        return False
    return True


def identity(section: str, entry) -> dict | None:
    """The identity fields an entry has, as {field: value}; None when there is no entry.

    section is a top-level section name, or "profiles" for basics.profiles.
    """
    if not isinstance(entry, dict):
        return None
    return {f: entry[f] for f in IDENTITY.get(section, DEFAULT_IDENTITY) if f in entry}


def describe(section: str, entry) -> str:
    """'Software Engineer, Tailspin Toys' for a work entry: its identity values, joined."""
    fields = IDENTITY.get(section, DEFAULT_IDENTITY)
    values = [str(entry.get(f)) for f in fields if isinstance(entry, dict) and entry.get(f) not in (None, "")]
    return ", ".join(values) or "an entry with no name"


def merged_arrays(doc):
    """Yield (pointer, section, array) for each array in doc that holds objects merged by index.

    These are the top-level sections and basics.profiles. The array is yielded
    as it is; callers check that its items are objects.
    """
    if not isinstance(doc, dict):
        return
    for key, value in doc.items():
        if key != "basics" and isinstance(value, list):
            yield f"/{key}", key, value
    basics = doc.get("basics")
    if isinstance(basics, dict) and isinstance(basics.get("profiles"), list):
        yield "/basics/profiles", "profiles", basics["profiles"]


def _merge(imported, wizard):
    if isinstance(imported, dict) and isinstance(wizard, dict):
        merged = dict(imported)
        for key, value in wizard.items():
            merged[key] = _merge(imported[key], value) if key in imported else value
        return merged
    if isinstance(imported, list) and isinstance(wizard, list):
        if all(isinstance(item, dict) for item in imported + wizard):
            merged = [_merge(item, wizard[i]) if i < len(wizard) else item
                      for i, item in enumerate(imported)]
            return merged + wizard[len(imported):]
        combined = list(imported)
        for item in wizard:
            if item not in combined:
                combined.append(item)
        return combined
    return wizard


def overlay(imported, wizard):
    """Lay wizard answers over an imported profile. Returns a new structure."""
    return copy.deepcopy(_merge(imported, wizard))


def _read_object(workspace: Path, rel: str) -> dict:
    data, _ = wsio.load(workspace, rel)
    return data if isinstance(data, dict) else {}


def effective_profile(workspace: Path) -> dict:
    workspace = Path(workspace)
    return overlay(_read_object(workspace, IMPORTED), _read_object(workspace, WIZARD))
