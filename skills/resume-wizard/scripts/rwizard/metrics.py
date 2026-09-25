"""Confirmed metrics in decisions/metrics.json: new IDs, the value in the statement, projects that are gone.

A metric is {id, project_id, value, unit, statement, evidence_ids}. The ID is
m_<n>, one more than the highest numbered ID. The statement must state the
value: some number in it, with thousands separators removed, equals the value
(ignoring its sign). evidence_ids is the project's evidence when the metric was
recorded; it is used only to suggest a project when the metric's project is gone.
"""
from __future__ import annotations

import math
import re

from .common import WizardError, shorten

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_NUMBERED = re.compile(r"^m_([0-9]+)$")


def parse_value(text: str):
    """A metric value from the command line: an int when written without a decimal point or exponent."""
    try:
        value = float(text)
    except ValueError:
        raise WizardError(f"the value {text!r} is not a number") from None
    if not math.isfinite(value):
        raise WizardError(f"the value {text!r} is not a finite number")
    return int(value) if re.fullmatch(r"[+-]?\d+", text.strip()) else value


def states_value(statement: str, value) -> bool:
    for token in _NUMBER.findall(statement):
        try:
            if float(token.replace(",", "")) == abs(float(value)):
                return True
        except ValueError:
            continue
    return False


def next_id(metrics: list[dict]) -> str:
    numbers = [int(m.group(1)) for m in (_NUMBERED.match(x["id"]) for x in metrics) if m]
    return f"m_{max(numbers, default=0) + 1}"


def find(metrics: list[dict], metric_id: str) -> dict:
    found = next((m for m in metrics if m["id"] == metric_id), None)
    if found is None:
        raise WizardError(f"{metric_id} is not in decisions/metrics.json")
    return found


def project(projects: list[dict] | None, project_id: str) -> dict:
    if projects is None:
        raise WizardError("04-projects/projects.json not found; run /resume-builder:analyze first")
    found = next((p for p in projects if p["id"] == project_id), None)
    if found is None:
        raise WizardError(f"{project_id} is not a project in 04-projects/projects.json")
    return found


def why_gone(project_id: str, decisions: list[dict]) -> str:
    """What decisions/projects.json says happened to a project, where it says so."""
    reason = f"{project_id} is not a project in 04-projects/projects.json"
    for n, decision in enumerate(decisions, start=1):
        if decision["action"] == "exclude" and decision["project_id"] == project_id:
            reason = f"{project_id} was excluded by decision {n}"
        elif decision["action"] == "merge" and project_id in decision.get("merge_with", []):
            reason = f"{project_id} was merged into {decision['project_id']} by decision {n}"
    return reason


def closest(metric: dict, projects: list[dict]) -> tuple[dict, int, int] | None:
    """The current project sharing the most of the metric's evidence_ids: (project, shared, snapshot size)."""
    snapshot = set(metric.get("evidence_ids", []))
    best = None
    for candidate in projects:
        items = set(candidate["evidence_ids"])
        shared = len(snapshot & items)
        if not shared:
            continue
        score = (shared, shared / len(snapshot | items), -candidate["rank"])
        if best is None or score > best[0]:
            best = (score, candidate)
    return None if best is None else (best[1], best[0][0], len(snapshot))


def describe(metric: dict) -> str:
    return f"{metric['id']} {shorten(metric['statement'])!r} ({metric['value']} {metric['unit']})".replace(" )", ")")
