"""Keyword coverage: whether each keyword of a version is on its resume, or could be.

- covered: found in the resume's visible text (VISIBLE), where lists the
  resume pointers in resume order;
- missing_with_evidence: found in what the resume could draw on
  (material.Material.pool), where lists bullet IDs, evidence IDs, metric:
  IDs, then resume: and wizard: pointers;
- missing_without_evidence: neither.
Keywords are found with match's rule.
"""
from __future__ import annotations

from . import match
from .material import Material

COVERED, WITH, WITHOUT = "covered", "missing_with_evidence", "missing_without_evidence"
# The fields an ATS reads for skills, by section; bullets are x-highlights texts.
VISIBLE = {
    "work": ("name", "position", "location"),
    "projects": ("name", "position", "location"),
    "education": ("studyType", "area", "institution"),
    "certificates": ("name", "issuer"),
    "skills": ("name",),
}


def visible(resume: dict) -> list[tuple[str, str]]:
    """(pointer, text) for the resume's visible text, in resume order."""
    found = []
    basics = resume.get("basics") if isinstance(resume.get("basics"), dict) else {}
    for name in ("label", "summary"):
        if isinstance(basics.get(name), str):
            found.append((f"/basics/{name}", basics[name]))
    for section, fields in VISIBLE.items():
        for i, entry in enumerate(resume.get(section, [])):
            found += [(f"/{section}/{i}/{f}", entry[f]) for f in fields if isinstance(entry.get(f), str)]
            for j, highlight in enumerate(entry.get("x-highlights", [])):
                found.append((f"/{section}/{i}/x-highlights/{j}/text", highlight["text"]))
            for k, keyword in enumerate(entry.get("keywords", [])):
                found.append((f"/{section}/{i}/keywords/{k}", keyword))
    return [(pointer, match.normalize(text)) for pointer, text in found]


def cover(resume: dict, keywords: list[str], material: Material) -> list[dict]:
    """One {keyword, status, where} per keyword, in keywords.json order."""
    shown = visible(resume)
    pool = [(where, match.normalize(text)) for where, text in material.pool()]
    report = []
    for keyword in keywords:
        where = [pointer for pointer, text in shown if match.mentions(text, keyword)]
        status = COVERED
        if not where:
            where = list(dict.fromkeys(w for w, text in pool if match.mentions(text, keyword)))
            status = WITH if where else WITHOUT
        report.append({"keyword": keyword, "status": status, "where": where})
    return report


def counts(report: list[dict]) -> dict[str, int]:
    return {status: sum(1 for k in report if k["status"] == status) for status in (COVERED, WITH, WITHOUT)}
