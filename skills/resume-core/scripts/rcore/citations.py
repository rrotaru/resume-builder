"""What each source reference says: the texts a claim may rest on.

A bullet's sources are evidence IDs, metrics and pointers into the profile
(see sources.py). resume-write checks that every number in a bullet appears
in its sources, and resume-ats compares a rewrite with its sources, so both
read a reference the same way:

- ev_<id>: the item's title and excerpt; for a performance review also its
  full text in 01-raw/ at raw_ref (raw.RawReader). A review with no raw_ref
  (it is optional), or whose raw record cannot be read, has only its excerpt,
  and a warning says so.
- metric:<id>: the metric's value, written with digits (numbers.digits,
  never an exponent), and its statement.
- resume:<pointer> and wizard:<pointer>: the single string or number it
  points to in 03-profile/profile.json or decisions/profile.json.

Evidence stats (lines and files changed) are not sources. A reference that
does not resolve says nothing ([]).
"""
from __future__ import annotations

from pathlib import Path

from . import numbers, wsio
from .raw import RawReader


def is_review(item: dict) -> bool:
    return item.get("kind") == "perf_review"


class Citations:
    """The texts of each source reference, from the evidence, metrics and profile given."""

    def __init__(self, workspace: Path, evidence: list[dict], metrics: list[dict],
                 profile: dict | None, wizard: dict | None):
        self.metrics = {m["id"]: m for m in metrics}
        self.profile = profile or {}
        self.wizard = wizard or {}
        self.warnings: list[str] = []
        self.evidence: dict[str, list[str]] = {}  # evidence ID -> its texts
        reader = RawReader(workspace)
        for item in evidence:
            found = [item["title"], item.get("excerpt") or ""]
            if is_review(item) and item.get("raw_ref") is None:
                self.warnings.append(f"{item['id']}: has no raw_ref; its excerpt stands in for the review's text")
            elif is_review(item):
                text, why = reader.text(item["raw_ref"])
                if text is None:
                    self.warnings.append(f"{item['id']}: the raw record {item['raw_ref']} {why}; "
                                         "its excerpt stands in for the review's text")
                else:
                    found.append(text)
            self.evidence[item["id"]] = found

    def texts(self, ref: str) -> list[str]:
        """What a source reference says; [] when it does not resolve."""
        if ref.startswith("ev_"):
            return self.evidence.get(ref, [])
        if ref.startswith("metric:"):
            metric = self.metrics.get(ref[len("metric:"):])
            return [numbers.digits(metric["value"]), metric["statement"]] if metric else []
        for prefix, doc in (("resume:", self.profile), ("wizard:", self.wizard)):
            if ref.startswith(prefix):
                try:
                    value = wsio.resolve_pointer(doc, ref[len(prefix):])
                except KeyError:
                    return []
                if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                    return []
                return [value if isinstance(value, str) else numbers.digits(value)]
        return []
