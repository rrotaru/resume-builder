"""ats.py and the checkers end to end, on the fixture."""
import json
import shutil

import answer
import ats
import ats_lint
import diff_claims
import keywords
import pytest
from ats_samples import (B1_GENERAL, B1_JOB, B1_SANITIZED, GENERAL_KEYWORDS, JOB_KEYWORDS, draft_resume, edit,
                         fix_month, posting, resume_path, set_text, write_keywords, ws_arg)
from conftest import FIXTURE_WORKSPACE
from rcore import flags, stages, validation, wsio
from rrender import gate

FILES = ["general/keywords.json", "general/report.json", "general/resume.json", "jobs/fintech-sre/flags.json",
         "jobs/fintech-sre/jd.txt", "jobs/fintech-sre/keywords.json", "jobs/fintech-sre/report.json",
         "jobs/fintech-sre/resume.json"]
PLACES = """\
places:
  /work/0  Senior Software Engineer, Northwind Payments  2023-01 to present
    b_1  pj_da2a2b53  xyz_quantified  Cut p99 checkout latency 40% for a top-10 US bank by building a \
Redis-backed idempotency cache for real-time fraud-detection platform in Go
    b_2  xyz  Mentored two new engineers through on-call onboarding
  /work/1  Software Engineer, Tailspin Toys  2019-06 to 2022-12
    b_3  xyz  Migrated the order service from PHP to Go, serving 2M requests per day
  /projects/0  ledger-lint  2021-04 to present
    b_4  xyz  Built ledger-lint, an open-source linter for double-entry ledger files with 300 GitHub stars
"""
DRAFT_GENERAL = """\
ats: drafted general in 08-ats.tmp/general/ (a new draft)
target role: Senior Backend Engineer
experience: 88 months: 1 page, 50 lines
""" + PLACES + """\
08-ats.tmp/general/resume.json: every fact from the profile and 4 bullets in their places, estimated 36 of 50 lines
next: write 08-ats.tmp/general/keywords.json (the target role's keywords), run keywords.py general, then select, \
order and reword the bullets in resume.json and run ats.py --commit
"""
COMMIT_GENERAL = """\
general: 4 of 4 bullets, 36 of 50 lines; keywords: 4 covered, 1 missing with evidence, 1 missing without evidence
committed 08-ats: general
"""
DRAFT_JOB = """\
ats: drafted fintech-sre in 08-ats.tmp/jobs/fintech-sre/ (a copy of the committed 08-ats/ with general)
posting: 08-ats.tmp/jobs/fintech-sre/jd.txt from {posting}: Senior Backend Engineer, Payments Reliability
target role: Senior Backend Engineer
experience: 88 months: 1 page, 50 lines
""" + PLACES + """\
08-ats.tmp/jobs/fintech-sre/resume.json: every fact from the profile and 4 bullets in their places, estimated 36 \
of 50 lines
next: read 08-ats.tmp/jobs/fintech-sre/jd.txt, write 08-ats.tmp/jobs/fintech-sre/keywords.json (the posting's \
keywords, as it spells them), run keywords.py fintech-sre, then tailor resume.json and run ats.py --commit
"""
COMMIT_BOTH = """\
general: 4 of 4 bullets, 36 of 50 lines; keywords: 4 covered, 1 missing with evidence, 1 missing without evidence
fintech-sre: 4 of 4 bullets, 36 of 50 lines; keywords: 5 covered, 1 missing with evidence, 2 missing without \
evidence; 1 flagged
  b_1  introduces 'SLO compliance', which no cited source mentions
committed 08-ats: general, fintech-sre (1 flagged)
"""


@pytest.fixture(autouse=True)
def _month(monkeypatch):
    fix_month(monkeypatch)


def run(module, workspace, *args):
    return module.main([*ws_arg(workspace), *args])


def same_as_fixture(workspace, rel):
    return (workspace / rel).read_bytes() == (FIXTURE_WORKSPACE / rel).read_bytes()


def tailor_general(workspace):
    write_keywords(workspace, "general", GENERAL_KEYWORDS)
    edit(resume_path(workspace), lambda r: set_text(r, "work", 0, 0, B1_GENERAL))


def tailor_job(workspace):
    write_keywords(workspace, "fintech-sre", JOB_KEYWORDS)
    edit(resume_path(workspace, "fintech-sre"), lambda r: set_text(r, "work", 0, 0, B1_JOB))


