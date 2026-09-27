"""progress.py: each step's state, what makes a stage stale, and the command that continues the first step not done."""
import datetime
import shutil

import answer
import ats
import check_profile
import configure
import decide
import extract_text
import match_projects
import progress
import pytest
import write
from build_samples import FALCON, build_once, copy_of, fix_time, fixture, next_line, run, survey, ws_arg
from rbuild import common, steps
from rcore import stages, workspace as rworkspace, wsio

GATE = "wizard: checkpoint 3 until questions.py prints 'wizard: no open questions' (resume-wizard); then "
FROM_CURRENT = ("apply it to the committed grouping: stage.py begin 04-projects --from-current, then "
                "match_projects.py (resume-analyze step 5)")
RECOMMIT = ("a wizard answer: recommit the bullets with write.py --from-current, then write.py --commit; bullets "
            "that still pass keep their IDs, and a new metric needs a bullet that cites it (resume-write)")
RECHECK = ("re-check every version: stage.py begin 08-ats --from-current, then ats.py --commit; redraft a version "
           "it refuses (ats.py, ats.py --job SLUG) or remove it (ats.py --remove SLUG) (resume-ats)")
NEVER_BEGIN = "never run stage.py begin 01-raw, which deletes it"


@pytest.fixture(autouse=True)
def _time(monkeypatch):
    fix_time(monkeypatch)


@pytest.fixture(scope="module")
def built_root(tmp_path_factory):
    return build_once(tmp_path_factory)


@pytest.fixture
def built(built_root, tmp_path, monkeypatch):
    return copy_of(built_root, tmp_path, monkeypatch)


def later(monkeypatch, days: int) -> None:
    monkeypatch.setattr(common, "today", lambda: datetime.date(2026, 9, 27) + datetime.timedelta(days=days))


def set_end(workspace, end: str) -> None:
    assert run(configure, workspace, "time-range", "--start", "2023-01-01", "--end", end) == 0


# init -----------------------------------------------------------------------------------

def test_an_empty_folder_starts_with_init(tmp_path):
    found = survey(tmp_path / "nowhere")
    assert (found["init"].state, found["init"].note) == ("missing", "no config.json")
    assert {s.state for name, s in found.items() if name not in ("init", "import", "wizard", "review")} == {"missing"}
    assert found["import"].state == "none"
    assert next_line(tmp_path / "nowhere") == "init: create the workspace and config.json (resume-init)"


def test_a_missing_decisions_file_sends_back_to_init(tmp_path):
    rworkspace.init_workspace(tmp_path, "Engineer")
    (tmp_path / "decisions" / "wizard.json").unlink()
    found = survey(tmp_path)["init"]
    assert (found.state, found.note) == ("missing", "decisions/wizard.json missing")
    assert next_line(tmp_path) == "init: run resume-init again: init_workspace.py creates only what is missing"


def test_an_invalid_config_is_an_error(tmp_path, capsys):
    rworkspace.init_workspace(tmp_path, "Engineer")
    (tmp_path / "config.json").write_text('{"schema_version": 1}\n', encoding="utf-8")
    assert progress.main(ws_arg(tmp_path)) == 1
    err = capsys.readouterr().err
    assert "error: config.json: " in err
    assert "error: config.json is not valid; it is written by resume-init and resume-collect's configure.py\n" in err


# collect ----------------------------------------------------------------------------------

def test_a_new_workspace_collects_after_the_notice(tmp_path):
    rworkspace.init_workspace(tmp_path, "Engineer")
    assert survey(tmp_path)["collect"].note == "nothing collected; the data notice is not accepted yet"


def test_a_paused_fetch_is_continued_never_begun_again(built):
    tmp = stages.begin(built, "01-raw", from_current=True)
    (tmp / "github.jsonl").rename(tmp / "github.partial.jsonl")
    found = survey(built)["collect"]
    assert (found.state, found.note) == ("draft", "01-raw.tmp/github.partial.jsonl: a paused fetch")
    assert next_line(built) == f"collect: continue the paused fetch in 01-raw.tmp/ (resume-collect step 5); {NEVER_BEGIN}"
    (tmp / "github.partial.jsonl").rename(tmp / "github.jsonl")
    assert next_line(built) == (f"collect: continue the collection in 01-raw.tmp/ (resume-collect steps 5 to 8); "
                                f"{NEVER_BEGIN}")


