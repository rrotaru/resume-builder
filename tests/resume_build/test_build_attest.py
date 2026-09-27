"""attest.py, the only writer of decisions/attestations.json, and checkpoint 4's accept, revert and edit."""
import re
from pathlib import Path

import ats
import attest
import pytest
from build_samples import (B1_JOB, B1_SANITIZED, build_once, copy_of, draft_path, edit_json, fix_time, fixture,
                           run, set_text)
from rcore import flags, ids, stages, wsio

ATTESTATIONS = Path("decisions") / "attestations.json"
EDITED = "Cut p99 checkout latency 40% for a top-10 US bank with a Redis-backed idempotency cache in Go, raising SLO"
SKILLS = Path(__file__).resolve().parents[2] / "skills"


@pytest.fixture(autouse=True)
def _time(monkeypatch):
    fix_time(monkeypatch)


@pytest.fixture(scope="module")
def built_root(tmp_path_factory):
    return build_once(tmp_path_factory)


@pytest.fixture
def built(built_root, tmp_path, monkeypatch):
    return copy_of(built_root, tmp_path, monkeypatch)


@pytest.fixture
def unattested(built):
    wsio.write_json(built / ATTESTATIONS, [])
    return built


def attestations(workspace) -> list[dict]:
    return wsio.read_json(workspace / ATTESTATIONS)


def revise(workspace, text: str) -> None:
    """Checkpoint 4 changes a job bullet through resume-ats: --revise, a new text, --commit."""
    assert run(ats, workspace, "--revise", "fintech-sre") == 0
    edit_json(draft_path(workspace, "fintech-sre"), lambda r: set_text(r, "work", 0, 0, text))
    assert run(ats, workspace, "--commit") == 0


# Accept, revert, edit -------------------------------------------------------------------

def test_accept_records_the_flag_as_the_fixture_does(unattested, capsys):
    assert flags.check_job(unattested, "fintech-sre")  # flagged, and render would refuse it
    assert run(attest, unattested, "accept", "fintech-sre", "b_1") == 0
    assert capsys.readouterr().out == (f"recorded: fintech-sre b_1 accept for its current text: {B1_JOB}\n"
                                       "fintech-sre: no open flags\n")
    assert (unattested / ATTESTATIONS).read_bytes() == fixture("decisions/attestations.json").read_bytes()
    assert flags.check_job(unattested, "fintech-sre") == []
    assert stages.status(unattested)["08-ats"] == "fresh"  # 08-ats never records attestations


def test_revert_needs_no_attestation(unattested, capsys):
    revise(unattested, B1_SANITIZED)  # the bullet's original text
    assert wsio.read_json(unattested / "08-ats/jobs/fintech-sre/flags.json")["flags"] == []
    assert flags.check_job(unattested, "fintech-sre") == []
    capsys.readouterr()
    assert run(attest, unattested, "accept", "fintech-sre", "b_1") == 1
    assert capsys.readouterr().err == ("error: b_1 is not flagged in fintech-sre: nothing to attest\n"
                                       "decisions/attestations.json unchanged\n")
    assert attestations(unattested) == []


def test_an_edit_still_flagged_is_attested_for_its_new_hash(unattested, capsys):
    revise(unattested, EDITED)
    [flag] = wsio.read_json(unattested / "08-ats/jobs/fintech-sre/flags.json")["flags"]
    assert flag["text"] == EDITED
    assert run(attest, unattested, "edit", "fintech-sre", "b_1") == 0
    assert attestations(unattested) == [{"job_slug": "fintech-sre", "bullet_id": "b_1",
                                         "text_sha256": ids.text_sha256(EDITED), "action": "edit"}]
    assert flags.check_job(unattested, "fintech-sre") == []


def test_an_attestation_for_an_unchanged_text_survives_a_redraft(built):
    """The fixture's attestation is for B1_JOB. A redraft reverts the text; writing it again needs no new one."""
    before = attestations(built)
    assert run(ats, built, "--job", "fintech-sre") == 0
    assert run(ats, built, "--commit") == 0
    assert flags.check_job(built, "fintech-sre") == []  # the original text is not flagged
    revise(built, B1_JOB)
    assert flags.check_job(built, "fintech-sre") == []
    assert attestations(built) == before


def test_the_same_attestation_twice_records_nothing_and_another_action_replaces_it(built, capsys):
    before = (built / ATTESTATIONS).read_bytes()
    assert run(attest, built, "accept", "fintech-sre", "b_1") == 0
    assert "fintech-sre b_1 is attested already (accept); nothing recorded\n" in capsys.readouterr().out
    assert (built / ATTESTATIONS).read_bytes() == before
    assert run(attest, built, "edit", "fintech-sre", "b_1") == 0
    assert capsys.readouterr().out.startswith("recorded: fintech-sre b_1 changed from accept to edit for its ")
    assert [a["action"] for a in attestations(built)] == ["edit"]


def test_withdraw_opens_the_flag_again(built, capsys):
    assert run(attest, built, "withdraw", "fintech-sre", "b_1") == 0
    assert capsys.readouterr().out == ("withdrew the attestation of fintech-sre b_1\n"
                                       "fintech-sre: 1 open (final_review.py lists them)\n")
    assert attestations(built) == []
    assert run(attest, built, "withdraw", "fintech-sre", "b_1") == 1
    assert "error: no attestation for the current text of b_1 in fintech-sre: nothing to withdraw\n" in \
        capsys.readouterr().err


