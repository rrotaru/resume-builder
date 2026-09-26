"""write.py end to end: begin, --from-current and --commit, on the fixture and on small workspaces."""
import json
import shutil

import apply
import pytest
import write

from conftest import FIXTURE_WORKSPACE
from rcore import stages, validation, wsio
from rrender import gate
from write_samples import PA, PB, METRICS, draft, eid, good_bullets, make_workspace, metric, project

FIXTURE_OUTPUT = """\
write: 1 project (1 story), 3 evidence items in projects, 1 performance review, 1 metric; profile: 2 jobs, 1 project
jobs:
  /work/0  Senior Software Engineer, Northwind Payments  2023-01 to present  projects: pj_da2a2b53
  /work/1  Software Engineer, Tailspin Toys  2019-06 to 2022-12  projects: none
    resume:/work/1/highlights/0  Migrated the order service from PHP to Go, serving 2M requests per day
profile projects:
  /projects/0  ledger-lint  2021-04 to present
    resume:/projects/0/description  Open-source linter for double-entry ledger files; 300 GitHub stars
projects:
 1. pj_da2a2b53  Project Falcon checkout latency  [lead, cross-team, 2025-02 to 2025-05]  story
    Idempotency cache that cut checkout latency for Contoso Bank.
    reasons: authored the core PR and owned the epic; customer-facing latency impact
    job: /work/0
    metric:m_1  p99 checkout latency reduced 40%  (value 40, unit %)
    ev_99a74656  epic, assignee, 2025-02-10  Project Falcon: checkout latency
      Reduce p99 checkout latency for Contoso Bank.
    ev_191cc8ce  pr, author, 2025-03-04  PAY-42: Add Redis idempotency cache for Project Falcon checkout
      Adds a Redis-backed idempotency cache in front of the Contoso Bank checkout path.
    ev_56410ed1  review, reviewer, 2025-04-02  PAY-57: Cache eviction metrics
      Adds eviction metrics for the PAY-42 idempotency cache.
performance reviews:
  ev_cbf558fa  2025-07-15  2025 H1 performance review  full text at 01-raw/reviews.jsonl:1#/items/0
began 06-bullets.tmp/: write 06-bullets.tmp/bullets.json and 06-bullets.tmp/stories.md, then run write.py --commit
"""
FIXTURE_COMMITTED = """\
  b_1  /work/0  pj_da2a2b53  xyz_quantified  Cut p99 checkout latency 40% for Contoso Bank by building a \
Redis-backed idempotency cache for Project Falcon in Go
  b_2  /work/0  xyz  Mentored two new engineers through on-call onboarding
  b_3  /work/1  xyz  Migrated the order service from PHP to Go, serving 2M requests per day
  b_4  /projects/0  xyz  Built ledger-lint, an open-source linter for double-entry ledger files with 300 GitHub stars
  story  pj_da2a2b53  Project Falcon checkout latency
committed 06-bullets: 4 bullets (1 quantified), 1 story
"""


def ws_arg(workspace):
    return ["--workspace", str(workspace)]


def same_as_fixture(workspace, rel):
    return (workspace / rel).read_bytes() == (FIXTURE_WORKSPACE / rel).read_bytes()


def fixture_draft(workspace):
    saved = wsio.read_json(FIXTURE_WORKSPACE / "06-bullets" / "bullets.json")
    wsio.write_json(workspace / "06-bullets.tmp" / "bullets.json", [{k: v for k, v in b.items() if k != "id"}
                                                                   for b in saved])
    shutil.copy(FIXTURE_WORKSPACE / "06-bullets" / "stories.md", workspace / "06-bullets.tmp" / "stories.md")


# The fixture -------------------------------------------------------------------------

