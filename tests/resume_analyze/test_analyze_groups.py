"""The model's groups: checks, the partly-grouped cluster note, and ID continuity."""
from fractions import Fraction

import pytest

from analyze_samples import eid, group, item
from ranalyze import groups
from rcore import ids

EVIDENCE = {e["id"]: e for e in [item(n) for n in range(1, 9)] + [item(9, "perf_review")]}
DRAFT = "04-projects.tmp/groups.json"


def stored(numbers, group_id, rank=1):
    return {"id": group_id, **group(numbers, rank)}


# Checks ----------------------------------------------------------------------

def test_a_good_draft_passes():
    assert groups.check([group([1, 2], 1), group([3], 2)], EVIDENCE) == []


def test_an_id_in_the_draft_is_ignored():
    assert groups.check([group([1], 1, id="pj_not-an-id")], EVIDENCE) == []


def test_schema_problems_stop_the_other_checks():
    bad = group([1], 1, role="owner")
    del bad["summary"]
    assert groups.check([bad, group([99], 2)], EVIDENCE) == [
        f"{DRAFT}: $[0]: missing required property 'summary'",
        f"{DRAFT}: $[0].role: 'owner' is not one of ['lead', 'core', 'supporting']",
    ]
    assert groups.check({"groups": []}, EVIDENCE) == [f"{DRAFT}: $: expected array, got dict"]


@pytest.mark.parametrize("draft, expected", [
    ([group([1, 99], 1)], f"{DRAFT}: /0/evidence_ids/1: ev_00000063 is not in 02-evidence/evidence.jsonl"),
    ([group([1, 2], 1, name="Falcon"), group([3, 2], 2)],
     f"{DRAFT}: /1/evidence_ids/1: ev_00000002 is also in /0 ('Falcon')"),
    ([group([1, 2, 1], 1)], f"{DRAFT}: /0/evidence_ids/2: ev_00000001 is earlier in this group"),
    ([group([1, 9], 1)], f"{DRAFT}: /0/evidence_ids/1: ev_00000009 is a performance review; reviews are never "
                         "part of a project"),
    ([group([1], 1), group([2], 1), group([3], 3)], f"{DRAFT}: ranks must be 1 to 3, each once (found 1, 1, 3)"),
    ([group([1], 2)], f"{DRAFT}: ranks must be 1 to 1, each once (found 2)"),
])
def test_each_problem(draft, expected):
    assert groups.check(draft, EVIDENCE) == [expected]


def test_the_fix_line_names_the_draft():
    assert groups.FIX.startswith(f"fix: edit {DRAFT}: ")


def test_note_for_a_partly_grouped_cluster():
    clusters = [{"id": "c1", "label": "Falcon", "evidence_ids": [eid(1), eid(2), eid(3)]},
                {"id": "c2", "label": "Ledger", "evidence_ids": [eid(4), eid(5)]},
                {"id": "c3", "label": "Alone", "evidence_ids": [eid(6)]},
                {"id": "c4", "label": "Split", "evidence_ids": [eid(7), eid(8)]}]
    draft = [group([1, 2], 1, name="Falcon cache"), group([7], 2, name="A"), group([8], 3, name="B")]
    assert groups.cluster_notes(draft, clusters) == [
        "cluster c1 ('Falcon') is partly grouped: 2 of its 3 items are in 'Falcon cache'; not in any group: "
        "ev_00000003"
    ]


# ID continuity -----------------------------------------------------------------

def test_without_a_last_run_ids_come_from_the_evidence():
    draft = [group([2, 1], 1), group([3], 2)]
    assert groups.assign_ids(draft, []) == [(ids.project_id([eid(1), eid(2)]), None, None),
                                            (ids.project_id([eid(3)]), None, None)]


def test_the_same_grouping_keeps_every_id():
    previous = [stored([1, 2], "pj_aaaaaaaa", 1), stored([3], "pj_bbbbbbbb", 2)]
    draft = [group([3], 1), group([1, 2], 2)]
    assert groups.assign_ids(draft, previous) == [("pj_bbbbbbbb", "pj_bbbbbbbb", 1), ("pj_aaaaaaaa", "pj_aaaaaaaa", 1)]


def test_a_group_keeps_its_id_while_it_shares_half_its_items():
    previous = [stored([1, 2, 3], "pj_aaaaaaaa")]
    grown = groups.assign_ids([group([1, 2, 3, 4, 5, 6], 1)], previous)
    assert grown == [("pj_aaaaaaaa", "pj_aaaaaaaa", Fraction(1, 2))]
    changed = groups.assign_ids([group([1, 4, 5], 1)], previous)
    assert changed == [(ids.project_id([eid(1), eid(4), eid(5)]), None, None)]


def test_a_group_takes_the_id_of_the_last_group_it_overlaps_most():
    previous = [stored([1, 2], "pj_aaaaaaaa", 1), stored([3, 4, 5], "pj_bbbbbbbb", 2)]
    draft = [group([6], 1), group([1, 2, 3], 2)]
    assert groups.assign_ids(draft, previous) == [(ids.project_id([eid(6)]), None, None),
                                                  ("pj_aaaaaaaa", "pj_aaaaaaaa", Fraction(2, 3))]


def test_a_tie_at_one_half_goes_to_the_better_ranked_new_group():
    previous = [stored([1, 2, 3, 4], "pj_aaaaaaaa")]
    draft = [group([3, 4], 2), group([1, 2], 1)]
    assert groups.assign_ids(draft, previous) == [(ids.project_id([eid(3), eid(4)]), None, None),
                                                  ("pj_aaaaaaaa", "pj_aaaaaaaa", Fraction(1, 2))]


def test_a_tie_between_two_last_groups_goes_to_the_smaller_id():
    previous = [stored([3, 4], "pj_bbbbbbbb", 1), stored([1, 2], "pj_aaaaaaaa", 2)]
    assert groups.assign_ids([group([1, 2, 3, 4], 1)], previous) == [("pj_aaaaaaaa", "pj_aaaaaaaa",
                                                                      Fraction(1, 2))]


def test_a_taken_id_gets_a_salted_one(monkeypatch):
    real = ids.project_id

    def fake(evidence_ids):
        evidence_ids = list(evidence_ids)
        return "pj_00000000" if not any(e.startswith("#") for e in evidence_ids) else real(evidence_ids)

    monkeypatch.setattr(ids, "project_id", fake)
    result = groups.assign_ids([group([2], 2), group([1], 1)], [])
    assert result == [(real([eid(2), "#1"]), None, None), ("pj_00000000", None, None)]
    assert groups.unique_id([eid(5)], {"pj_00000000", real([eid(5), "#1"])}) == real([eid(5), "#2"])


def test_with_ids_puts_the_id_first_sorts_evidence_and_orders_by_rank():
    draft = [group([3, 1], 2), group([2], 1, id="pj_ignored0")]
    result = groups.with_ids(draft, groups.assign_ids(draft, []))
    assert [list(g)[0] for g in result] == ["id", "id"]
    assert [g["rank"] for g in result] == [1, 2]
    assert result[1]["evidence_ids"] == [eid(1), eid(3)]
    assert result[0]["id"] == ids.project_id([eid(2)])
