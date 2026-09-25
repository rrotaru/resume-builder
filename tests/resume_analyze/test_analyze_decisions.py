"""Project decisions: record checks, applying them in order, orphans, and decide.py's edits."""
import pytest

from analyze_samples import eid
from ranalyze import decisions
from ranalyze.common import AnalyzeError
from ranalyze.decisions import Project
from rcore import ids

A, B, C, D = "pj_aaaaaaaa", "pj_bbbbbbbb", "pj_cccccccc", "pj_dddddddd"


def projects():
    """Four projects in rank order: A holds items 1-3, B 4-5, C 6, D 7-8."""
    return [Project(A, "Alpha", "a", [eid(1), eid(2), eid(3)], "core", "team", ["ra"]),
            Project(B, "Beta", "b", [eid(4), eid(5)], "lead", "team", ["rb"]),
            Project(C, "Gamma", "c", [eid(6)], "supporting", "team", ["rc", "ra"]),
            Project(D, "Delta", "d", [eid(7), eid(8)], "core", "org", [])]


def ids_of(outcome):
    return [p.id for p in outcome.projects]


# Record checks -------------------------------------------------------------------

def test_record_checks():
    records = [
        {"project_id": A, "action": "rename"},
        {"project_id": A, "action": "merge", "merge_with": []},
        {"project_id": A, "action": "exclude", "name": "x"},
        {"project_id": A, "action": "merge", "merge_with": [A]},
        {"project_id": A, "action": "split", "split_groups": [[eid(1)], []]},
        {"project_id": A, "action": "rename", "name": "N", "summary": "S", "evidence_ids": [eid(1)]},
        {"project_id": A, "action": "set_rank", "rank": 2, "role": "lead"},
    ]
    assert decisions.check_records(records) == [
        f"decisions/projects.json: decision 1 (rename {A} to ''): needs name",
        f"decisions/projects.json: decision 2 (merge {A} with ): merge_with is empty",
        f"decisions/projects.json: decision 3 (exclude {A}): name is not used by exclude",
        f"decisions/projects.json: decision 4 (merge {A} with {A}): a project cannot merge with itself",
        f"decisions/projects.json: decision 5 (split 2 groups off {A}): split group 2 is empty",
        f"decisions/projects.json: decision 7 (set_rank {A} 2): role is not used by set_rank",
    ]


def test_describe():
    assert decisions.describe({"project_id": A, "action": "split", "split_groups": [[eid(1)]]}) == \
        f"split 1 group off {A}"
    assert decisions.describe({"project_id": A, "action": "set_scope", "scope": "org"}) == f"set_scope {A} org"


# Applying ------------------------------------------------------------------------

def test_no_decisions_keep_the_projects():
    outcome = decisions.apply(projects(), [])
    assert ids_of(outcome) == [A, B, C, D]
    assert (outcome.applied, outcome.orphans, outcome.notes) == (0, [], [])


def test_exclude_and_a_later_decision_about_the_excluded_project():
    outcome = decisions.apply(projects(), [{"project_id": B, "action": "exclude"},
                                           {"project_id": B, "action": "set_role", "role": "core"}])
    assert ids_of(outcome) == [A, C, D]
    assert [(p.id, n) for p, n in outcome.excluded] == [(B, 1)]
    [orphan] = outcome.orphans
    assert (orphan.number, orphan.reason) == (2, f"{B} was excluded by decision 1")
    assert outcome.applied == 1


def test_merge_takes_the_best_rank_and_adds_the_reasons():
    outcome = decisions.apply(projects(), [{"project_id": C, "action": "merge", "merge_with": [A, "pj_eeeeeeee"]},
                                           {"project_id": A, "action": "rename", "name": "gone"}])
    assert ids_of(outcome) == [C, B, D]
    merged = outcome.projects[0]
    assert merged.evidence == [eid(1), eid(2), eid(3), eid(6)]
    assert (merged.internal_name, merged.role, merged.rank_reasons) == ("Gamma", "supporting", ["rc", "ra"])
    assert outcome.notes == [f"decision 1 (merge {C} with {A}, pj_eeeeeeee): pj_eeeeeeee is not a project in this "
                             "run; nothing merged from it"]
    assert outcome.orphans[0].reason == f"{A} was merged into {C} by decision 1"
    assert outcome.gone == {A: f"{A} was merged into {C} by decision 1"}


def test_split_adds_parts_right_after_the_project():
    split = {"project_id": A, "action": "split", "split_groups": [[eid(2)], [eid(3), eid(9)], [eid(9)]]}
    outcome = decisions.apply(projects(), [split])
    part2, part3 = ids.project_id([eid(2)]), ids.project_id([eid(3), eid(9)])
    assert ids_of(outcome) == [A, part2, part3, B, C, D]
    assert outcome.projects[0].evidence == [eid(1)]
    second = outcome.projects[1]
    assert (second.internal_name, second.summary, second.evidence, second.role, second.rank_reasons) == \
        ("Alpha (part 2)", "", [eid(2)], "core", [])
    assert second.origin == f"split off {A} by decision 1"
    assert outcome.projects[2].evidence == [eid(3)]
    assert outcome.notes == [f"decision 1 (split 3 groups off {A}): split group 3 names none of {A}'s items; skipped"]


def test_a_later_decision_can_name_a_split_part():
    part = ids.project_id([eid(7)])
    outcome = decisions.apply(projects(), [
        {"project_id": D, "action": "split", "split_groups": [[eid(7)]]},
        {"project_id": part, "action": "rename", "name": "Seventh", "summary": "Item seven."},
        {"project_id": part, "action": "set_rank", "rank": 1},
    ])
    assert ids_of(outcome) == [part, A, B, C, D]
    assert (outcome.projects[0].internal_name, outcome.projects[0].summary) == ("Seventh", "Item seven.")
    assert outcome.projects[0].applied == ["split", "rename", "set_rank"]


