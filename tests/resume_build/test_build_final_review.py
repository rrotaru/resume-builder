"""final_review.py: checkpoint 4's sections and open items."""
import shutil

import answer
import apply
import final_review
import pytest
from build_samples import B1_JOB, build_once, copy_of, edit_json, fix_time, run, set_text, ws_arg
from rbuild import final, jobs
from rcore import flags, wsio

REVIEW = """\
checkpoint 4: final review
stages: fresh from 02-evidence to 08-ats
new terms: none undecided
notices: none
sanitized bullets: 1 of 4 changed
  b_1  was: Cut p99 checkout latency 40% for Contoso Bank by building a Redis-backed idempotency cache for Project \
Falcon in Go
       now: Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency cache for \
real-time fraud-detection platform in Go
sanitized stories: 3 lines changed
  3  was: ## Project Falcon checkout latency
     now: ## Real-time fraud-detection platform checkout latency
  5  was: - **Situation:** Checkout for Contoso Bank missed its p99 latency target at peak traffic.
     now: - **Situation:** Checkout for a top-10 US bank missed its p99 latency target at peak traffic.
  6  was: - **Task:** Jordan led the fix for the Project Falcon checkout path.
     now: - **Task:** Jordan led the fix for the real-time fraud-detection platform checkout path.
sanitized profile: no prose changed
facts holding a denied term: none
general: 4 of 4 bullets, 36 of 50 lines (1 page for 88 months of experience)
  keywords: 4 covered, 1 missing with evidence, 1 missing without evidence
    missing with evidence  metrics  ev_56410ed1
  left out: none
  warnings: none
fintech-sre: 4 of 4 bullets, 36 of 50 lines (1 page for 88 months of experience)
  keywords: 5 covered, 1 missing with evidence, 2 missing without evidence
    missing with evidence  metrics  ev_56410ed1
  left out: none
  warnings: none
  flags: 1, 0 open
    b_1  accepted  {b1}
      introduces 'SLO compliance', which no cited source mentions
checkpoint 4: no open items
""".format(b1=B1_JOB)
FLAG_ITEM = ("fintech-sre b_1 is flagged: accept it (attest.py accept fintech-sre b_1), or revert or edit it "
             "(resume-ats: ats.py --revise fintech-sre)")


@pytest.fixture(autouse=True)
def _time(monkeypatch):
    fix_time(monkeypatch)


@pytest.fixture(scope="module")
def built_root(tmp_path_factory):
    return build_once(tmp_path_factory)


@pytest.fixture
def built(built_root, tmp_path, monkeypatch):
    return copy_of(built_root, tmp_path, monkeypatch)


def review(workspace, capsys) -> str:
    capsys.readouterr()
    assert final_review.main(ws_arg(workspace)) == 0
    return capsys.readouterr().out


def tail(out: str) -> list[str]:
    """The open items and the last line."""
    lines = out.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("open items:")), len(lines) - 1)
    return lines[start:]


def test_the_review_of_a_first_run(built, capsys):
    assert review(built, capsys) == REVIEW


def test_nothing_to_review_before_ats(built, capsys):
    shutil.rmtree(built / "08-ats")
    assert final_review.main(ws_arg(built)) == 1
    assert capsys.readouterr().err == ("error: nothing to review: 08-ats is not committed; build it with resume-ats "
                                       "first (progress.py names the next step)\n")


def test_an_unattested_flag_is_open(built, capsys):
    wsio.write_json(built / "decisions" / "attestations.json", [])
    out = review(built, capsys)
    assert f"  flags: 1, 1 open\n    b_1  flagged  {B1_JOB}\n" in out
    assert tail(out) == ["open items: 1", f"  {FLAG_ITEM}", "checkpoint 4: 1 open item"]


def new_term(workspace, term: dict) -> None:
    """Sanitize apply again, with the model listing a new term."""
    assert run(apply, workspace) == 0
    wsio.write_json(workspace / "07-sanitized.tmp" / "new-terms.json", [term])
    assert run(apply, workspace, "--commit") == 0


def test_a_new_term_is_open_until_the_wizard_decides_it(built, capsys):
    new_term(built, {"term": "Redis", "kind": "product", "proposed_replacement": "an in-memory cache"})
    out = review(built, capsys)
    assert ("new terms: 1 undecided\n  'Redis'  product, proposed 'an in-memory cache'; 3 places: b_1, stories.md:7, "
            "resume:/skills/0/keywords/2\n") in out
    assert tail(out) == ["open items: 1", "  new term 'Redis': decide it with the wizard (resume-wizard), then run "
                         "sanitize apply and ats again", "checkpoint 4: 1 open item"]

    assert run(answer, built, "term", "Redis", "--allow") == 0
    out = review(built, capsys)
    assert "new terms: none undecided\n" in out
    assert "stages: 2 not fresh\n  07-sanitized  stale  decisions/terms.json changed\n" in out
    assert tail(out)[:3] == ["open items: 2", "  07-sanitized is stale: finish the steps progress.py names first",
                             "  08-ats is stale: finish the steps progress.py names first"]


