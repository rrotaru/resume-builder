"""The analyze command lines end to end: signals.py, match_projects.py and decide.py."""
import shutil

import decide
import match_projects
import pytest
import signals

from analyze_samples import eid, group, item, make_workspace, write_decisions, write_draft
from conftest import FIXTURE_WORKSPACE
from rcore import ids, stages, validation, wsio

FALCON = "pj_da2a2b53"
FIXTURE_FILES = ("signals.json", "groups.json", "projects.json")


def ws_arg(workspace):
    return ["--workspace", str(workspace)]


def d(n: int) -> str:
    return f"2025-{n:02d}-01T00:00:00Z"


def draft_from_fixture():
    """The fixture's saved groups as the model wrote them: without IDs."""
    saved = wsio.read_json(FIXTURE_WORKSPACE / "04-projects" / "groups.json")
    return [{k: v for k, v in g.items() if k != "id"} for g in saved]


# The fixture -------------------------------------------------------------------

@pytest.mark.parametrize("first_run", [False, True])
def test_fixture_end_to_end(workspace, capsys, first_run):
    if first_run:
        shutil.rmtree(workspace / "04-projects")
    assert signals.main(ws_arg(workspace)) == 0
    out = capsys.readouterr().out
    assert out.startswith("02-evidence: 4 items, 1 cluster (1 with two or more items), 1 performance review\n")
    assert out.endswith("wrote 04-projects.tmp/signals.json\n")
    assert (workspace / "04-projects.tmp" / "signals.json").read_bytes() == \
        (FIXTURE_WORKSPACE / "04-projects" / "signals.json").read_bytes()
    write_draft(workspace, draft_from_fixture())

    assert match_projects.main([*ws_arg(workspace), "--commit"]) == 0
    out = capsys.readouterr().out
    carried = "carried from the last run (similarity 1.00)" if not first_run else "new"
    assert f" 1. {FALCON}  Project Falcon checkout latency  [lead, cross-team, 2025-02 to 2025-05]  " \
           "metric prompt\n" in out
    assert f"    id: {carried}\n    decisions: set_role\n" in out
    assert out.endswith("committed 04-projects: 1 project (0 excluded), metric prompts for 1\n")
    for name in FIXTURE_FILES:
        assert (workspace / "04-projects" / name).read_bytes() == \
            (FIXTURE_WORKSPACE / "04-projects" / name).read_bytes(), name
    meta = wsio.read_json(workspace / "04-projects" / "_stage.json")
    assert sorted(meta["inputs"]) == ["01-raw", "02-evidence/evidence.jsonl", "config.json",
                                      "decisions/projects.json"]
    assert meta["extra"] == {"projects": 1, "excluded": 0, "metric_prompts": 1, "carried": int(not first_run),
                             "new": int(first_run), "decisions": 1, "unassigned": 1}
    assert validation.validate_workspace(workspace) == []
    assert stages.status(workspace)["04-projects"] == "fresh"
    projects = {p["id"] for p in wsio.read_json(workspace / "04-projects" / "projects.json")}
    named = {b["project_id"] for b in wsio.read_json(workspace / "06-bullets" / "bullets.json")} - {None}
    named |= {m["project_id"] for m in wsio.read_json(workspace / "decisions" / "metrics.json")}
    assert named <= projects


def test_a_decision_change_makes_the_stage_stale(workspace, capsys):
    assert signals.main(ws_arg(workspace)) == 0
    write_draft(workspace, draft_from_fixture())
    assert match_projects.main([*ws_arg(workspace), "--commit"]) == 0
    assert decide.main([*ws_arg(workspace), "set-scope", FALCON, "org"]) == 0
    assert stages.status(workspace)["04-projects"] == "stale"


# signals.py --------------------------------------------------------------------

def test_signals_needs_evidence(workspace, capsys):
    (workspace / "02-evidence" / "evidence.jsonl").write_text("", encoding="utf-8")
    assert signals.main(ws_arg(workspace)) == 1
    err = capsys.readouterr().err
    assert "error: 02-evidence/evidence.jsonl has no items; run /resume-builder:collect first" in err
    assert not (workspace / "04-projects.tmp").exists()
    shutil.rmtree(workspace / "02-evidence")
    assert signals.main(ws_arg(workspace)) == 1
    assert "02-evidence/evidence.jsonl not found" in capsys.readouterr().err