def test_raw_without_evidence_needs_only_link(built):
    shutil.rmtree(built / "02-evidence")
    found = survey(built)["collect"]
    assert (found.state, found.note) == ("missing", "01-raw is committed, 02-evidence is not built")
    assert next_line(built) == "collect: link.py builds 02-evidence from the committed 01-raw (resume-collect step 8)"


def test_changed_raw_makes_the_evidence_stale(built):
    with (built / "01-raw" / "github.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("\n")
    found = survey(built)
    assert (found["collect"].state, found["collect"].note) == ("stale", "01-raw changed")
    assert found["analyze"].note == "01-raw changed; 02-evidence is stale"
    assert next_line(built) == "collect: 01-raw changed since 02-evidence was built: link.py (resume-collect step 8)"


@pytest.mark.parametrize("days, end, clause", [
    (0, None, ""),
    (1, None, "; the time range is open, so work since then is not in it"),
    (40, "2026-09-26", ""),
    (40, "2026-12-31", "; the time range ends 2026-12-31, so work since then is not in it"),
])
def test_the_collection_date_and_the_time_range(built, monkeypatch, days, end, clause):
    later(monkeypatch, days)
    if end:
        set_end(built, end)
    age = {0: "today", 1: "1 day ago", 40: "40 days ago"}[days]
    note = survey(built)["collect"].note
    assert note == f"4 items (github 2, jira 1, review 1), built 2026-09-27 ({age}){clause}"


# import -----------------------------------------------------------------------------------

def test_no_resume_is_none_and_skipped(built):
    shutil.rmtree(built / "03-profile")
    assert run(configure, built, "resume", "none") == 0
    found = survey(built)["import"]
    assert found.state == "none"
    assert found.note == "no resume in config.json: the engineer has none, or checkpoint 1 records it"
    assert not next_line(built).startswith("import")


def test_a_missing_import_names_the_file(built, built_root):
    shutil.rmtree(built / "03-profile")
    resume = built_root / "engineer" / "resume.txt"
    assert survey(built)["import"].note == str(resume)
    assert next_line(built) == f"import: import {resume} (resume-import)"


def test_a_missing_resume_file_is_asked_for(built, tmp_path):
    shutil.rmtree(built / "03-profile")
    gone = tmp_path / "gone.txt"
    gone.write_text("x", encoding="utf-8")
    assert run(configure, built, "resume", gone) == 0
    gone.unlink()
    assert next_line(built) == f"import: {gone} is not found: ask the engineer for the resume (resume-import)"


def test_an_interrupted_import_is_continued(built):
    assert run(extract_text, built) == 0
    found = survey(built)["import"]
    assert (found.state, found.note) == ("draft", "03-profile.tmp/resume.txt: waiting to be mapped")
    shutil.copy(built / "03-profile" / "profile.json", built / "03-profile.tmp" / "profile.json")
    assert next_line(built) == "import: check and commit it with check_profile.py --commit (resume-import step 5)"


def reimported(built, tmp_path):
    """Import a copy of the resume, so a test can change the file the import names."""
    resume = tmp_path / "resume.txt"
    shutil.copy(fixture("03-profile/resume.txt"), resume)
    assert run(extract_text, built, "--resume", resume) == 0
    shutil.copy(built / "03-profile" / "profile.json", built / "03-profile.tmp" / "profile.json")
    assert run(check_profile, built, "--commit") == 0
    return resume


def test_an_unchanged_resume_is_fresh(built, tmp_path):
    resume = reimported(built, tmp_path)
    found = survey(built)["import"]
    assert (found.state, found.note) == ("fresh", f"{resume}, unchanged since the import")


def test_an_edited_resume_is_changed(built, tmp_path):
    resume = reimported(built, tmp_path)
    resume.write_text(resume.read_text(encoding="utf-8") + "Kubernetes\n", encoding="utf-8")
    found = survey(built)["import"]
    assert (found.state, found.note) == ("changed", f"{resume} changed since the import")
    assert next_line(built) == ("import: import it again (resume-import); wizard answers the new import moves "
                                "become moved: questions (resume-wizard)")


def test_another_resume_in_the_config_is_changed(built, built_root, tmp_path):
    other = tmp_path / "new-resume.txt"
    shutil.copy(fixture("03-profile/resume.txt"), other)
    assert run(configure, built, "resume", other) == 0
    found = survey(built)["import"]
    assert (found.state, found.note) == (
        "changed", f"config.json names {other}, not the imported {built_root / 'engineer' / 'resume.txt'}")


def test_a_resume_file_gone_or_unnamed_keeps_the_import(built, tmp_path):
    resume = reimported(built, tmp_path)
    resume.unlink()
    assert (survey(built)["import"].state, survey(built)["import"].note) == (
        "fresh", f"{resume} is no longer there; the import stays")
    assert run(configure, built, "resume", "none") == 0
    assert survey(built)["import"].note == f"config.json names no resume; the import of {resume} stays"


# analyze ----------------------------------------------------------------------------------

def test_a_project_decision_is_applied_to_the_committed_grouping(built, capsys):
    """Checkpoint 2's choices go through decide.py; one recorded after the commit makes 04-projects stale."""
    assert run(decide, built, "set-scope", FALCON, "org") == 0
    found = survey(built)["analyze"]
    assert (found.state, found.note, found.action) == ("stale", "decisions/projects.json changed", FROM_CURRENT)
    assert survey(built)["write"].note == "04-projects is stale"
    stages.begin(built, "04-projects", from_current=True)
    assert run(match_projects, built, "--commit") == 0
    assert survey(built)["analyze"].state == "fresh"
    projects = wsio.read_json(built / "04-projects" / "projects.json")
    assert projects[0]["scope"] == "org"


def test_changed_evidence_means_grouping_again(built):
    evidence = built / "02-evidence" / "evidence.jsonl"
    evidence.write_text(evidence.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    found = survey(built)
    assert found["collect"].state == "fresh"  # 02-evidence records only 01-raw
    assert found["analyze"].note == "02-evidence/evidence.jsonl changed"
    assert next_line(built) == ("analyze: the evidence changed: group again with signals.py, starting from the "
                                "last groups.json (resume-analyze)")


def test_an_interrupted_checkpoint_2_is_continued(built):
    tmp = stages.begin(built, "04-projects", from_current=True)
    assert survey(built)["analyze"].note == "04-projects.tmp/groups.json: checkpoint 2 in progress"
    assert next_line(built) == "analyze: continue checkpoint 2 with match_projects.py (resume-analyze step 5)"
    (tmp / "groups.json").unlink()
    (tmp / "signals.json").unlink()
    assert next_line(built) == "analyze: run signals.py again (resume-analyze step 2)"


# scan, write, apply ---------------------------------------------------------------------------

def test_an_interrupted_scan_is_continued(built):
    stages.begin(built, "05-terms", from_current=True)
    found = survey(built)["scan"]
    assert (found.state, found.note) == ("draft", "05-terms.tmp/candidates.json: waiting for the check")
    assert next_line(built) == "scan: scan.py --commit (resume-sanitize, scan step 5)"


def test_a_wizard_answer_recommits_write_unchanged(built):
    before = (built / "06-bullets" / "bullets.json").read_bytes()
    assert run(answer, built, "profile", "/basics/phone", "+1 555 0100") == 0
    found = survey(built)
    assert (found["write"].state, found["write"].note, found["write"].action) == (
        "stale", "decisions/profile.json changed", RECOMMIT)
    assert found["apply"].note == "06-bullets is stale"
    assert found["ats"].note == "07-sanitized is stale; decisions/profile.json changed"
    assert found["scan"].state == found["analyze"].state == "fresh"
    assert next_line(built) == GATE + "write: " + RECOMMIT

    assert run(write, built, "--from-current") == 0
    assert next_line(built) == "write: write.py --commit (resume-write step 6)"  # a draft needs no checkpoint 3
    assert run(write, built, "--commit") == 0
    assert (built / "06-bullets" / "bullets.json").read_bytes() == before  # same text, same IDs
    found = survey(built)
    assert found["write"].state == found["apply"].state == "fresh"  # 07-sanitized's inputs are unchanged
    assert (found["ats"].note, found["ats"].action) == ("decisions/profile.json changed", RECHECK)

    stages.begin(built, "08-ats", from_current=True)
    assert run(ats, built, "--commit") == 0
    assert survey(built)["ats"].state == "fresh"


def test_a_new_metric_or_regrouping_means_revising_the_bullets(built):
    assert run(decide, built, "rename", FALCON, "--name", "Checkout latency") == 0
    stages.begin(built, "04-projects", from_current=True)
    assert run(match_projects, built, "--commit") == 0
    found = survey(built)["write"]
    assert (found.state, found.note) == ("stale", "04-projects/projects.json changed")
    assert found.action == "revise the bullets: write.py --from-current, then write.py --commit (resume-write)"


def test_a_term_decision_makes_only_apply_and_later_stale(built):
    assert run(answer, built, "term", "Northwind", "--allow", "--kind", "other") == 0
    found = survey(built)
    assert found["scan"].state == found["write"].state == "fresh"  # neither records decisions/terms.json
    assert (found["apply"].state, found["apply"].note) == ("stale", "decisions/terms.json changed")
    assert next_line(built) == GATE + "apply: apply.py, then apply.py --commit (resume-sanitize, apply)"


def test_an_interrupted_write_or_apply_is_continued(built):
    stages.begin(built, "07-sanitized", from_current=True)
    assert next_line(built) == ("apply: apply.py --commit; if it says the inputs changed, apply.py again "
                                "(resume-sanitize, apply step 5)")
    stages.begin(built, "06-bullets")
    found = survey(built)["write"]
    assert (found.state, found.note) == ("draft", "06-bullets.tmp/: write.py began")
    assert next_line(built) == "write: write.py --from-current again, then write.py --commit (resume-write)"


# ats, review, render ---------------------------------------------------------------------------

def test_an_ats_draft_is_continued(built):
    assert run(ats, built, "--revise", "fintech-sre") == 0
    found = survey(built)
    assert (found["ats"].state, found["ats"].note) == ("draft", "08-ats.tmp/ with general, fintech-sre")
    assert found["review"].state == "waiting"
    assert next_line(built) == ("ats: continue with ats.py --commit, or start over from the committed stage with "
                                "stage.py begin 08-ats --from-current (resume-ats)")


def test_an_unattested_flag_opens_the_review(built):
    wsio.write_json(built / "decisions" / "attestations.json", [])
    found = survey(built)
    assert found["ats"].note == "general, fintech-sre: 1 flagged, 1 open"
    assert (found["review"].state, found["review"].note) == ("open", "checkpoint 4: 1 open item")
    assert next_line(built) == "review: checkpoint 4: final_review.py lists the open items"


def test_a_render_after_the_review_leaves_nothing_to_do(built):
    stages.begin(built, "out")
    assert stages.commit(built, "out", ["08-ats", "decisions/attestations.json"],
                         extra={"targets": ["general", "fintech-sre"], "pdf": False}) == []
    found = survey(built)
    assert (found["render"].state, found["render"].note) == ("fresh", "general, fintech-sre (DOCX and TXT)")
    assert next_line(built) == steps.NOTHING
    wsio.write_json(built / "decisions" / "attestations.json", [])  # an attestation withdrawn
    found = survey(built)
    assert (found["render"].state, found["render"].note) == ("stale", "decisions/attestations.json changed")
    assert found["review"].state == "open"
    assert next_line(built) == "review: checkpoint 4: final_review.py lists the open items"


def test_the_stale_note_names_each_input_once():
    assert steps.stale_note([("decisions/terms.json", "changed"), ("02-evidence/evidence.jsonl", "missing"),
                             ("07-sanitized/bullets.json", "stale"), ("07-sanitized/profile.json", "stale")]) == \
        "decisions/terms.json changed; 02-evidence/evidence.jsonl is gone; 07-sanitized is stale"
