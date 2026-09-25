import pytest

from rcore import flags, ids, wsio

JOB = "fintech-sre"
RESUME = f"08-ats/jobs/{JOB}/resume.json"
FLAGS = f"08-ats/jobs/{JOB}/flags.json"
LABEL = "08-ats/jobs/fintech-sre"


def _rewrite(workspace, work, index, new_text):
    resume = wsio.read_json(workspace / RESUME)
    resume["work"][work]["x-highlights"][index]["text"] = new_text
    resume["work"][work]["highlights"][index] = new_text
    wsio.write_json(workspace / RESUME, resume)


def test_fixture_checked_hashes_match_resume():
    from conftest import FIXTURE_WORKSPACE
    resume = wsio.read_json(FIXTURE_WORKSPACE / RESUME)
    checked = wsio.read_json(FIXTURE_WORKSPACE / FLAGS)["checked"]
    assert checked == {h["bullet_id"]: ids.text_sha256(h["text"])
                       for _, h in wsio.resume_highlights(resume)}


def test_attested_flag_passes(workspace):
    assert flags.check_job(workspace, JOB) == []


def test_unattested_flag_fails(workspace):
    wsio.write_json(workspace / "decisions" / "attestations.json", [])
    assert flags.check_job(workspace, JOB) == [
        f"{LABEL}: b_1 is flagged (introduces 'SLO compliance', which no "
        "cited source mentions); accept, revert or edit it"
    ]


def test_unflagged_bullet_rewritten_after_claim_diff_fails(workspace):
    _rewrite(workspace, 0, 1, "Saved the company $40M single-handedly")
    assert flags.check_job(workspace, JOB) == [
        f"{LABEL}: b_2 changed after the claim diff; re-run the claim diff"
    ]


def test_bullet_missing_from_checked_fails(workspace):
    data = wsio.read_json(workspace / FLAGS)
    del data["checked"]["b_3"]
    wsio.write_json(workspace / FLAGS, data)
    assert flags.check_job(workspace, JOB) == [
        f"{LABEL}: b_3 changed after the claim diff; re-run the claim diff"
    ]


def test_edit_after_attestation_invalidates_it(workspace):
    resume = wsio.read_json(workspace / RESUME)
    _rewrite(workspace, 0, 0, resume["work"][0]["x-highlights"][0]["text"] + " across 12 regions")
    assert flags.check_job(workspace, JOB) == [
        f"{LABEL}: b_1 changed after the claim diff; re-run the claim diff"
    ]


def test_edited_text_with_matching_attestation_passes(workspace):
    new_text = "Cut p99 checkout latency 40% for a top-10 US bank with a Redis idempotency cache"
    _rewrite(workspace, 0, 0, new_text)
    wsio.write_json(workspace / "decisions" / "attestations.json", [
        {"job_slug": JOB, "bullet_id": "b_1", "text_sha256": ids.text_sha256(new_text), "action": "edit"}
    ])
    assert flags.check_job(workspace, JOB) == []


def test_flag_for_missing_bullet_is_stale(workspace):
    data = wsio.read_json(workspace / FLAGS)
    data["flags"][0]["bullet_id"] = "b_99"
    wsio.write_json(workspace / FLAGS, data)
    assert flags.check_job(workspace, JOB) == [
        f"{LABEL}: flag for b_99, which is not in resume.json; re-run the claim diff"
    ]


def test_checked_entry_for_missing_bullet_is_stale(workspace):
    data = wsio.read_json(workspace / FLAGS)
    data["checked"]["b_98"] = "0" * 64
    wsio.write_json(workspace / FLAGS, data)
    assert flags.check_job(workspace, JOB) == [
        f"{LABEL}: checked entry for b_98, which is not in resume.json; re-run the claim diff"
    ]


def test_duplicate_bullet_id_in_resume_fails(workspace):
    resume = wsio.read_json(workspace / RESUME)
    resume["work"][1]["x-highlights"][0]["bullet_id"] = "b_2"
    wsio.write_json(workspace / RESUME, resume)
    errors = flags.check_job(workspace, JOB)
    assert f"{LABEL}: b_2 appears more than once in resume.json" in errors


def test_attestation_for_another_job_does_not_count(workspace):
    atts = wsio.read_json(workspace / "decisions" / "attestations.json")
    atts[0]["job_slug"] = "other-job"
    wsio.write_json(workspace / "decisions" / "attestations.json", atts)
    assert len(flags.check_job(workspace, JOB)) == 1


def test_old_list_format_is_rejected(workspace):
    wsio.write_json(workspace / FLAGS, wsio.read_json(workspace / FLAGS)["flags"])
    errors = flags.check_job(workspace, JOB)
    assert errors and all(e.startswith(f"{FLAGS}: $: expected object") for e in errors)


def test_missing_files(workspace):
    assert flags.check_job(workspace, "nope") == ["08-ats/jobs/nope/resume.json: not found"]
    (workspace / FLAGS).unlink()
    assert flags.check_job(workspace, JOB) == [
        f"{FLAGS}: not found; run the claim diff for this job"
    ]


def test_unreadable_files_are_reported_not_raised(workspace):
    (workspace / FLAGS).write_bytes(b"\xff\xfe")
    assert flags.check_job(workspace, JOB) == [f"{FLAGS}: not UTF-8 text"]
    (workspace / "decisions" / "attestations.json").write_text("[", encoding="utf-8")
    (workspace / FLAGS).write_text("{}", encoding="utf-8")
    errors = flags.check_job(workspace, JOB)
    assert any(e.startswith("decisions/attestations.json: invalid JSON") for e in errors)


@pytest.mark.parametrize("slug", ["./fintech-sre", "fintech-sre/", "../jobs/fintech-sre",
                                  "Fintech-SRE", "-x", "", "a/b"])
def test_job_slug_must_be_a_single_plain_name(workspace, slug):
    assert flags.check_job(workspace, slug) == [f"{slug}: job slug must be a single plain name"]
