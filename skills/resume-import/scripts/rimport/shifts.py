"""Wizard answers that a re-import attaches to a different entry.

decisions/profile.json merges into the imported profile by index (rcore.profile):
wizard item i of an array of objects merges onto imported item i. When a new
import puts a different entry at index i, or an entry where there was none,
the answer silently moves. warnings() names each such answer so the engineer
can review it with the wizard. Only the wizard writes decisions/, so import
reports the shift and does not repair it. The identity fields live in
rcore.profile, so the wizard compares entries the same way.
"""
from __future__ import annotations

from rcore.profile import describe, identity, merged_arrays

REVIEW = "Review it with /resume-builder:wizard."


def _item(array, i: int) -> dict | None:
    if isinstance(array, list) and i < len(array) and isinstance(array[i], dict):
        return array[i]
    return None


def _lookup(doc: dict, pointer: str):
    node = doc
    for part in pointer.strip("/").split("/"):
        node = node.get(part) if isinstance(node, dict) else None
    return node


def warnings(old: dict, new: dict, wizard: dict) -> list[str]:
    """One line per non-empty wizard answer whose imported entry changes with this import."""
    found = []
    for pointer, section, answers in merged_arrays(wizard):
        if not all(isinstance(a, dict) for a in answers):
            continue  # not merged by index
        old_items, new_items = _lookup(old, pointer), _lookup(new, pointer)
        for i, answer in enumerate(answers):
            if not answer:
                continue
            where = f"decisions/profile.json {pointer}/{i}"
            before, after = _item(old_items, i), _item(new_items, i)
            if before is None and after is not None:
                found.append(f"{where} added a {section} entry; after this import it merges into "
                             f"'{describe(section, after)}'. {REVIEW}")
            elif before is not None and after is None:
                found.append(f"{where} was answered for '{describe(section, before)}'; after this import "
                             f"there is no {pointer}/{i}, so the answer adds a new entry. {REVIEW}")
            elif before is not None and identity(section, before) != identity(section, after):
                found.append(f"{where} was answered for '{describe(section, before)}'; after this import "
                             f"{pointer}/{i} is '{describe(section, after)}'. {REVIEW}")
    return found
