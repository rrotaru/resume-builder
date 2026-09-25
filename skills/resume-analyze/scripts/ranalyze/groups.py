"""The model's project groups (04-projects/groups.json): checks and ID continuity."""
from __future__ import annotations

import copy
from fractions import Fraction

from rcore import ids, schema

from .common import TMP, is_perf_review, shorten

DRAFT = f"{TMP}/groups.json"
FIX = (f"fix: edit {DRAFT}: list each evidence ID from 02-evidence/evidence.jsonl in at most one group, "
       "leave out performance reviews, and rank the groups 1 to n.")
FIELDS = ("id", "internal_name", "summary", "evidence_ids", "role", "scope", "rank", "rank_reasons")
SIMILAR = Fraction(1, 2)


def draft_schema() -> dict:
    """project-groups.schema.json with id optional and unchecked: match_projects.py replaces any id."""
    spec = copy.deepcopy(schema.load_schema("project-groups"))
    spec["items"]["required"] = [key for key in spec["items"]["required"] if key != "id"]
    spec["items"]["properties"]["id"] = {}
    return spec


def check(groups, evidence_by_id: dict[str, dict]) -> list[str]:
    """Problems with the model's draft, one line each."""
    errors = schema.validate(groups, draft_schema())
    if errors:
        return [f"{DRAFT}: {e}" for e in errors]
    problems = []
    owner: dict[str, int] = {}
    for g, group in enumerate(groups):
        for e, evidence_id in enumerate(group["evidence_ids"]):
            where = f"{DRAFT}: /{g}/evidence_ids/{e}"
            item = evidence_by_id.get(evidence_id)
            if item is None:
                problems.append(f"{where}: {evidence_id} is not in 02-evidence/evidence.jsonl")
                continue
            if is_perf_review(item):
                problems.append(f"{where}: {evidence_id} is a performance review; reviews are never part of a "
                                "project")
                continue
            if evidence_id in owner:
                first = owner[evidence_id]
                other = "earlier in this group" if first == g else \
                    f"also in /{first} ({shorten(groups[first]['internal_name'])!r})"
                problems.append(f"{where}: {evidence_id} is {other}")
                continue
            owner[evidence_id] = g
    ranks = sorted(group["rank"] for group in groups)
    if ranks != list(range(1, len(groups) + 1)):
        problems.append(f"{DRAFT}: ranks must be 1 to {len(groups)}, each once (found "
                        f"{', '.join(map(str, ranks))})")
    return problems


def cluster_notes(groups: list[dict], clusters: list[dict]) -> list[str]:
    """A note for each cluster of two or more items that is partly in a group and partly in none."""
    grouped = {evidence_id: g["internal_name"] for g in groups for evidence_id in g["evidence_ids"]}
    notes = []
    for cluster in clusters:
        members = cluster["evidence_ids"]
        left_out = [e for e in members if e not in grouped]
        if len(members) > 1 and left_out and len(left_out) < len(members):
            names = sorted({grouped[e] for e in members if e in grouped})
            notes.append(f"cluster {cluster['id']} ({shorten(cluster['label'])!r}) is partly grouped: "
                         f"{len(members) - len(left_out)} of its {len(members)} items are in "
                         f"{', '.join(repr(shorten(n)) for n in names)}; not in any group: {', '.join(left_out)}")
    return notes


def jaccard(a: set, b: set) -> Fraction:
    union = len(a | b)
    return Fraction(len(a & b), union) if union else Fraction(0)


def unique_id(evidence_ids, taken: set[str]) -> str:
    """ids.project_id of the evidence, or of the evidence plus "#1", "#2", ... when that ID is taken."""
    evidence_ids = list(evidence_ids)
    candidate, salt = ids.project_id(evidence_ids), 0
    while candidate in taken:
        salt += 1
        candidate = ids.project_id([*evidence_ids, f"#{salt}"])
    return candidate


def assign_ids(groups: list[dict], previous: list[dict]) -> list[tuple[str, str | None, Fraction | None]]:
    """(id, previous id matched or None, similarity) for each group, in the order given.

    Pairs with a Jaccard similarity of 0.5 or more are taken best first (similarity,
    then overlap, then the new group's rank, then the previous ID), one-to-one. A
    matched group takes the previous ID; any other gets ids.project_id of its evidence.
    """
    new_sets = [set(g["evidence_ids"]) for g in groups]
    pairs = []
    for i, members in enumerate(new_sets):
        for old in previous:
            similarity = jaccard(members, set(old["evidence_ids"]))
            if similarity >= SIMILAR:
                pairs.append((-similarity, -len(members & set(old["evidence_ids"])), groups[i]["rank"], old["id"],
                              i, similarity))
    matched: dict[int, tuple[str, Fraction]] = {}
    used: set[str] = set()
    for *_, old_id, i, similarity in sorted(pairs):
        if i not in matched and old_id not in used:
            matched[i] = (old_id, similarity)
            used.add(old_id)
    result: list[tuple[str, str | None, Fraction | None] | None] = [None] * len(groups)
    taken = set(used)
    for i, _ in sorted(enumerate(groups), key=lambda pair: pair[1]["rank"]):
        if i in matched:
            old_id, similarity = matched[i]
            result[i] = (old_id, old_id, similarity)
        else:
            new_id = unique_id(new_sets[i], taken)
            taken.add(new_id)
            result[i] = (new_id, None, None)
    return result  # type: ignore[return-value]


def with_ids(groups: list[dict], assigned) -> list[dict]:
    """The groups as stored: id first, evidence sorted, in rank order."""
    stored = []
    for group, (group_id, _, _) in zip(groups, assigned, strict=True):
        record = {"id": group_id, **{k: group[k] for k in FIELDS[1:]}}
        record["evidence_ids"] = sorted(group["evidence_ids"])
        stored.append(record)
    return sorted(stored, key=lambda g: g["rank"])