def test_fixture_end_to_end(workspace, capsys):
    shutil.rmtree(workspace / "06-bullets")
    shutil.rmtree(workspace / "07-sanitized")
    assert write.main(ws_arg(workspace)) == 0
    assert capsys.readouterr().out == FIXTURE_OUTPUT
    fixture_draft(workspace)
    assert write.main([*ws_arg(workspace), "--commit"]) == 0
    assert capsys.readouterr().out == FIXTURE_COMMITTED
    for name in ("bullets.json", "stories.md"):
        assert same_as_fixture(workspace, f"06-bullets/{name}"), name
    meta = wsio.read_json(workspace / "06-bullets" / "_stage.json")
    assert sorted(meta["inputs"]) == ["01-raw", "02-evidence/evidence.jsonl", "03-profile/profile.json",
                                      "04-projects/projects.json", "decisions/metrics.json", "decisions/profile.json"]
    assert meta["extra"] == {"bullets": 4, "quantified": 1, "stories": 1}

    # Sanitize apply reads the committed bullets and stories and rebuilds the saved 07-sanitized/.
    assert apply.main(ws_arg(workspace)) == 0
    wsio.write_json(workspace / "07-sanitized.tmp" / "new-terms.json", [])
    assert apply.main([*ws_arg(workspace), "--commit"]) == 0
    for name in ("bullets.json", "profile.json", "stories.md", "new-terms.json"):
        assert same_as_fixture(workspace, f"07-sanitized/{name}"), name
    assert validation.validate_workspace(workspace) == []
    targets, _ = gate.discover(workspace)
    assert gate.run(workspace, targets) == []
    status = stages.status(workspace)
    assert status["06-bullets"] == status["07-sanitized"] == "fresh"


def test_a_second_run_with_the_same_draft_keeps_every_id(workspace, capsys):
    assert write.main(ws_arg(workspace)) == 0
    fixture_draft(workspace)
    assert write.main([*ws_arg(workspace), "--commit"]) == 0
    assert same_as_fixture(workspace, "06-bullets/bullets.json")


# Must promises -----------------------------------------------------------------------

def test_stories_are_required(tmp_path, capsys):
    ws = make_workspace(tmp_path)
    assert write.main(ws_arg(ws)) == 0
    draft(ws, stories=None)
    capsys.readouterr()
    assert write.main([*ws_arg(ws), "--commit"]) == 1
    err = capsys.readouterr().err
    assert "error: 06-bullets.tmp/stories.md: not found; write the stories first: sanitize apply needs " \
           "06-bullets/stories.md (see SKILL.md)\n" in err
    assert not (ws / "06-bullets").exists()


def test_a_committed_stage_holds_both_files_and_validates(tmp_path, capsys):
    ws = make_workspace(tmp_path)
    assert write.main(ws_arg(ws)) == 0
    draft(ws)
    assert write.main([*ws_arg(ws), "--commit"]) == 0
    assert sorted(p.name for p in (ws / "06-bullets").iterdir()) == ["_stage.json", "bullets.json", "stories.md"]
    assert validation.validate_paths(ws, ["06-bullets"]) == []
    records = wsio.read_json(ws / "06-bullets" / "bullets.json")
    assert all(r["sources"] for r in records)
    assert [r["form"] for r in records if any(s.startswith("metric:") for s in r["sources"])] == ["xyz_quantified"]
    earlier = [r for r in records if r["work_ref"] == 1]
    assert earlier and all(s.startswith("resume:") for r in earlier for s in r["sources"])
    assert any(r["sources"] == [eid(5)] and r["project_id"] is None for r in records)  # a review cited directly
    out = capsys.readouterr().out
    assert out.endswith("committed 06-bullets: 5 bullets (1 quantified), 1 story\n")


def test_groups_json_is_never_read(tmp_path):
    ws = make_workspace(tmp_path)
    (ws / "04-projects" / "groups.json").write_text("not json", encoding="utf-8")
    assert write.main(ws_arg(ws)) == 0
    draft(ws)
    assert write.main([*ws_arg(ws), "--commit"]) == 0
    assert "04-projects/groups.json" not in wsio.read_json(ws / "06-bullets" / "_stage.json")["inputs"]