def committed(workspace, tmp_path):
    """The fixture's 08-ats/, committed by ats.py."""
    shutil.rmtree(workspace / "08-ats")
    assert run(ats, workspace) == 0
    tailor_general(workspace)
    assert run(ats, workspace, "--jd", str(posting(tmp_path))) == 0
    tailor_job(workspace)
    assert run(ats, workspace, "--commit") == 0


# The fixture -------------------------------------------------------------------------

def test_fixture_end_to_end(workspace, tmp_path, capsys):
    shutil.rmtree(workspace / "08-ats")
    assert run(ats, workspace) == 0
    assert capsys.readouterr().out == DRAFT_GENERAL
    tailor_general(workspace)
    assert run(keywords, workspace, "general") == 0
    assert run(ats_lint, workspace) == 0
    assert run(diff_claims, workspace) == 0
    capsys.readouterr()
    assert run(ats, workspace, "--commit") == 0
    assert capsys.readouterr().out == COMMIT_GENERAL
    assert not (workspace / "08-ats.tmp").exists()

    path = posting(tmp_path)
    assert run(ats, workspace, "--jd", str(path)) == 0
    assert capsys.readouterr().out == DRAFT_JOB.format(posting=path)
    tailor_job(workspace)
    assert run(diff_claims, workspace, "fintech-sre") == 0
    assert "b_1  introduces 'SLO compliance', which no cited source mentions" in capsys.readouterr().out
    assert run(ats, workspace, "--commit") == 0
    assert capsys.readouterr().out == COMMIT_BOTH

    for rel in FILES:
        assert same_as_fixture(workspace, f"08-ats/{rel}"), rel
    meta = wsio.read_json(workspace / "08-ats" / "_stage.json")
    assert list(meta["inputs"]) == ["01-raw", "02-evidence/evidence.jsonl", "03-profile/profile.json",
                                    "04-projects/projects.json", "07-sanitized/bullets.json",
                                    "07-sanitized/profile.json", "config.json", "decisions/metrics.json",
                                    "decisions/profile.json", "decisions/terms.json"]
    assert meta["extra"] == {"versions": ["general", "fintech-sre"], "flagged": {"fintech-sre": 1}}
    assert validation.validate_workspace(workspace) == []
    assert flags.check_job(workspace, "fintech-sre") == []  # the fixture's attestation still holds
    targets, _ = gate.discover(workspace)
    assert gate.run(workspace, targets) == []
    assert stages.status(workspace)["08-ats"] == "fresh"


def test_an_attestation_leaves_08_ats_fresh_and_a_term_decision_makes_it_stale(workspace, tmp_path):
    committed(workspace, tmp_path)
    wsio.write_json(workspace / "decisions" / "attestations.json", [])
    assert stages.status(workspace)["08-ats"] == "fresh"
    assert answer.main([*ws_arg(workspace), "term", "Northwind", "--allow", "--kind", "other"]) == 0
    assert stages.status(workspace)["08-ats"] == "stale"


def test_the_flag_needs_checkpoint_4(workspace, tmp_path):
    committed(workspace, tmp_path)
    wsio.write_json(workspace / "decisions" / "attestations.json", [])
    assert flags.check_job(workspace, "fintech-sre") == [
        "08-ats/jobs/fintech-sre: b_1 is flagged (introduces 'SLO compliance', which no cited source mentions); "
        "accept, revert or edit it"]


# Must promises -----------------------------------------------------------------------

def test_facts_must_be_copied(workspace, capsys):
    assert run(ats, workspace) == 0
    tailor_general(workspace)
    edit(resume_path(workspace), lambda r: r["work"][0].update(position="Staff Engineer"))
    edit(resume_path(workspace), lambda r: r["skills"][0]["keywords"].append("Kubernetes"))
    capsys.readouterr()
    assert run(ats, workspace, "--commit") == 1
    out = capsys.readouterr().out
    assert "08-ats.tmp/general/resume.json: /work/0: position 'Staff Engineer' does not match the profile (closest " \
           "entry /work/0 has 'Senior Software Engineer')\n" in out
    assert "08-ats.tmp/general/resume.json: /skills/0: keyword 'Kubernetes' is not in the profile (closest entry " \
           "/skills/0)\n" in out
    assert "  fix: keep every fact as drafted" in out
    assert same_as_fixture(workspace, "08-ats/general/resume.json")  # the committed stage is untouched


