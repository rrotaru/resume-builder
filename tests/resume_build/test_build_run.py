"""A first run end to end, following progress.py's next step at every step."""
import final_review
import progress
import pytest
from build_samples import fix_time, first_run, next_line, same_as_fixture, ws_arg
from rcore import flags, stages, validation
from rrender import gate

GATE = "wizard: checkpoint 3 until questions.py prints 'wizard: no open questions' (resume-wizard); then "
NEVER_BEGIN = "never run stage.py begin 01-raw, which deletes it"
NEXT = {
    "start": "init: create the workspace and config.json (resume-init)",
    "init": "collect: checkpoint 1: confirm the sources and collect (resume-collect)",
    "fetched": f"collect: continue the collection in 01-raw.tmp/ (resume-collect steps 5 to 8); {NEVER_BEGIN}",
    "collected": "import: import {engineer}/resume.txt (resume-import)",
    "extracted": "import: map 03-profile.tmp/resume.txt into profile.json, then check_profile.py --commit "
                 "(resume-import steps 4 and 5)",
    "mapped": "import: check and commit it with check_profile.py --commit (resume-import step 5)",
    "imported": "analyze: checkpoint 2: find and review the projects (resume-analyze)",
    "signals": "analyze: group the evidence into 04-projects.tmp/groups.json (resume-analyze step 3)",
    "grouped": "analyze: continue checkpoint 2 with match_projects.py (resume-analyze step 5)",
    "analyzed": "scan: scan.py (resume-sanitize, scan)",
    "candidates": "scan: scan.py --commit (resume-sanitize, scan step 5)",
    "scanned": GATE + "write: write the bullets and stories: write.py, then write.py --commit (resume-write)",
    "wizard": GATE + "write: write the bullets and stories: write.py, then write.py --commit (resume-write)",
    "bullets": "write: write.py --commit (resume-write step 6)",
    "written": GATE + "apply: apply.py, then apply.py --commit (resume-sanitize, apply)",
    "new terms": "apply: apply.py --commit; if it says the inputs changed, apply.py again "
                 "(resume-sanitize, apply step 5)",
    "applied": GATE + "ats: draft and commit the general resume, then each posting (resume-ats)",
    "general drafted": "ats: continue with ats.py --commit, or start over from the committed stage with stage.py "
                       "begin 08-ats --from-current (resume-ats)",
    "general": "review: checkpoint 4 (final_review.py), then render (resume-render)",
    "job": "review: checkpoint 4: final_review.py lists the open items",
    "attested": "review: checkpoint 4 (final_review.py), then render (resume-render)",
}
PROGRESS = """\
resume-builder run in {ws} (target role: Senior Backend Engineer)
 1. init     done     config.json and decisions/
 2. collect  fresh    4 items (github 2, jira 1, review 1), built 2026-09-27 (today)
 3. import   fresh    {engineer}/resume.txt, unchanged since the import
 4. analyze  fresh    1 project (0 excluded), metric prompts for 1, 1 decision
 5. scan     fresh    2 candidates
 6. wizard   check    checkpoint 3: questions.py lists what is open
 7. write    fresh    4 bullets (1 quantified), 1 story
 8. apply    fresh    1 of 4 bullets changed, 0 new terms
 9. ats      fresh    general, fintech-sre: 1 flagged, 0 open
10. review   ready    checkpoint 4: no open items
11. render   missing
next: review: checkpoint 4 (final_review.py), then render (resume-render)
"""
COMMITTED = ["02-evidence/evidence.jsonl", "03-profile/profile.json", "03-profile/resume.txt",
             "04-projects/signals.json", "04-projects/groups.json", "04-projects/projects.json",
             "05-terms/candidates.json", "06-bullets/bullets.json", "06-bullets/stories.md",
             "07-sanitized/bullets.json", "07-sanitized/profile.json", "07-sanitized/stories.md",
             "07-sanitized/new-terms.json"] + [
    f"08-ats/{rel}" for rel in ("general/keywords.json", "general/report.json", "general/resume.json",
                                "jobs/fintech-sre/flags.json", "jobs/fintech-sre/jd.txt",
                                "jobs/fintech-sre/keywords.json", "jobs/fintech-sre/report.json",
                                "jobs/fintech-sre/resume.json")]
DECISIONS = ["terms.json", "projects.json", "metrics.json", "profile.json", "attestations.json", "wizard.json"]


@pytest.fixture(autouse=True)
def _time(monkeypatch):
    fix_time(monkeypatch)


def test_a_first_run_follows_the_next_step_to_the_fixture(tmp_path, capsys):
    seen = []

    def check(label):
        engineer = tmp_path / "engineer"
        assert next_line(tmp_path / "ws") == NEXT[label].format(engineer=engineer), label
        seen.append(label)
        attestations = tmp_path / "ws" / "decisions" / "attestations.json"
        if label not in ("start", "attested"):  # nothing but attest.py writes attestations
            assert attestations.read_text(encoding="utf-8") == "[]\n", label

    ws = first_run(tmp_path, check)
    assert seen == list(NEXT)
    for rel in COMMITTED:
        assert same_as_fixture(ws, rel), rel
    for name in DECISIONS:
        assert same_as_fixture(ws, f"decisions/{name}"), name
    assert validation.validate_workspace(ws) == []
    status = stages.status(ws)
    assert all(status[stage] == "fresh" for stage in stages.STAGES if stage != "out")
    assert flags.check_job(ws, "fintech-sre") == []
    targets, _ = gate.discover(ws)
    assert gate.run(ws, targets) == []

    capsys.readouterr()
    assert progress.main(ws_arg(ws)) == 0
    assert capsys.readouterr().out == PROGRESS.format(ws=ws.resolve(), engineer=tmp_path / "engineer")
    assert final_review.main(ws_arg(ws)) == 0
    assert capsys.readouterr().out.endswith("\ncheckpoint 4: no open items\n")