def test_a_new_metric_makes_the_stage_stale_and_a_term_decision_does_not(tmp_path):
    ws = make_workspace(tmp_path)
    (ws / "decisions" / "terms.json").unlink()  # write never reads the term decisions
    assert write.main(ws_arg(ws)) == 0
    draft(ws)
    assert write.main([*ws_arg(ws), "--commit"]) == 0
    wsio.write_json(ws / "decisions" / "terms.json", [{"term": "Northwind", "replacement": "a payments company",
                                                       "kind": "other"}])
    assert stages.status(ws)["06-bullets"] == "fresh"
    wsio.write_json(ws / "decisions" / "metrics.json", METRICS + [metric("m_2", PB, 3, "3 retries")])
    assert stages.status(ws)["06-bullets"] == "stale"


def test_a_profile_answer_makes_the_stage_stale(tmp_path):
    ws = make_workspace(tmp_path, wizard={})
    assert write.main(ws_arg(ws)) == 0
    draft(ws)
    assert write.main([*ws_arg(ws), "--commit"]) == 0
    wsio.write_json(ws / "decisions" / "profile.json", {"work": [{"endDate": "2025-03"}]})
    assert stages.status(ws)["06-bullets"] == "stale"


# Beginning -------------------------------------------------------------------------

def test_missing_projects_or_evidence(tmp_path, capsys):
    ws = make_workspace(tmp_path, projects=None)
    assert write.main(ws_arg(ws)) == 1
    assert capsys.readouterr().err == ("error: 04-projects/projects.json not found; run /resume-builder:analyze "
                                       "first\n06-bullets not begun\n")
    assert not (ws / "06-bullets.tmp").exists()
    ws = make_workspace(tmp_path / "e", evidence=None)
    assert write.main(ws_arg(ws)) == 1
    assert "02-evidence/evidence.jsonl not found; run /resume-builder:collect first" in capsys.readouterr().err


def test_an_invalid_input_names_the_command_that_fixes_it(tmp_path, capsys):
    ws = make_workspace(tmp_path, metrics=[{"id": "m_1", "project_id": PA}])
    assert write.main(ws_arg(ws)) == 1
    err = capsys.readouterr().err
    assert "error: decisions/metrics.json: $[0]: missing required property 'value'\n" in err
    assert "error: decisions/metrics.json is not valid; fix it with /resume-builder:wizard\n" in err


def test_begin_discards_a_draft(tmp_path):
    ws = make_workspace(tmp_path)
    assert write.main(ws_arg(ws)) == 0
    draft(ws)
    assert write.main(ws_arg(ws)) == 0
    assert list((ws / "06-bullets.tmp").iterdir()) == []


def test_from_current_starts_from_the_committed_files(tmp_path, capsys):
    ws = make_workspace(tmp_path)
    assert write.main([*ws_arg(ws), "--from-current"]) == 1
    assert "error: 06-bullets/ not found: nothing to revise; run write.py without --from-current\n" in \
        capsys.readouterr().err
    assert write.main(ws_arg(ws)) == 0
    draft(ws)
    assert write.main([*ws_arg(ws), "--commit"]) == 0
    capsys.readouterr()
    assert write.main([*ws_arg(ws), "--from-current"]) == 0
    assert capsys.readouterr().out.endswith(
        "began 06-bullets.tmp/ from the committed bullets and stories: revise 06-bullets.tmp/bullets.json and "
        "06-bullets.tmp/stories.md, then run write.py --commit\n")
    assert sorted(p.name for p in (ws / "06-bullets.tmp").iterdir()) == ["bullets.json", "stories.md"]

    # Revising: a new bullet gets the next number, the others keep theirs.
    revised = wsio.read_json(ws / "06-bullets.tmp" / "bullets.json")
    revised.insert(1, {"project_id": PB, "work_ref": 0, "text": "Cut failed ledger exports with retries",
                       "form": "xyz", "sources": [eid(3)]})
    wsio.write_json(ws / "06-bullets.tmp" / "bullets.json", revised)
    assert write.main([*ws_arg(ws), "--commit"]) == 0
    ids = [b["id"] for b in wsio.read_json(ws / "06-bullets" / "bullets.json")]
    assert ids == ["b_1", "b_6", "b_2", "b_3", "b_4", "b_5"]