def test_signals_needs_valid_evidence_and_config(workspace, capsys):
    records = wsio.read_jsonl(workspace / "02-evidence" / "evidence.jsonl")
    records[0]["kind"] = "meeting"
    wsio.write_jsonl(workspace / "02-evidence" / "evidence.jsonl", records)
    assert signals.main(ws_arg(workspace)) == 1
    assert "02-evidence/evidence.jsonl: record 1: $.kind:" in capsys.readouterr().err
    (workspace / "config.json").unlink()
    assert signals.main(ws_arg(workspace)) == 1
    assert "config.json not found; run /resume-builder:init first" in capsys.readouterr().err


def test_signals_needs_evidence_timestamps(workspace, capsys):
    records = wsio.read_jsonl(workspace / "02-evidence" / "evidence.jsonl")
    records[0]["created_at"] = "2025-02-30T00:00:00Z"
    records[1]["closed_at"] = "2025-03-11"
    wsio.write_jsonl(workspace / "02-evidence" / "evidence.jsonl", records)
    assert signals.main(ws_arg(workspace)) == 1
    err = capsys.readouterr().err
    assert "error: 02-evidence/evidence.jsonl: record 1: created_at '2025-02-30T00:00:00Z' is not " \
           "YYYY-MM-DDTHH:MM:SSZ" in err
    assert "error: 02-evidence/evidence.jsonl: record 2: closed_at '2025-03-11' is not YYYY-MM-DDTHH:MM:SSZ" in err


def test_signals_warns_about_missing_raw_files(workspace, capsys):
    (workspace / "01-raw" / "jira.jsonl").unlink()
    assert signals.main(ws_arg(workspace)) == 0
    assert "warning: 01-raw/jira.jsonl: not found; its items add no people to the signals\n" in \
        capsys.readouterr().out


# match_projects.py -------------------------------------------------------------

def test_match_needs_signals_and_a_draft(workspace, capsys):
    assert match_projects.main(ws_arg(workspace)) == 1
    assert "error: 04-projects.tmp/ not found; run signals.py first" in capsys.readouterr().err
    stages.begin(workspace, "04-projects")
    assert match_projects.main(ws_arg(workspace)) == 1
    assert "error: 04-projects.tmp/signals.json: not found; run signals.py" in capsys.readouterr().err
    assert signals.main(ws_arg(workspace)) == 0
    assert match_projects.main(ws_arg(workspace)) == 1
    assert "error: 04-projects.tmp/groups.json: not found; write the groups first" in capsys.readouterr().err


def test_match_refuses_evidence_changed_since_signals(workspace, capsys):
    assert signals.main(ws_arg(workspace)) == 0
    write_draft(workspace, draft_from_fixture())
    records = wsio.read_jsonl(workspace / "02-evidence" / "evidence.jsonl")
    wsio.write_jsonl(workspace / "02-evidence" / "evidence.jsonl", records[:3])
    assert match_projects.main(ws_arg(workspace)) == 1
    assert "02-evidence/evidence.jsonl changed since signals.py ran; run signals.py and group again" in \
        capsys.readouterr().err


@pytest.mark.parametrize("change", ["raw", "username"])
def test_match_refuses_signals_that_config_or_raw_changes_made_stale(workspace, capsys, change):
    """A changed raw record or username leaves the evidence alone but changes the signals."""
    assert signals.main(ws_arg(workspace)) == 0
    write_draft(workspace, draft_from_fixture())
    if change == "raw":  # PAY-42's reporter becomes the engineer, so they created the epic
        raw = workspace / "01-raw" / "jira.jsonl"
        text = raw.read_text(encoding="utf-8")
        raw.write_text(text.replace('"Reporter": "priya.shah"', '"Reporter": "jordan.rivera"', 1), encoding="utf-8")
    else:  # the Jira username becomes PAY-42's reporter
        cfg = wsio.read_json(workspace / "config.json")
        cfg["sources"][1]["username"] = "priya.shah"
        wsio.write_json(workspace / "config.json", cfg)
    capsys.readouterr()
    assert match_projects.main([*ws_arg(workspace), "--commit"]) == 1
    assert "error: 04-projects.tmp/signals.json no longer matches config.json and 01-raw/ (a username or a raw " \
           "record changed since signals.py ran); run signals.py and group again" in capsys.readouterr().err
    assert not (workspace / "04-projects" / "_stage.json").exists()
    assert signals.main(ws_arg(workspace)) == 0
    assert wsio.read_json(workspace / "04-projects.tmp" / "signals.json")["clusters"][0]["epics_created"] == \
        ["ev_99a74656"]
    write_draft(workspace, draft_from_fixture())
    assert match_projects.main([*ws_arg(workspace), "--commit"]) == 0