def test_a_keyword_enters_skills_only_through_the_wizard(workspace, capsys):
    assert answer.main([*ws_arg(workspace), "add", "/skills/0/keywords", "Kubernetes"]) == 0
    assert run(ats, workspace) == 0
    assert draft_resume(workspace)["skills"][0]["keywords"] == ["Go", "Python", "Redis", "PostgreSQL", "Kubernetes"]
    tailor_general(workspace)
    capsys.readouterr()
    assert run(keywords, workspace, "general") == 0
    assert "  covered  Kubernetes  /skills/0/keywords/4\n" in capsys.readouterr().out


def test_x_sources_are_refused(workspace, capsys):
    assert run(ats, workspace) == 0
    tailor_general(workspace)
    edit(resume_path(workspace), lambda r: r["work"][0].update({"x-sources": ["resume:/work/0/name"]}))
    capsys.readouterr()
    assert run(ats, workspace, "--commit") == 1
    assert "08-ats.tmp/general/resume.json: $.work[0].x-sources: unexpected property\n" in capsys.readouterr().out


@pytest.mark.parametrize("change, line", [
    (lambda r: r["work"][0]["x-highlights"].append(r["work"][1]["x-highlights"].pop()),
     "/work/0/x-highlights/2: b_3 goes under /work/1 (Software Engineer, Tailspin Toys); this entry copies /work/0"),
    (lambda r: r["work"][0]["x-highlights"].append(r["projects"][0]["x-highlights"].pop()),
     "/work/0/x-highlights/2: b_4 goes under /projects/0 (ledger-lint); this entry copies /work/0"),
    (lambda r: r["work"][0]["x-highlights"][1]["sources"].append("metric:m_1"),
     "/work/0/x-highlights/1: sources must be b_2's sources ['ev_cbf558fa']"),
    (lambda r: r["work"][0]["x-highlights"][1].update(bullet_id="b_9"),
     "/work/0/x-highlights/1: b_9 is not a bullet of 07-sanitized/bullets.json; use only the drafted bullets"),
])
def test_placement(workspace, capsys, change, line):
    assert run(ats, workspace) == 0
    tailor_general(workspace)
    edit(resume_path(workspace), change)
    capsys.readouterr()
    assert run(ats, workspace, "--commit") == 1
    out = capsys.readouterr().out
    assert f"08-ats.tmp/general/resume.json: {line}\n" in out
    assert "  fix: keep each bullet under the entry it was drafted under" in out


def test_a_bullet_with_no_place_is_left_out_reported_and_refused(workspace, capsys):
    edit(workspace / "07-sanitized" / "bullets.json", lambda b: b[0].update(work_ref=None))
    assert run(ats, workspace) == 0
    out = capsys.readouterr().out
    assert out.startswith("warning: b_1 (pj_da2a2b53 'Project Falcon checkout latency') has no place: no job of the "
                          "profile overlaps its project; it is left out until the job is added with "
                          "/resume-builder:wizard\n")
    assert [h["bullet_id"] for h in draft_resume(workspace)["work"][0]["x-highlights"]] == ["b_2"]
    write_keywords(workspace, "general", GENERAL_KEYWORDS)
    edit(resume_path(workspace), lambda r: r["work"][0]["x-highlights"].insert(0, {
        "bullet_id": "b_1", "text": B1_SANITIZED, "sources": ["ev_191cc8ce", "ev_99a74656", "metric:m_1"]}))
    assert run(ats, workspace, "--commit") == 1
    assert ("08-ats.tmp/general/resume.json: /work/0/x-highlights/0: b_1 has no place (no job of the profile "
            "overlaps its project); leave it out\n") in capsys.readouterr().out
    edit(resume_path(workspace), lambda r: r["work"][0]["x-highlights"].pop(0))
    capsys.readouterr()
    assert run(ats, workspace, "--commit") == 1  # the kept job still holds b_1, which has no place now
    assert ("08-ats.tmp/jobs/fintech-sre/resume.json: /work/0/x-highlights/0: b_1 has no place (no job of the "
            "profile overlaps its project); leave it out\n") in capsys.readouterr().out
    assert run(ats, workspace, "--remove", "fintech-sre") == 0
    assert run(ats, workspace, "--commit") == 0
    report = wsio.read_json(workspace / "08-ats" / "general" / "report.json")
    assert report["left_out"] == [{"bullet_id": "b_1", "reason": "no place"}]