def test_usage_errors():
    with pytest.raises(SystemExit) as exc:
        write.main(["--commit", "--from-current"])
    assert exc.value.code == 2


def test_warnings_and_notes(tmp_path, capsys):
    profile = {"work": [{"name": "Northwind", "position": "Engineer", "startDate": "2023-01", "endDate": "2024-12"}]}
    metrics = [metric("m_2", "pj_1d2c3b4a", 5, "5 fewer")]
    ws = make_workspace(tmp_path, profile=profile, metrics=metrics, review_text=None)
    assert write.main(ws_arg(ws)) == 0
    out = capsys.readouterr().out
    assert out.startswith(
        "warning: decisions/metrics.json m_2: pj_1d2c3b4a is not a project in 04-projects/projects.json; the wizard "
        "re-links or removes it\n"
        f"warning: {PA} 'Checkout latency' (2025-02 to 2025-05) falls in no job of the profile; resume-ats cannot "
        "place its bullets until the job is added with /resume-builder:wizard\n"
        f"warning: {PB} 'Ledger export retries' (2025-06 to 2025-06) falls in no job of the profile; resume-ats "
        "cannot place its bullets until the job is added with /resume-builder:wizard\n"
        f"warning: {eid(5)}: the raw record 01-raw/reviews.jsonl:1#/items/0 01-raw/reviews.jsonl not found; its "
        "excerpt stands in for the review's text\n"
        f"note: {PA} 'Checkout latency' has a metric prompt and no metric in decisions/metrics.json: its bullets use "
        "the xyz form; if the engineer has not been through the wizard, run /resume-builder:wizard first\n")
    assert "    job: none in the profile\n" in out
    assert "  /work/0  Engineer, Northwind  2023-01 to 2024-12  projects: none\n" in out

    bullets = [{"project_id": PA, "work_ref": None, "text": "Built an idempotency cache", "form": "xyz",
                "sources": [eid(2)]},
               {"project_id": PA, "work_ref": None, "text": "Cut p99 checkout latency", "form": "xyz",
                "sources": [eid(1)]},
               {"project_id": PB, "work_ref": None, "text": "Made ledger exports retry", "form": "xyz",
                "sources": [eid(3)]}]
    draft(ws, bullets, stories="# Stories\n\n## Checkout latency\n\n- **Situation:** Slow.\n- **Task:** Fix it.\n"
                               "- **Action:** Built a cache.\n- **Result:** Faster.\n")
    assert write.main([*ws_arg(ws), "--commit"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(
        "warning: decisions/metrics.json m_2: pj_1d2c3b4a is not a project in 04-projects/projects.json; the wizard "
        "re-links or removes it\n"
        f"warning: {eid(5)}: the raw record 01-raw/reviews.jsonl:1#/items/0 01-raw/reviews.jsonl not found; its "
        "excerpt stands in for the review's text\n"
        f"warning: 2 bullets of {PA} 'Checkout latency' (2025-02 to 2025-05) have no place: no job of the profile "
        "overlaps it; resume-ats cannot place them until the job is added with /resume-builder:wizard\n"
        f"warning: 1 bullet of {PB} 'Ledger export retries' (2025-06 to 2025-06) has no place: no job of the "
        "profile overlaps it; resume-ats cannot place it until the job is added with /resume-builder:wizard\n")
    assert "  b_1  no place  pj_0000000a  xyz  Built an idempotency cache\n" in out


def test_a_review_without_a_raw_ref(tmp_path, capsys):
    from write_samples import EVIDENCE
    evidence = [dict(e) for e in EVIDENCE]
    del evidence[4]["raw_ref"]  # optional in evidence.schema.json
    ws = make_workspace(tmp_path, evidence=evidence)
    assert write.main(ws_arg(ws)) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"warning: {eid(5)}: has no raw_ref; its excerpt stands in for the review's text\n")
    assert f"  {eid(5)}  2025-07-15  2025 H1 review  no raw record: only its excerpt\n" in out
    bullets = good_bullets()
    bullets[2]["text"] = "Led the cache work"  # 30% is only in the full text, which cannot be read
    draft(ws, bullets)
    assert write.main([*ws_arg(ws), "--commit"]) == 0


def test_no_profile(tmp_path, capsys):
    ws = make_workspace(tmp_path, profile=None)
    assert write.main(ws_arg(ws)) == 0
    out = capsys.readouterr().out
    assert out.startswith("warning: 03-profile/profile.json not found: no jobs or profile projects to put bullets "
                          "under; run /resume-builder:import\n")
    assert "jobs: none in the profile\n" in out and "profile projects:" not in out


# Committing ------------------------------------------------------------------------

def test_commit_needs_a_begun_stage_and_a_draft(tmp_path, capsys):
    ws = make_workspace(tmp_path)
    assert write.main([*ws_arg(ws), "--commit"]) == 1
    assert capsys.readouterr().err == "error: 06-bullets.tmp/ not found; run write.py first\n06-bullets not committed\n"
    assert write.main(ws_arg(ws)) == 0
    capsys.readouterr()
    assert write.main([*ws_arg(ws), "--commit"]) == 1
    assert "error: 06-bullets.tmp/bullets.json: not found; write the bullets first (see SKILL.md)\n" in \
        capsys.readouterr().err


def test_a_failed_check_commits_nothing_and_keeps_the_draft(tmp_path, capsys):
    ws = make_workspace(tmp_path)
    assert write.main(ws_arg(ws)) == 0
    bullets = good_bullets()
    bullets[1]["text"] = "Made 12 ledger exports retry"
    draft(ws, bullets, stories="# Stories\n")
    capsys.readouterr()
    assert write.main([*ws_arg(ws), "--commit"]) == 1
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "06-bullets.tmp/bullets.json: /1/text: the number '12' is in none of its sources",
        "  fix: edit 06-bullets.tmp/bullets.json: cite only a project's own evidence, performance reviews, its "
        "metrics and the profile; write only numbers the sources state; give each bullet its place; and cover every "
        "project, metric and resume highlight (see SKILL.md)",
        f"06-bullets.tmp/stories.md: no story for {PA} 'Checkout latency' (rank 1)",
        "  fix: edit 06-bullets.tmp/stories.md: '# Stories', then for each project write.py marked 'story', in its "
        "order, '## <its name>' and one line each for Situation, Task, Action and Result, with only numbers its "
        "evidence, the performance reviews or its metrics state (see SKILL.md)"]
    assert captured.err == "write check failed: 2 problems; 06-bullets not committed\n"
    assert not (ws / "06-bullets").exists()
    assert wsio.read_json(ws / "06-bullets.tmp" / "bullets.json") == bullets