def test_match_accepts_config_changes_that_leave_the_signals_alone(workspace, capsys):
    assert signals.main(ws_arg(workspace)) == 0
    write_draft(workspace, draft_from_fixture())
    cfg = wsio.read_json(workspace / "config.json")
    cfg["target_role"] = "Staff Engineer"
    wsio.write_json(workspace / "config.json", cfg)
    assert match_projects.main([*ws_arg(workspace), "--commit"]) == 0


def test_match_prints_group_problems_and_writes_nothing(workspace, capsys):
    assert signals.main(ws_arg(workspace)) == 0
    draft = draft_from_fixture()
    draft[0]["evidence_ids"].append("ev_cbf558fa")
    write_draft(workspace, draft)
    capsys.readouterr()
    assert match_projects.main([*ws_arg(workspace), "--commit"]) == 1
    out, err = capsys.readouterr()
    assert out.splitlines() == [
        "04-projects.tmp/groups.json: /0/evidence_ids/3: ev_cbf558fa is a performance review; reviews are never "
        "part of a project",
        "  fix: edit 04-projects.tmp/groups.json: list each evidence ID from 02-evidence/evidence.jsonl in at most "
        "one group, leave out performance reviews, and rank the groups 1 to n.",
    ]
    assert "groups check failed: 1 problem; 04-projects not written" in err
    assert not (workspace / "04-projects.tmp" / "projects.json").exists()


def test_match_rejects_an_invalid_decisions_file(workspace, capsys):
    assert signals.main(ws_arg(workspace)) == 0
    write_draft(workspace, draft_from_fixture())
    write_decisions(workspace, [{"project_id": FALCON, "action": "rename"}])
    capsys.readouterr()
    assert match_projects.main(ws_arg(workspace)) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"decisions/projects.json: decision 1 (rename {FALCON} to ''): needs name"
    assert out[1].startswith("  fix: record project decisions only with decide.py")
    write_decisions(workspace, [{"project_id": FALCON, "action": "promote"}])
    assert match_projects.main(ws_arg(workspace)) == 1
    assert "decisions/projects.json: $[0].action: 'promote' is not one of" in capsys.readouterr().out


def test_match_rejects_metric_settings_that_do_not_fit(workspace, capsys):
    cfg = wsio.read_json(workspace / "config.json")
    cfg["metric_prompts"] = {"percent": 0.3, "min": 5, "max": 2}
    wsio.write_json(workspace / "config.json", cfg)
    assert signals.main(ws_arg(workspace)) == 0
    write_draft(workspace, draft_from_fixture())
    assert match_projects.main(ws_arg(workspace)) == 1
    assert "error: config.json metric prompts: minimum 5 is greater than maximum 2" in capsys.readouterr().err


def test_orphans_block_the_commit(workspace, capsys):
    before = (workspace / "04-projects" / "projects.json").read_bytes()
    assert signals.main(ws_arg(workspace)) == 0
    write_draft(workspace, draft_from_fixture())
    decisions = wsio.read_json(workspace / "decisions" / "projects.json")
    decisions.append({"project_id": "pj_0000abcd", "action": "exclude", "evidence_ids": ["ev_191cc8ce"]})
    write_decisions(workspace, decisions)
    capsys.readouterr()
    for args in ([], ["--commit"]):
        assert match_projects.main([*ws_arg(workspace), *args]) == 3
        out, err = capsys.readouterr()
        assert out.splitlines()[-2:] == [
            "orphaned: decision 2 (exclude pj_0000abcd): pj_0000abcd is not a project in this run; closest is "
            f"{FALCON} 'Project Falcon checkout latency' (1 of its 1 items)",
            "  fix: re-link it to a project with decide.py relink 2 PJ, or discard it with decide.py discard 2",
        ]
        assert "decisions: 1 applied, 1 orphaned" in out
        assert "1 orphaned decision: re-link or discard each one; 04-projects not committed" in err
        assert (workspace / "04-projects.tmp" / "projects.json").is_file()
        assert (workspace / "04-projects" / "projects.json").read_bytes() == before
        assert not (workspace / "04-projects" / "_stage.json").exists()


