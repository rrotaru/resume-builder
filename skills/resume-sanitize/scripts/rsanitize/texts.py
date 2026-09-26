"""The texts each half reads, each with its place, and where terms occur in them.

A place names where a text came from, in the vocabulary bullets already use:
pj_... (a project in 04-projects/projects.json), ev_... (an evidence item or a
performance review), resume:<pointer> (03-profile/profile.json, or the same
pointer in 07-sanitized/profile.json), b_... (a bullet) and stories.md, whose
places carry the line a match starts on (stories.md:3).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rcore import terms, wsio
from rcore.raw import RawReader

from .replace import prose

_LINE_BREAK = re.compile("\r\n|[\n\r\x0b\x0c\x1c\x1d\x1e\x85  ]")


@dataclass(frozen=True)
class Text:
    place: str
    text: str
    by_line: bool = False  # places are "<place>:<line>" (stories.md)
    names: bool = True  # look for capitalized names here (not in the profile's fact fields)

    def place_at(self, offset: int) -> str:
        """The place of a match starting at offset."""
        return f"{self.place}:{line_of(self.text, offset)}" if self.by_line else self.place


def line_of(text: str, offset: int) -> int:
    """The 1-based line of offset, counting lines as str.splitlines() does."""
    return len(_LINE_BREAK.findall(text[:offset])) + 1


# The scan ----------------------------------------------------------------------

@dataclass
class ScanTexts:
    texts: list[Text]
    warnings: list[str]
    projects: int
    project_items: int
    reviews: int
    profile: bool


def scan_texts(workspace: Path, projects: list[dict], evidence: list[dict], profile: dict | None) -> ScanTexts:
    """The texts the scan reads, in order: projects, their evidence and the reviews, the profile."""
    texts: list[Text] = []
    for project in sorted(projects, key=lambda p: p["rank"]):
        place = project["id"]
        texts += [Text(place, project["internal_name"]), Text(place, project["summary"])]
        texts += [Text(place, reason) for reason in project["rank_reasons"]]
    in_projects = {e for p in projects for e in p["evidence_ids"]}
    reader, warnings, items, reviews = RawReader(workspace), [], 0, 0
    for item in evidence:
        review = item["kind"] == "perf_review"
        if not review and item["id"] not in in_projects:
            continue
        reviews, items = reviews + review, items + (not review)
        texts += [Text(item["id"], item["title"]), Text(item["id"], item.get("excerpt") or "")]
        if review:
            text, why = reader.text(item.get("raw_ref"))
            if text is None:
                warnings.append(f"{item['id']}: the raw record {item.get('raw_ref')} {why}; "
                                "its excerpt stands in for the review's text")
            else:
                texts.append(Text(item["id"], text))
    if profile is not None:
        texts += profile_texts(profile)
    return ScanTexts([t for t in texts if t.text], warnings, len(projects), items, reviews, profile is not None)


# Apply's output ----------------------------------------------------------------

def output_texts(bullets: list[dict], stories: str, profile: dict) -> list[Text]:
    """The sanitized text, in order: bullets, stories.md, the profile."""
    texts = [Text(b["id"], b["text"]) for b in bullets]
    texts.append(Text("stories.md", stories, by_line=True))
    texts += profile_texts(profile)
    return [t for t in texts if t.text]


def profile_texts(profile: dict) -> list[Text]:
    """Every string of a profile, as resume:<pointer>. Names are looked for only in its prose.

    Fact fields hold the engineer's own titles, employers and schools, which
    are rarely confidential and would drown the list of likely terms.
    """
    prose_pointers = {pointer for pointer, _, _ in prose(profile)}
    return [Text(f"resume:{pointer}", value, names=pointer in prose_pointers)
            for pointer, value in wsio.iter_strings(profile)]


# Occurrences -------------------------------------------------------------------

def places(term: str, texts: list[Text], allowed: list[str]) -> list[str]:
    """Where term occurs in texts, by the terms check's rules, each place once, in text order.

    Allowed terms exempt a match they cover, as in the check, except an allowed
    term that is this term itself (an already decided candidate still occurs).
    """
    key = terms.key(term)
    patterns = terms.compile_terms([term], [a for a in allowed if terms.key(a) != key])
    found: list[str] = []
    for text in texts:
        for start, _, _ in terms.find(text.text, patterns):
            place = text.place_at(start)
            if place not in found:
                found.append(place)
    return found
