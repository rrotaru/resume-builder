"""decisions/wizard.json: which imported entry each profile answer was given for, and skipped questions.

anchors: {"entry": "/work/1", "answered_for": {"position": ..., "name": ...}}, one
per wizard answer inside an array of objects in decisions/profile.json.
answered_for is rcore.profile.identity of the imported entry at that index when
the answer was given, or null when the answer added an entry past the imported
end. skipped: {"question": "profile:/basics/phone"}; a skip inside an entry
(profile:/work/1/startDate) also stores answered_for and lapses when the
imported entry there changes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from rcore import profile as core_profile

from .common import STATE, check_schema, load, save_json

_ENTRY = re.compile(r"^(/basics/profiles|/[A-Za-z]+)/(0|[1-9][0-9]*)")
MISSING = object()  # no anchor recorded


def entry_of(pointer: str) -> str | None:
    """The array entry a pointer lies in (/work/1 for /work/1/endDate), or None (basics fields)."""
    match = _ENTRY.match(pointer)
    if match is None or match.group(1) == "/basics":
        return None
    return match.group(0)


def split_entry(entry: str) -> tuple[str, str, int]:
    """(array pointer, section, index) of an entry: ("/work", "work", 1) for /work/1."""
    array, _, index = entry.rpartition("/")
    return array, array.rsplit("/", 1)[-1], int(index)


def imported_identity(imported: dict, entry: str):
    """The identity of the imported entry at entry, or None when there is none."""
    array, section, index = split_entry(entry)
    node = imported
    for part in array.strip("/").split("/"):
        node = node.get(part) if isinstance(node, dict) else None
    if isinstance(node, list) and index < len(node):
        return core_profile.identity(section, node[index])
    return None


def _order(entry: str):
    array, _, index = split_entry(entry)
    return array, index


@dataclass
class State:
    anchors: dict[str, dict | None] = field(default_factory=dict)
    skipped: list[dict] = field(default_factory=list)

    def anchor(self, entry: str):
        return self.anchors.get(entry, MISSING)

    def to_json(self) -> dict:
        return {"anchors": [{"entry": e, "answered_for": self.anchors[e]} for e in sorted(self.anchors, key=_order)],
                "skipped": self.skipped}

    def is_skipped(self, question: str, imported: dict) -> bool:
        """True when question was skipped, and a skip inside an entry still names the same imported entry."""
        entry = entry_of(question.partition(":")[2]) if question.startswith("profile:") else None
        for skip in self.skipped:
            if skip["question"] != question:
                continue
            if entry is None or skip.get("answered_for") == imported_identity(imported, entry):
                return True
        return False

    def skip(self, question: str, imported: dict) -> None:
        self.unskip(question)
        record: dict = {"question": question}
        entry = entry_of(question.partition(":")[2]) if question.startswith("profile:") else None
        if entry is not None:
            record["answered_for"] = imported_identity(imported, entry)
        self.skipped.append(record)

    def unskip(self, question: str) -> bool:
        before = len(self.skipped)
        self.skipped = [s for s in self.skipped if s["question"] != question]
        return len(self.skipped) != before


def load_state(workspace: Path) -> State:
    data = load(workspace, STATE, {"anchors": [], "skipped": []})
    return State({a["entry"]: a["answered_for"] for a in data["anchors"]}, list(data["skipped"]))


def save_state(workspace: Path, state: State) -> None:
    data = state.to_json()
    check_schema(data, "wizard-state", STATE)
    save_json(workspace, STATE, data)