def test_metric_warnings(workspace, capsys):
    metrics = wsio.read_json(workspace / "decisions" / "metrics.json")
    metrics.append({"id": "m_2", "project_id": "pj_0000abcd", "value": 3, "unit": "x", "statement": "3x"})
    wsio.write_json(workspace / "decisions" / "metrics.json", metrics)
    assert signals.main(ws_arg(workspace)) == 0
    write_draft(workspace, draft_from_fixture())
    assert match_projects.main(ws_arg(workspace)) == 0
    assert "warning: decisions/metrics.json m_2: pj_0000abcd is not a project in this run; the wizard re-links " \
           "or removes this metric\n" in capsys.readouterr().out
    assert decide.main([*ws_arg(workspace), "exclude", FALCON]) == 0
    assert match_projects.main(ws_arg(workspace)) == 0
    out = capsys.readouterr().out
    assert f"warning: decisions/metrics.json m_1: {FALCON} was excluded by decision 2;" in out
    assert "0 projects; metric prompts for the top 0" in out
    assert f"excluded: {FALCON} 'Project Falcon checkout latency' (decision 2)" in out


# Metric prompts ----------------------------------------------------------------

def _many(tmp_path, count, **cfg):
    evidence = [item(n, "pr", created=d(1)) for n in range(1, count + 1)]
    ws = make_workspace(tmp_path, evidence, **cfg)
    assert signals.main(ws_arg(ws)) == 0
    write_draft(ws, [group([n], n) for n in range(1, count + 1)])
    return ws


def test_metric_prompts_count_the_projects_left_after_exclusions(tmp_path, capsys):
    ws = _many(tmp_path, 11)
    write_decisions(ws, [{"project_id": ids.project_id([eid(1)]), "action": "exclude"}])
    assert match_projects.main(ws_arg(ws)) == 0
    projects = wsio.read_json(ws / "04-projects.tmp" / "projects.json")
    assert [p["rank"] for p in projects] == list(range(1, 11))
    assert [p["metric_prompt"] for p in projects] == [True] * 3 + [False] * 7
    assert projects[0]["id"] == ids.project_id([eid(2)])


def test_metric_prompts_use_the_config_settings(tmp_path, capsys):
    ws = _many(tmp_path, 10, metric_prompts={"percent": 0.5, "min": 1, "max": 20})
    assert match_projects.main(ws_arg(ws)) == 0
    assert sum(p["metric_prompt"] for p in wsio.read_json(ws / "04-projects.tmp" / "projects.json")) == 5


# Runs --------------------------------------------------------------------------

def _run_workspace(tmp_path):
    evidence = [item(1, "epic", created=d(1), closed=d(6)), item(2, "ticket", links=[1], created=d(2)),
                item(3, "pr", links=[2], created=d(3), closed=d(4)), item(4, "pr", created=d(4)),
                item(5, "pr", links=[4], created=d(5)), item(6, "pr", created=d(6)),
                item(7, "ticket", created=d(7)), item(8, "pr", links=[7], created=d(8)),
                item(9, "perf_review", links=[3], created=d(9))]
    return make_workspace(tmp_path, evidence)


def _first_run_draft():
    return [group([1, 2], 1, name="Alpha"), group([3, 4, 5], 2, name="Beta"), group([6], 3, name="Gamma"),
            group([7, 8], 4, name="Delta")]


A, B = ids.project_id([eid(1), eid(2)]), ids.project_id([eid(3), eid(4), eid(5)])
C, D = ids.project_id([eid(6)]), ids.project_id([eid(7), eid(8)])
PART = ids.project_id([eid(8)])


def _projects(ws):
    return [(p["id"], p["internal_name"], p["role"], p["evidence_ids"])
            for p in wsio.read_json(ws / "04-projects" / "projects.json")]