def test_left_out_bullets_are_reported(workspace):
    assert run(ats, workspace) == 0
    tailor_general(workspace)
    edit(resume_path(workspace), lambda r: r["work"][0]["x-highlights"].pop(1))
    assert run(ats, workspace, "--commit") == 0
    report = wsio.read_json(workspace / "08-ats" / "general" / "report.json")
    assert report["left_out"] == [{"bullet_id": "b_2", "reason": "not selected"}]
    assert wsio.read_json(workspace / "08-ats" / "general" / "resume.json")["work"][0]["highlights"] == [B1_GENERAL]


def test_the_general_resume_may_have_no_claim(workspace, capsys):
    assert run(ats, workspace) == 0
    tailor_general(workspace)
    edit(resume_path(workspace), lambda r: set_text(r, "work", 0, 0, B1_GENERAL + " on Kubernetes for 12 teams"))
    capsys.readouterr()
    assert run(diff_claims, workspace, "general") == 1
    assert "  /work/0/x-highlights/0 (b_1): introduces 'Kubernetes', which no cited source mentions\n" in \
        capsys.readouterr().out
    assert run(ats, workspace, "--commit") == 1
    out = capsys.readouterr().out
    assert ("08-ats.tmp/general/resume.json: /work/0/x-highlights/0 (b_1): introduces 'Kubernetes', which no cited "
            "source mentions\n08-ats.tmp/general/resume.json: /work/0/x-highlights/0 (b_1): states the number '12', "
            "which no cited source states\n  fix: in the general resume, reword only") in out


def test_a_denied_term_is_refused(workspace, capsys):
    assert run(ats, workspace) == 0
    tailor_general(workspace)
    edit(resume_path(workspace), lambda r: set_text(r, "work", 0, 0, B1_GENERAL.replace("a top-10 US bank",
                                                                                         "Contoso Bank")))
    capsys.readouterr()
    assert run(ats, workspace, "--commit") == 1
    assert "08-ats.tmp/general/resume.json:/work/0/x-highlights/0/text: contains denylisted term 'Contoso Bank'" in \
        capsys.readouterr().out


def test_lint_errors_and_a_schema_problem_stop_the_commit(workspace, tmp_path, capsys):
    committed(workspace, tmp_path)
    assert run(ats, workspace, "--revise", "general") == 0
    edit(resume_path(workspace), lambda r: set_text(r, "work", 0, 1, "• Mentored two new engineers"))
    edit(resume_path(workspace, "fintech-sre"), lambda r: r.update(awards=[]))
    capsys.readouterr()
    assert run(ats, workspace, "--commit") == 1
    out = capsys.readouterr().out
    assert "08-ats.tmp/jobs/fintech-sre/resume.json: $.awards: unexpected property\n" in out
    assert "08-ats.tmp/general/resume.json: /work/0/x-highlights/1: begins with '•'; render adds the bullet\n" in out
    assert run(ats_lint, workspace, "general") == 1


# Files and versions ------------------------------------------------------------------

def test_commit_without_a_draft(workspace, capsys):
    assert run(ats, workspace, "--commit") == 1
    assert "error: 08-ats.tmp/ not found; draft a version with ats.py first" in capsys.readouterr().err


def test_unexpected_and_missing_files(workspace, capsys):
    assert run(ats, workspace) == 0
    tailor_general(workspace)
    (workspace / "08-ats.tmp" / "general" / "notes.txt").write_text("x", encoding="utf-8")
    (workspace / "08-ats.tmp" / "stray.json").write_text("{}", encoding="utf-8")
    (workspace / "08-ats.tmp" / "jobs" / "Bad_Slug").mkdir()
    capsys.readouterr()
    assert run(ats, workspace, "--commit") == 1
    out = capsys.readouterr().out
    assert "08-ats.tmp/general/notes.txt: not a file resume-ats writes; remove it\n" in out
    assert "08-ats.tmp/stray.json: not a file resume-ats writes; remove it\n" in out
    assert "08-ats.tmp/jobs/Bad_Slug: 'Bad_Slug' is not a job slug" in out
    (workspace / "08-ats.tmp" / "jobs" / "fintech-sre" / "keywords.json").unlink()
    assert run(ats, workspace, "--commit") == 1
    assert ("08-ats.tmp/jobs/fintech-sre/keywords.json: not found; write the posting's keywords (see SKILL.md)\n"
            in capsys.readouterr().out)