def test_every_notice_is_shown(built, capsys):
    """An allowed term that looks like a denied one is shown for the engineer to confirm, every time."""
    assert run(answer, built, "term", "ContosoBank", "--allow", "--kind", "other") == 0
    out = review(built, capsys)
    assert ("notices: 1\n  notice: allowed term 'ContosoBank' looks like denied term 'Contoso Bank'; confirm at "
            "checkpoint 4 that it is a different word\n") in out


def test_facts_holding_a_denied_term(built, capsys):
    assert run(answer, built, "term", "Northwind", "--replacement", "a payments company", "--kind", "customer") == 0
    assert run(answer, built, "term", "Redis", "--replacement", "an in-memory cache", "--kind", "product") == 0
    out = review(built, capsys)
    assert ("facts holding a denied term: 2\n"
            "  /work/0/name 'Northwind Payments' holds the denied term 'Northwind'; set a replacement value with "
            "the wizard\n"
            "  /skills/0/keywords/2 'Redis' holds the denied term 'Redis'; a keyword cannot be replaced, so "
            "resume-ats leaves it out\n") in out
    assert ("  /work/0/name 'Northwind Payments' holds the denied term 'Northwind': set a replacement value with the "
            "wizard (resume-wizard, a fact: question), then run write, sanitize apply and ats again") in tail(out)
    assert not any("/skills/0/keywords/2" in line for line in tail(out))  # a keyword is a note, not an item


def test_versions_show_left_out_bullets_warnings_and_places(built, capsys):
    report = built / "08-ats" / "general" / "report.json"
    edit_json(report, lambda r: r.update(
        left_out=[{"bullet_id": "b_3", "reason": "not selected"}],
        warnings=["jobs are not most recent first"],
        keywords=[{"keyword": "Go", "status": "missing_with_evidence",
                   "where": ["b_1", "b_3", "ev_191cc8ce", "resume:/work/1/highlights/0", "wizard:/skills/0/name"]}]))
    out = review(built, capsys)
    assert ("general: 4 of 4 bullets, 36 of 50 lines (1 page for 88 months of experience)\n"
            "  keywords: 0 covered, 1 missing with evidence, 0 missing without evidence\n"
            "    missing with evidence  Go  b_1, b_3, ev_191cc8ce and 2 more\n"
            "  left out: 1\n"
            "    b_3  not selected  Migrated the order service from PHP to Go, serving 2M requests per day\n"
            "  warnings: 1\n"
            "    jobs are not most recent first\n") in out


def test_changed_prose_and_story_lines(tmp_path):
    wsio.write_json(tmp_path / "03-profile" / "profile.json", {"basics": {"summary": "Led Project Falcon."}})
    wsio.write_json(tmp_path / "07-sanitized" / "profile.json", {"basics": {"summary": "Led a fraud platform."}})
    (tmp_path / "06-bullets").mkdir()
    (tmp_path / "06-bullets" / "stories.md").write_text("# Stories\n\n- for Contoso\n  Bank today\n- end\n",
                                                         encoding="utf-8")
    (tmp_path / "07-sanitized" / "stories.md").write_text("# Stories\n\n- for a bank today\n- end\n", encoding="utf-8")
    assert final._changed_prose(tmp_path) == [("/basics/summary", "Led Project Falcon.", "Led a fraud platform.")]
    assert final._changed_story_lines(tmp_path) == [(3, "- for Contoso", "- for a bank today"), (4, "  Bank today", None)]


@pytest.mark.parametrize("change, status", [
    (lambda r: set_text(r, "work", 0, 0, "Cut latency"), "changed after the claim diff"),
    (lambda r: r["work"][0]["x-highlights"].pop(0) and r["work"][0]["highlights"].pop(0), "not in resume.json"),
    (lambda r: r["work"][0]["x-highlights"].append(dict(r["work"][0]["x-highlights"][1])), "used twice"),
])
def test_open_flag_items_are_the_flags_check_lines(built, change, status):
    edit_json(built / "08-ats" / "jobs" / "fintech-sre" / "resume.json", change)
    job = jobs.load_job(built, "fintech-sre")
    states = jobs.flag_states(job, jobs.load_attestations(built))
    assert status in {s.status for s in states if s.is_open}
    assert sum(s.is_open for s in states) == len(flags.check_job(built, "fintech-sre"))


def test_open_flags_match_the_flags_check_when_flagged_and_when_attested(built):
    for attestations in (wsio.read_json(built / "decisions" / "attestations.json"), []):
        wsio.write_json(built / "decisions" / "attestations.json", attestations)
        states = jobs.flag_states(jobs.load_job(built, "fintech-sre"), attestations)
        assert sum(s.is_open for s in states) == len(flags.check_job(built, "fintech-sre"))