def test_runs_keep_ids_and_decisions(tmp_path, capsys):
    ws = _run_workspace(tmp_path)
    assert signals.main(ws_arg(ws)) == 0
    write_draft(ws, _first_run_draft())
    assert match_projects.main(ws_arg(ws)) == 0
    for args in (["merge", A, "--with", B], ["exclude", C], ["split", D, "--group", eid(8)]):
        assert decide.main([*ws_arg(ws), *args]) == 0
    assert match_projects.main(ws_arg(ws)) == 0
    for args in (["rename", PART, "--name", "Eighth", "--summary", "Item eight."], ["set-role", A, "lead"],
                 ["set-rank", PART, "1"]):
        assert decide.main([*ws_arg(ws), *args]) == 0
    assert match_projects.main([*ws_arg(ws), "--commit"]) == 0
    first = _projects(ws)
    assert first == [(PART, "Eighth", "core", [eid(8)]),
                     (A, "Alpha", "lead", [eid(n) for n in range(1, 6)]),
                     (D, "Delta", "core", [eid(7)])]
    assert wsio.read_json(ws / "04-projects" / "projects.json")[0]["summary"] == "Item eight."

    # Second run: more evidence, and the model keeps its grouping. Every ID and decision carries over.
    evidence = wsio.read_jsonl(ws / "02-evidence" / "evidence.jsonl")
    evidence.append(item(10, "pr", links=[4], created=d(10)))
    wsio.write_jsonl(ws / "02-evidence" / "evidence.jsonl", evidence)
    assert stages.status(ws)["04-projects"] == "stale"
    assert signals.main(ws_arg(ws)) == 0
    draft = _first_run_draft()
    draft[1]["evidence_ids"].append(eid(10))
    write_draft(ws, draft)
    capsys.readouterr()
    assert match_projects.main([*ws_arg(ws), "--commit"]) == 0
    assert "IDs: 4 groups carried from the last run, 0 new" in capsys.readouterr().out
    second = _projects(ws)
    assert [p[:3] for p in second] == [p[:3] for p in first]
    assert second[1][3] == [eid(n) for n in (1, 2, 3, 4, 5, 10)]

    # Third run: the model groups Alpha and Beta together itself. The group takes Beta's ID (the larger
    # overlap), so decisions about Alpha are orphaned and point at it.
    assert signals.main(ws_arg(ws)) == 0
    write_draft(ws, [group([1, 2, 3, 4, 5, 10], 1, name="Alpha and Beta"), group([6], 2, name="Gamma"),
                     group([7, 8], 3, name="Delta")])
    capsys.readouterr()
    assert match_projects.main([*ws_arg(ws), "--commit"]) == 3
    out = capsys.readouterr().out
    assert f"orphaned: decision 1 (merge {A} with {B}): {A} is not a project in this run; closest is {B} " \
           "'Alpha and Beta' (2 of its 2 items)" in out
    assert f"orphaned: decision 5 (set_role {A} lead): {A} is not a project in this run; closest is {B}" in out
    assert decide.main([*ws_arg(ws), "relink", "1", B]) == 1
    assert "error: a project cannot merge with itself" in capsys.readouterr().err
    assert decide.main([*ws_arg(ws), "discard", "1"]) == 0
    assert decide.main([*ws_arg(ws), "list"]) == 0
    assert capsys.readouterr().out.splitlines()[-5:] == [
        f"1. exclude {C}", f"2. split 1 group off {D}", f"3. rename {PART} to 'Eighth'", f"4. set_role {A} lead",
        f"5. set_rank {PART} 1"]
    assert match_projects.main(ws_arg(ws)) == 3
    assert decide.main([*ws_arg(ws), "relink", "4", B]) == 0
    assert capsys.readouterr().out.splitlines()[-2] == f"re-linked decision 4 as decision 5: set_role {B} lead"
    assert match_projects.main([*ws_arg(ws), "--commit"]) == 0
    assert [p[:3] for p in _projects(ws)] == [(PART, "Eighth", "core"), (B, "Alpha and Beta", "lead"),
                                               (D, "Delta", "core")]


def test_reuse_the_committed_grouping(tmp_path, capsys):
    ws = _run_workspace(tmp_path)
    assert signals.main(ws_arg(ws)) == 0
    write_draft(ws, _first_run_draft())
    assert match_projects.main([*ws_arg(ws), "--commit"]) == 0
    assert decide.main([*ws_arg(ws), "set-rank", D, "1"]) == 0
    stages.begin(ws, "04-projects", from_current=True)
    capsys.readouterr()
    assert match_projects.main([*ws_arg(ws), "--commit"]) == 0
    assert "IDs: 4 groups carried from the last run, 0 new" in capsys.readouterr().out
    assert [p[0] for p in _projects(ws)] == [D, A, B, C]
    assert wsio.read_json(ws / "04-projects" / "_stage.json")["extra"]["carried"] == 4


# decide.py ---------------------------------------------------------------------