def test_a_kept_version_is_checked_against_the_current_inputs(workspace, capsys):
    def rewrite(bullets):
        bullets[2]["id"] = "b_5"  # write reworded b_3, so it has a new ID
    edit(workspace / "07-sanitized" / "bullets.json", rewrite)
    assert run(ats, workspace) == 0
    tailor_general(workspace)
    capsys.readouterr()
    assert run(ats, workspace, "--commit") == 1
    assert ("08-ats.tmp/jobs/fintech-sre/resume.json: /work/1/x-highlights/0: b_3 is not a bullet of "
            "07-sanitized/bullets.json; use only the drafted bullets\n") in capsys.readouterr().out
    assert run(ats, workspace, "--job", "fintech-sre") == 0  # redrafted from its saved posting, in the same draft
    assert "(continuing the draft with general, fintech-sre)" in capsys.readouterr().out
    assert wsio.read_json(workspace / "08-ats.tmp" / "jobs" / "fintech-sre" / "keywords.json") == JOB_KEYWORDS
    assert not (workspace / "08-ats.tmp" / "jobs" / "fintech-sre" / "flags.json").exists()
    assert run(ats, workspace, "--commit") == 0
    assert wsio.read_json(workspace / "08-ats" / "jobs" / "fintech-sre" / "flags.json")["flags"] == []


def test_slugs(workspace, tmp_path, capsys):
    path = posting(tmp_path, "Fintech SRE (2).txt")
    assert run(ats, workspace, "--jd", str(path)) == 0
    assert (workspace / "08-ats.tmp" / "jobs" / "fintech-sre-2" / "jd.txt").read_bytes() == path.read_bytes()
    for args, error in [
        (["--jd", str(path), "--job", "general"], "'general' is the general resume; give the job another slug with "
                                                  "--job"),
        (["--jd", str(path), "--job", "Bad_Slug"], "'Bad_Slug' is not a job slug"),
        (["--jd", str(posting(tmp_path, "___.txt"))], "the posting's file name gives no slug; give one with --job"),
        (["--jd", str(tmp_path / "gone.txt")], "gone.txt: not found"),
        (["--job", "nope"], "no saved posting for nope; draft it with ats.py --jd FILE --job nope"),
    ]:
        capsys.readouterr()
        assert run(ats, workspace, *args) == 1, args
        assert error in capsys.readouterr().err, args


def test_a_posting_must_be_text(workspace, tmp_path, capsys):
    (tmp_path / "empty.txt").write_text(" \n", encoding="utf-8")
    (tmp_path / "binary.txt").write_bytes(b"\xff\xfe\x00posting")
    assert run(ats, workspace, "--jd", str(tmp_path / "empty.txt")) == 1
    assert "empty.txt: the posting is empty" in capsys.readouterr().err
    assert run(ats, workspace, "--jd", str(tmp_path / "binary.txt")) == 1
    assert "binary.txt: not UTF-8 text; save the posting's text as a .txt file" in capsys.readouterr().err
    assert not (workspace / "08-ats.tmp").exists()


def test_a_relative_posting_path_is_relative_to_the_workspace(workspace):
    shutil.copy(posting(workspace.parent), workspace / "posting.txt")
    assert run(ats, workspace, "--jd", "posting.txt", "--job", "acme") == 0
    assert (workspace / "08-ats.tmp" / "jobs" / "acme" / "jd.txt").is_file()


def test_a_new_posting_starts_the_job_over(workspace, tmp_path):
    assert run(ats, workspace, "--jd", str(posting(tmp_path))) == 0
    assert sorted(p.name for p in (workspace / "08-ats.tmp" / "jobs" / "fintech-sre").iterdir()) == [
        "jd.txt", "resume.json"]


def test_revise_prints_each_bullet_with_its_original(workspace, tmp_path, capsys):
    committed(workspace, tmp_path)
    capsys.readouterr()
    assert run(ats, workspace, "--revise", "fintech-sre") == 0
    out = capsys.readouterr().out
    assert out.startswith("ats: revising fintech-sre in 08-ats.tmp/jobs/fintech-sre/ (a copy of the committed "
                          f"08-ats/ with general, fintech-sre)\n  /work/0/x-highlights/0  b_1  {B1_JOB}\n"
                          f"      was: {B1_SANITIZED}\n")
    assert "flags: 1\n  b_1  introduces 'SLO compliance', which no cited source mentions\n" in out
    # Revert b_1 to its original: nothing is flagged, and no attestation is needed.
    edit(resume_path(workspace, "fintech-sre"), lambda r: set_text(r, "work", 0, 0, B1_SANITIZED))
    assert run(ats, workspace, "--commit") == 0
    assert "fintech-sre: 4 of 4 bullets" in capsys.readouterr().out
    wsio.write_json(workspace / "decisions" / "attestations.json", [])
    assert flags.check_job(workspace, "fintech-sre") == []
    assert run(ats, workspace, "--revise", "nope") == 1


