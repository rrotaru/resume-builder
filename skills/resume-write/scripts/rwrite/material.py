"""What write writes about, and what the checks compare bullets and stories with.

- Jobs are the effective profile's work entries (the imported ones, then any the
  wizard added). A job's months run from its startDate to its endDate: a year
  alone starts in January and ends in December, a missing startDate is open and
  a missing endDate means the job is ongoing. A job overlaps a project when
  neither ends before the other starts, by the project's start and end months.
- Projects come from 04-projects/projects.json only, in rank order.
- Source texts are what a source reference says, for the number check: an
  evidence item's title and excerpt, and for a performance review also its
  full text in 01-raw/; a metric's value and statement; a pointer's value.
- A pointer's place is the profile entry it points into: resume:/work/1/...
  is in /work/1, resume:/projects/0/... in /projects/0.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rcore import numbers, sources, wsio
from rcore.profile import is_date
from rcore.raw import RawReader

from .common import Inputs

OPEN_START, ONGOING = (0, 0), (9999, 99)
_PLACE = re.compile(r"^(?:resume|wizard):/(work|projects)/(0|[1-9][0-9]*)(?:/|$)")


def month(value, end: bool = False) -> tuple[int, int] | None:
    """(year, month) of a YYYY, YYYY-MM or YYYY-MM-DD date, or None when value is not a date.

    A year alone is its first month, or with end its last.
    """
    if not is_date(value):
        return None
    parts = value.split("-")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else (12 if end else 1)


def job_months(job: dict) -> tuple[tuple[int, int], tuple[int, int]]:
    return month(job.get("startDate")) or OPEN_START, month(job.get("endDate"), end=True) or ONGOING


def project_months(project: dict) -> tuple[tuple[int, int], tuple[int, int]]:
    return month(project["start"]) or OPEN_START, month(project["end"], end=True) or ONGOING


def overlaps(job: dict, project: dict) -> bool:
    (job_start, job_end), (start, end) = job_months(job), project_months(project)
    return job_start <= end and start <= job_end


def span(entry: dict) -> str:
    """'2019-06 to 2022-12', '2023-01 to present', or '' for an entry without dates."""
    start, end = entry.get("startDate"), entry.get("endDate")
    if start is None and end is None:
        return ""
    return f"{start or '?'} to {end or 'present'}"


def project_span(project: dict) -> str:
    return f"{project['start']} to {project['end'] or 'present'}"


def pointer_place(ref: str) -> tuple[str, int] | None:
    """('work', 1) for resume:/work/1/highlights/0, ('projects', 0) for a profile project; else None."""
    match = _PLACE.match(ref)
    return (match.group(1), int(match.group(2))) if match else None


def x_field(ref: str) -> str | None:
    """The x- field a resume: or wizard: pointer goes through (x-lines), if any."""
    for prefix in ("resume:", "wizard:"):
        if ref.startswith(prefix):
            return next((t for t in ref[len(prefix):].split("/") if t.startswith("x-")), None)
    return None


def is_review(item: dict) -> bool:
    return item["kind"] == "perf_review"


@dataclass
class Material:
    inputs: Inputs
    projects: list[dict]  # rank order
    by_id: dict[str, dict]  # project ID -> project
    evidence: dict[str, dict]  # evidence ID -> item
    reviews: list[dict]  # performance reviews, in evidence order
    owner: dict[str, str]  # evidence ID -> the project holding it
    jobs: list[dict]  # the effective profile's work entries
    profile_projects: list[dict]  # the effective profile's projects entries
    known: sources.KnownSources
    texts: dict[str, list[str]]  # evidence ID -> its texts
    raw_warnings: list[str]

    @property
    def metrics(self) -> list[dict]:
        return self.inputs.metrics

    def metrics_of(self, project_id: str) -> list[dict]:
        return [m for m in self.metrics if m["project_id"] == project_id]

    def metric(self, metric_id: str) -> dict | None:
        return next((m for m in self.metrics if m["id"] == metric_id), None)

    def items_of(self, project: dict) -> list[dict]:
        """A project's evidence items, in evidence order (by date)."""
        held = set(project["evidence_ids"])
        return [item for item in self.evidence.values() if item["id"] in held]

    def jobs_for(self, project: dict) -> list[int]:
        """The jobs a project overlaps, as indexes of the effective profile's work."""
        return [i for i, job in enumerate(self.jobs) if overlaps(job, project)]

    def job_label(self, index: int) -> str:
        """'/work/1 (2019-06 to 2022-12)'."""
        dates = span(self.jobs[index]) or "no dates"
        return f"/work/{index} ({dates})"

    def source_texts(self, ref: str) -> list[str]:
        """What a source reference says, for the number check; [] when it does not resolve."""
        if ref.startswith("ev_"):
            return self.texts.get(ref, [])
        if ref.startswith("metric:"):
            metric = self.metric(ref[len("metric:"):])
            return [numbers.digits(metric["value"]), metric["statement"]] if metric else []
        for prefix, doc in (("resume:", self.known.profile), ("wizard:", self.known.wizard)):
            if ref.startswith(prefix):
                try:
                    value = wsio.resolve_pointer(doc, ref[len(prefix):])
                except KeyError:
                    return []
                if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                    return []
                return [value if isinstance(value, str) else numbers.digits(value)]
        return []

    def story_texts(self, project: dict) -> list[str]:
        """What a project's story may draw numbers from: its evidence, the reviews, its metrics."""
        found = [t for e in project["evidence_ids"] for t in self.texts.get(e, [])]
        found += [t for review in self.reviews for t in self.texts[review["id"]]]
        for metric in self.metrics_of(project["id"]):
            found += [numbers.digits(metric["value"]), metric["statement"]]
        return found

    def required_pointers(self) -> list[str]:
        """Imported resume text every run must cite: each highlight of a work or projects entry,
        and the description of a projects entry without highlights."""
        profile = self.inputs.profile or {}
        required = []
        for section in ("work", "projects"):
            entries = profile.get(section)
            for i, entry in enumerate(entries if isinstance(entries, list) else []):
                if not isinstance(entry, dict):
                    continue
                highlights = entry.get("highlights")
                if isinstance(highlights, list) and highlights:
                    required += [f"resume:/{section}/{i}/highlights/{j}" for j, text in enumerate(highlights)
                                 if isinstance(text, str) and text.strip()]
                elif section == "projects" and isinstance(entry.get("description"), str) \
                        and entry["description"].strip():
                    required.append(f"resume:/projects/{i}/description")
        return required

    def gone_metrics(self) -> list[dict]:
        """Metrics whose project is not in 04-projects/projects.json."""
        return [m for m in self.metrics if m["project_id"] not in self.by_id]

    def homeless(self) -> list[dict]:
        """Projects no job overlaps."""
        return [p for p in self.projects if not self.jobs_for(p)]