def test_decide_needs_projects(tmp_path, capsys):
    ws = _run_workspace(tmp_path)
    assert decide.main([*ws_arg(ws), "list"]) == 0
    assert capsys.readouterr().out == "no project decisions\n"
    assert decide.main([*ws_arg(ws), "exclude", A]) == 1
    assert "error: no projects to decide about yet; run signals.py and match_projects.py first" in \
        capsys.readouterr().err
    assert not (ws / "decisions" / "projects.json").exists()


def test_decide_prefers_the_checkpoint_in_progress(workspace, capsys):
    assert signals.main(ws_arg(workspace)) == 0
    write_draft(workspace, [{**draft_from_fixture()[0], "evidence_ids": ["ev_191cc8ce"]}])
    assert match_projects.main(ws_arg(workspace)) == 3  # the fixture's set_role names the committed project
    tmp_id = ids.project_id(["ev_191cc8ce"])
    assert decide.main([*ws_arg(workspace), "set-scope", FALCON, "org"]) == 1
    assert f"{FALCON} is not one of the current projects in 04-projects.tmp/projects.json" in \
        capsys.readouterr().err
    assert decide.main([*ws_arg(workspace), "set-scope", tmp_id, "org"]) == 0
    assert capsys.readouterr().out == (f"recorded decision 2: set_scope {tmp_id} org\n"
                                       "run match_projects.py to see the projects with it\n")


def test_decide_commands_and_the_file_they_write(tmp_path, capsys):
    ws = _run_workspace(tmp_path)
    assert signals.main(ws_arg(ws)) == 0
    write_draft(ws, _first_run_draft())
    assert match_projects.main(ws_arg(ws)) == 0
    run = [*ws_arg(ws)]
    assert decide.main([*run, "rename", A, "--name", "First"]) == 0
    assert decide.main([*run, "set-role", B, "supporting"]) == 0
    assert decide.main([*run, "rename", A, "--name", "Alpha One", "--summary", "The first."]) == 0
    assert decide.main([*run, "split", B, "--group", f"{eid(3)}, {eid(4)}", "--group", eid(5)]) == 1
    assert "leave at least one item" in capsys.readouterr().err
    assert decide.main([*run, "split", B, "--group", f"{eid(3)} {eid(4)}"]) == 0
    assert decide.main([*run, "merge", C, "--with", D, A]) == 0
    assert wsio.read_json(ws / "decisions" / "projects.json") == [
        {"project_id": B, "action": "set_role", "role": "supporting", "evidence_ids": [eid(3), eid(4), eid(5)]},
        {"project_id": A, "action": "rename", "name": "Alpha One", "summary": "The first.",
         "evidence_ids": [eid(1), eid(2)]},
        {"project_id": B, "action": "split", "split_groups": [[eid(3), eid(4)]],
         "evidence_ids": [eid(3), eid(4), eid(5)]},
        {"project_id": C, "action": "merge", "merge_with": [D, A], "evidence_ids": [eid(6)]},
    ]
    before = (ws / "decisions" / "projects.json").read_bytes()
    for args, message in ((["set-rank", A, "5"], "rank must be 1 to 4"),
                          (["merge", A, "--with", "pj_0000abcd"], "pj_0000abcd is not one of the current projects"),
                          (["discard", "9"], "there is no decision 9; decide.py list shows them"),
                          (["relink", "0", A], "there is no decision 0")):
        assert decide.main([*run, *args]) == 1
        err = capsys.readouterr().err
        assert message in err and err.endswith("decisions/projects.json unchanged\n")
    assert (ws / "decisions" / "projects.json").read_bytes() == before
    assert decide.main([*run, "discard", "1"]) == 0
    assert capsys.readouterr().out.startswith(f"discarded decision 1: set_role {B} supporting\n")
    assert len(wsio.read_json(ws / "decisions" / "projects.json")) == 3
    with pytest.raises(SystemExit) as exit_info:
        decide.main([*run, "set-role", A, "owner"])
    assert exit_info.value.code == 2


def test_decide_can_discard_a_record_whose_fields_are_wrong(tmp_path, capsys):
    ws = _run_workspace(tmp_path)
    assert signals.main(ws_arg(ws)) == 0
    write_draft(ws, _first_run_draft())
    write_decisions(ws, [{"project_id": A, "action": "rename"}, {"project_id": B, "action": "exclude"}])
    assert decide.main([*ws_arg(ws), "discard", "1"]) == 0
    assert wsio.read_json(ws / "decisions" / "projects.json") == [{"project_id": B, "action": "exclude"}]
