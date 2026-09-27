"""What ats works from: the sanitized bullets and their places, the effective profile, and the texts claims rest on.

- A bullet's place is rcore.places.place: work_ref, or a resume: or wizard:
  pointer into /projects/<i>. A place past the end of the effective profile's
  work or projects is no place (07-sanitized is out of date).
- Known texts are what a bullet may say: its original text, the texts of its
  sources (rcore.citations), those texts with each denied term replaced as
  sanitize apply would, and the name, position and location of the entry it
  sits under.
- The evidence pool is what a resume could draw on, for keyword coverage:
  every sanitized bullet, the evidence of current projects and the
  performance reviews, the metrics of current projects, and every string of
  the imported profile and the wizard's answers.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path

from rcore import places, terms, wsio
from rcore.citations import Citations, is_review

from .common import AtsError, Inputs

ENTRY_FIELDS = ("name", "position", "location")  # an entry's facts a bullet under it may name
SECTIONS = ("work", "projects")


def current_month() -> tuple[int, int]:
    """(year, month) today. Tests replace it to fix the date."""
    today = datetime.date.today()
    return today.year, today.month


@dataclass
class Material:
    inputs: Inputs
    bullets: list[dict]  # 07-sanitized order
    by_id: dict[str, dict]
    effective: dict
    projects: dict[str, dict]  # project ID -> project
    citations: Citations
    patterns: terms.Patterns
    replacements: dict[str, str]  # denied term -> its replacement
    month: tuple[int, int]
    homeless: dict[str, str] = field(default_factory=dict)  # bullet ID -> why it has no place

    def entries(self, section: str) -> list:
        found = self.effective.get(section)
        return found if isinstance(found, list) else []

    def place(self, bullet: dict) -> tuple[str, int] | None:
        """The bullet's place, when the effective profile has that entry."""
        found = places.place(bullet)
        if found is None:
            return None
        section, index = found
        entries = self.entries(section)
        return found if index < len(entries) and isinstance(entries[index], dict) else None

    def no_place(self, bullet: dict) -> str:
        """Why a bullet has no place."""
        found = places.place(bullet)
        if found is None:
            return "no job of the profile overlaps its project" if bullet.get("project_id") else "it names no place"
        return f"/{found[0]}/{found[1]} is not in the profile (07-sanitized is out of date)"

    def sanitized(self, text: str) -> str:
        """text with each denied term replaced by its replacement."""
        spans = terms.find(text, self.patterns)
        if not spans:
            return text
        out, at = [], 0
        for start, end, term in spans:
            out += [text[at:start], self.replacements[term]]
            at = end
        return "".join(out + [text[at:]])

    def source_texts(self, refs) -> list[str]:
        """The texts of each source, and each with denied terms replaced."""
        found = []
        for ref in refs:
            for text in self.citations.texts(ref):
                found.append(text)
                replaced = self.sanitized(text)
                if replaced != text:
                    found.append(replaced)
        return found

    def known(self, highlight: dict, entry: dict) -> list[str]:
        """What an x-highlights item may say: its bullet's text and sources, and its entry's facts."""
        bullet = self.by_id.get(highlight.get("bullet_id"))
        refs = bullet["sources"] if bullet else highlight.get("sources") or []
        found = [bullet["text"]] if bullet else []
        found += self.source_texts(refs)
        found += [entry[f] for f in ENTRY_FIELDS if isinstance(entry.get(f), str)]
        return found

    def project_of(self, highlight: dict) -> dict | None:
        bullet = self.by_id.get(highlight.get("bullet_id"))
        return self.projects.get(bullet.get("project_id")) if bullet else None

    def pool(self) -> list[tuple[str, str]]:
        """(where, text) of everything a resume could draw on, for keyword coverage."""
        found = [(b["id"], b["text"]) for b in self.bullets]
        held = {e for p in self.projects.values() for e in p["evidence_ids"]}
        for item in self.inputs.evidence:
            if item["id"] in held or is_review(item):
                found += [(item["id"], text) for text in self.citations.texts(item["id"])]
        for metric in self.inputs.metrics:
            if metric["project_id"] in self.projects:
                found.append((f"metric:{metric['id']}", metric["statement"]))
        for prefix, doc in (("resume:", self.inputs.profile or {}), ("wizard:", self.inputs.wizard)):
            found += [(prefix + pointer, text) for pointer, text in wsio.iter_strings(doc)]
        return found


def build(workspace: Path, inputs: Inputs) -> Material:
    entries, errors = terms.read_entries(workspace)
    if errors:
        raise AtsError(errors + ["decisions/terms.json is not usable; fix it with /resume-builder:wizard"])
    denied = [e for e in entries if e["replacement"] is not None]
    patterns = terms.compile_terms([e["term"] for e in denied],
                                   [e["term"] for e in entries if e["replacement"] is None])
    material = Material(
        inputs=inputs, bullets=inputs.bullets, by_id={b["id"]: b for b in inputs.bullets},
        effective=inputs.effective, projects={p["id"]: p for p in inputs.projects},
        citations=Citations(workspace, inputs.evidence, inputs.metrics, inputs.profile, inputs.wizard),
        patterns=patterns, replacements={e["term"]: e["replacement"] for e in denied}, month=current_month())
    material.homeless = {b["id"]: material.no_place(b) for b in inputs.bullets if material.place(b) is None}
    return material