def test_list(built, capsys):
    wsio.write_json(built / ATTESTATIONS, attestations(built) + [
        {"job_slug": "fintech-sre", "bullet_id": "b_2", "text_sha256": "0" * 64, "action": "edit"}])
    assert run(attest, built, "list") == 0
    assert capsys.readouterr().out == (
        "1. fintech-sre b_1 accept f6c1490f4c91: applies to the committed text\n"
        "2. fintech-sre b_2 edit 000000000000: no committed text has this hash (kept: it applies again if the text "
        "returns)\n")
    wsio.write_json(built / ATTESTATIONS, [])
    assert run(attest, built, "list") == 0
    assert capsys.readouterr().out == "no attestations\n"


# Refusals leave the file unchanged ------------------------------------------------------

@pytest.mark.parametrize("args, error", [
    (["accept", "general", "b_1"], "'general' is not a job slug (lower-case letters, digits and '-', not 'general')"),
    (["accept", "Fintech", "b_1"], "'Fintech' is not a job slug (lower-case letters, digits and '-', not 'general')"),
    (["accept", "other-job", "b_1"], "08-ats/jobs/other-job/resume.json: not found"),
    (["accept", "fintech-sre", "b_9"], "08-ats/jobs/fintech-sre/resume.json has no bullet b_9"),
    (["accept", "fintech-sre", "summary"], "08-ats/jobs/fintech-sre/resume.json has no basics.summary"),
    (["edit", "fintech-sre", "b_2"], "b_2 is not flagged in fintech-sre: nothing to attest"),
])
def test_refusals(unattested, capsys, args, error):
    assert run(attest, unattested, *args) == 1
    err = capsys.readouterr().err
    assert f"error: {error}\n" in err and err.endswith("decisions/attestations.json unchanged\n")
    assert attestations(unattested) == []


def test_a_job_only_in_the_draft_is_refused(unattested, tmp_path, capsys):
    posting = tmp_path / "other.txt"
    posting.write_text("Backend Engineer\nGo and Redis.\n", encoding="utf-8")
    assert run(ats, unattested, "--jd", posting) == 0
    capsys.readouterr()
    assert run(attest, unattested, "accept", "other", "b_1") == 1
    assert "other is not a committed job version; draft and commit it with resume-ats" in capsys.readouterr().err


def test_a_text_changed_after_the_claim_diff_is_refused(unattested, capsys):
    edit_json(unattested / "08-ats/jobs/fintech-sre/resume.json", lambda r: set_text(r, "work", 0, 0, EDITED))
    assert run(attest, unattested, "accept", "fintech-sre", "b_1") == 1
    assert ("error: b_1 in fintech-sre changed after the claim diff; commit 08-ats again first: stage.py begin "
            "08-ats --from-current, then ats.py --commit (resume-ats)\n") in capsys.readouterr().err
    assert attestations(unattested) == []


def test_an_invalid_attestations_file_is_refused(unattested, capsys):
    (unattested / ATTESTATIONS).write_text('[{"job_slug": "fintech-sre"}]\n', encoding="utf-8")
    assert run(attest, unattested, "accept", "fintech-sre", "b_1") == 1
    err = capsys.readouterr().err
    assert "error: decisions/attestations.json: " in err
    assert "decisions/attestations.json is not valid; it is written by attest.py" in err
    assert (unattested / ATTESTATIONS).read_text(encoding="utf-8") == '[{"job_slug": "fintech-sre"}]\n'


def test_a_draft_gets_a_note_and_a_stale_stage_a_warning(unattested, capsys):
    assert run(ats, unattested, "--revise", "general") == 0
    wsio.write_json(unattested / "decisions" / "metrics.json", [])  # makes 08-ats stale
    capsys.readouterr()
    assert run(attest, unattested, "accept", "fintech-sre", "b_1") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == ("warning: 08-ats is stale; rebuild it (progress.py names the step) and check its flags "
                      "again")
    assert out[1].startswith("note: 08-ats.tmp/ holds a draft; this attests the committed text")
    assert out[2].startswith("recorded: fintech-sre b_1 accept")


def test_attesting_makes_a_render_stale_and_leaves_08_ats_fresh(unattested):
    stages.begin(unattested, "out")
    assert stages.commit(unattested, "out", ["08-ats", "decisions/attestations.json"]) == []
    assert run(attest, unattested, "accept", "fintech-sre", "b_1") == 0
    status = stages.status(unattested)
    assert (status["08-ats"], status["out"]) == ("fresh", "stale")


# Only attest.py writes attestations -------------------------------------------------------

def test_no_other_script_writes_attestations():
    """Outside resume-build, scripts name decisions/attestations.json only to read it, map its schema or create
    it empty at init; inside it, only attest.py saves it."""
    naming = {path.relative_to(SKILLS).as_posix() for path in SKILLS.rglob("*.py")
              if re.search(r"attestations\.json|ATTESTATIONS", path.read_text(encoding="utf-8"))}
    assert {p for p in naming if not p.startswith("resume-build/")} == {
        "resume-core/scripts/rcore/flags.py",        # reads it for the flags check
        "resume-core/scripts/rcore/validation.py",   # maps its schema
        "resume-core/scripts/rcore/workspace.py",    # init creates it as []
        "resume-render/scripts/rrender/gate.py",     # render reads it and records it as an input
        "resume-ats/scripts/rats/common.py",         # a comment: 08-ats never records it
    }
    for path in SKILLS.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        writes = re.findall(r"^.*(?:write_json|write_text|os\.replace|_save)\(.*$", text, re.MULTILINE)
        rel = path.relative_to(SKILLS).as_posix()
        if rel != "resume-build/scripts/attest.py":
            assert not [line for line in writes if "ATTESTATIONS" in line or "attestations" in line], rel
    assert "_save(workspace" in (SKILLS / "resume-build/scripts/attest.py").read_text(encoding="utf-8")