def test_an_invalid_previous_file_carries_no_ids(tmp_path, capsys):
    ws = make_workspace(tmp_path)
    assert write.main(ws_arg(ws)) == 0
    draft(ws)
    assert write.main([*ws_arg(ws), "--commit"]) == 0
    (ws / "06-bullets" / "bullets.json").write_text(json.dumps([{"id": "b_9"}]), encoding="utf-8")
    assert write.main(ws_arg(ws)) == 0
    draft(ws)
    capsys.readouterr()
    assert write.main([*ws_arg(ws), "--commit"]) == 0
    assert capsys.readouterr().out.startswith(
        "warning: 06-bullets/bullets.json is not valid; no bullet IDs are carried from the last run\n")
    assert [b["id"] for b in wsio.read_json(ws / "06-bullets" / "bullets.json")] == [f"b_{n}" for n in range(1, 6)]


def test_a_split_part_without_a_summary(tmp_path, capsys):
    projects = [project(PA, [1, 2], "Checkout latency", 1, "2025-02", "2025-05", True),
                dict(project(PB, [3], "Checkout latency (part 2)", 2, "2025-06", "2025-06", False), summary="")]
    ws = make_workspace(tmp_path, projects=projects)
    assert write.main(ws_arg(ws)) == 0
    assert " 2. pj_0000000b  Checkout latency (part 2)  [lead, team, 2025-06 to 2025-06]\n    (no summary)\n" in \
        capsys.readouterr().out