def test_a_split_that_would_empty_the_project_is_orphaned():
    outcome = decisions.apply(projects(), [{"project_id": B, "action": "split",
                                            "split_groups": [[eid(4)], [eid(5)]]}])
    assert ids_of(outcome) == [A, B, C, D]
    assert outcome.orphans[0].reason == f"splitting it would leave {B} with no items"
    assert outcome.notes == []


def test_a_split_whose_groups_name_none_of_the_items_does_nothing():
    outcome = decisions.apply(projects(), [{"project_id": B, "action": "split", "split_groups": [[eid(1)]]}])
    assert ids_of(outcome) == [A, B, C, D]
    assert outcome.applied == 1 and len(outcome.notes) == 1


def test_a_split_part_id_that_is_taken_is_salted(monkeypatch):
    real = ids.project_id
    monkeypatch.setattr(ids, "project_id", lambda evidence: B if list(evidence) == [eid(2)] else real(evidence))
    outcome = decisions.apply(projects(), [{"project_id": A, "action": "split", "split_groups": [[eid(2)]]}])
    assert outcome.projects[1].id == real([eid(2), "#1"])


def test_attribute_decisions():
    outcome = decisions.apply(projects(), [
        {"project_id": A, "action": "rename", "name": "Alpha 2"},
        {"project_id": B, "action": "set_role", "role": "supporting"},
        {"project_id": C, "action": "set_scope", "scope": "company"},
    ])
    a, b, c, _ = outcome.projects
    assert (a.internal_name, a.summary, b.role, c.scope) == ("Alpha 2", "a", "supporting", "company")


@pytest.mark.parametrize("rank, order", [(1, [D, A, B, C]), (2, [A, D, B, C]), (9, [A, B, C, D])])
def test_set_rank(rank, order):
    assert ids_of(decisions.apply(projects(), [{"project_id": D, "action": "set_rank", "rank": rank}])) == order


def test_set_rank_moves_a_project_down():
    assert ids_of(decisions.apply(projects(), [{"project_id": A, "action": "set_rank", "rank": 3}])) == [B, C, A, D]


def test_an_unknown_project_is_orphaned_and_the_closest_is_suggested():
    decision = {"project_id": "pj_eeeeeeee", "action": "exclude", "evidence_ids": [eid(4), eid(6), eid(99)]}
    outcome = decisions.apply(projects(), [decision])
    [orphan] = outcome.orphans
    assert orphan.reason == "pj_eeeeeeee is not a project in this run"
    project, shared, total = decisions.closest(decision, outcome.projects)
    assert (project.id, shared, total) == (C, 1, 3)  # C shares 1 of its 1 items: the higher similarity
    assert decisions.closest({"project_id": A, "action": "exclude"}, outcome.projects) is None
    assert decisions.closest({"project_id": A, "action": "exclude", "evidence_ids": [eid(99)]},
                             outcome.projects) is None


# decide.py's edits ---------------------------------------------------------------

CURRENT = [{"id": A, "evidence_ids": [eid(1), eid(2)]}, {"id": B, "evidence_ids": [eid(3)]}]


def test_make_stores_the_evidence_snapshot():
    assert decisions.make(CURRENT, "x", "set_role", A, role="lead") == \
        {"project_id": A, "action": "set_role", "role": "lead", "evidence_ids": [eid(1), eid(2)]}
    assert decisions.make(CURRENT, "x", "rename", B, name="  Beta  ", summary=None) == \
        {"project_id": B, "action": "rename", "name": "Beta", "evidence_ids": [eid(3)]}


@pytest.mark.parametrize("action, project, values, message", [
    ("exclude", C, {}, f"{C} is not one of the current projects in x"),
    ("merge", A, {"merge_with": [C]}, f"{C} is not one of the current projects in x"),
    ("merge", A, {"merge_with": [A]}, "a project cannot merge with itself"),
    ("merge", A, {"merge_with": [B, B]}, "name each project to merge once"),
    ("split", A, {"split_groups": [[eid(3)]]}, f"{eid(3)} is not one of {A}'s items"),
    ("split", A, {"split_groups": [[eid(1)], [eid(1)]]}, f"{eid(1)} is listed twice"),
    ("split", A, {"split_groups": [[eid(1)], [eid(2)]]}, f"leave at least one item in {A}"),
    ("split", A, {"split_groups": [[]]}, "split group 1 is empty"),
    ("set_rank", A, {"rank": 3}, "rank must be 1 to 2"),
    ("set_rank", A, {"rank": 0}, "rank must be 1 to 2"),
    ("rename", A, {"name": " "}, "the name is empty"),
    ("rename", A, {"name": "N", "summary": ""}, "the summary is empty"),
])
def test_make_rejects(action, project, values, message):
    with pytest.raises(AnalyzeError, match=message.replace("(", r"\(")):
        decisions.make(CURRENT, "x", action, project, **values)


def test_add_replaces_an_earlier_decision_of_the_same_kind():
    old = [{"project_id": A, "action": "rename", "name": "One"}, {"project_id": B, "action": "rename", "name": "B"},
           {"project_id": A, "action": "merge", "merge_with": [B]}]
    new = {"project_id": A, "action": "rename", "name": "Two"}
    assert decisions.add(old, new) == [old[1], old[2], new]
    merge = {"project_id": A, "action": "merge", "merge_with": [B]}
    assert decisions.add(old, merge) == [*old, merge]


def test_values_of():
    assert decisions.values_of({"project_id": A, "action": "rename", "name": "N", "evidence_ids": []}) == \
        {"name": "N"}