def _entries(doc: dict, section: str) -> list[dict]:
    entries = doc.get(section)
    return [e if isinstance(e, dict) else {} for e in entries] if isinstance(entries, list) else []


def build(workspace: Path, inputs: Inputs) -> Material:
    projects = sorted(inputs.projects, key=lambda p: p["rank"])
    effective = inputs.effective
    reader, texts, warnings = RawReader(workspace), {}, []
    for item in inputs.evidence:
        found = [item["title"], item.get("excerpt") or ""]
        if is_review(item) and item.get("raw_ref") is None:
            warnings.append(f"{item['id']}: has no raw_ref; its excerpt stands in for the review's text")
        elif is_review(item):
            text, why = reader.text(item["raw_ref"])
            if text is None:
                warnings.append(f"{item['id']}: the raw record {item['raw_ref']} {why}; "
                                "its excerpt stands in for the review's text")
            else:
                found.append(text)
        texts[item["id"]] = found
    known = sources.KnownSources(evidence_ids={e["id"] for e in inputs.evidence},
                                 metric_ids={m["id"] for m in inputs.metrics},
                                 profile=inputs.profile or {}, wizard=inputs.wizard)
    return Material(
        inputs=inputs, projects=projects, by_id={p["id"]: p for p in projects},
        evidence={e["id"]: e for e in inputs.evidence},
        reviews=[e for e in inputs.evidence if is_review(e)],
        owner={e: p["id"] for p in projects for e in p["evidence_ids"]},
        jobs=_entries(effective, "work"), profile_projects=_entries(effective, "projects"),
        known=known, texts=texts, raw_warnings=warnings)