def test_remove(workspace, capsys):
    assert run(ats, workspace, "--remove", "fintech-sre") == 0
    assert capsys.readouterr().out == ("ats: removed fintech-sre from 08-ats.tmp/ (a copy of the committed 08-ats/ "
                                       "with general, fintech-sre); run ats.py --commit\n")
    assert not (workspace / "08-ats.tmp" / "jobs").exists()
    assert run(ats, workspace, "--commit") == 0
    assert gate.discover(workspace)[0] == [gate.Target("general")]
    assert run(ats, workspace, "--remove", "general") == 1
    assert run(ats, workspace, "--remove", "fintech-sre") == 1


def test_usage_errors(workspace):
    for args in (["--commit", "--jd", "x.txt"], ["--revise", "general", "--job", "x"], ["--commit", "--remove", "x"]):
        with pytest.raises(SystemExit) as exc:
            run(ats, workspace, *args)
        assert exc.value.code == 2


def test_checkers_need_a_draft(workspace, capsys):
    for module in (ats_lint, keywords, diff_claims):
        assert run(module, workspace) == 1
        assert "error: 08-ats.tmp/ not found: there is no draft" in capsys.readouterr().err
    assert run(ats, workspace) == 0
    assert run(keywords, workspace, "nope") == 1
    assert "error: nope: not in the draft (08-ats.tmp/)" in capsys.readouterr().err
    (workspace / "08-ats.tmp" / "general" / "keywords.json").unlink()
    assert run(keywords, workspace, "general") == 1
    assert "error: 08-ats.tmp/general/keywords.json: not found" in capsys.readouterr().out


def test_missing_inputs(workspace, capsys):
    (workspace / "07-sanitized" / "bullets.json").unlink()
    assert run(ats, workspace) == 1
    assert "07-sanitized/bullets.json not found; run /resume-builder:write, then /resume-builder:sanitize (apply) " \
           "first" in capsys.readouterr().err
    assert not (workspace / "08-ats.tmp").exists()


def test_an_invalid_terms_file_stops_the_draft(workspace, capsys):
    (workspace / "decisions" / "terms.json").write_text(json.dumps([{"term": "x"}]), encoding="utf-8")
    assert run(ats, workspace) == 1
    assert "decisions/terms.json is not valid; fix it with /resume-builder:wizard" in capsys.readouterr().err


def test_a_fact_holding_a_denied_term_needs_the_wizard(workspace, capsys):
    edit(workspace / "decisions" / "terms.json", lambda t: t.append(
        {"term": "Tailspin", "replacement": "a toy maker", "kind": "customer"}))
    assert run(ats, workspace) == 0
    assert capsys.readouterr().out.startswith(
        "warning: /work/1/name 'Tailspin Toys' holds the denied term 'Tailspin'; facts are copied exactly")
    tailor_general(workspace)
    assert run(ats, workspace, "--commit") == 1
    out = capsys.readouterr().out
    assert "08-ats.tmp/general/resume.json:/work/1/name: contains denylisted term 'Tailspin'\n" in out
    assert "for a fact field, set a replacement value with /resume-builder:wizard" in out
    assert answer.main([*ws_arg(workspace), "profile", "/work/1/name", "A toy company"]) == 0
    assert run(ats, workspace) == 0
    assert draft_resume(workspace)["work"][1]["name"] == "A toy company"


def test_an_interrupted_commit_is_restored_before_drafting(workspace, capsys):
    (workspace / "08-ats").rename(workspace / "08-ats.old")
    assert run(ats, workspace, "--job", "fintech-sre") == 1  # the saved posting is in 08-ats.old/ until restored
    assert run(ats, workspace) == 0
    assert "(a copy of the committed 08-ats/ with general, fintech-sre)" in capsys.readouterr().out
    assert (workspace / "08-ats" / "jobs" / "fintech-sre" / "jd.txt").is_file()
