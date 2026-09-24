from rcore import flags, ids, wsio

JOB = "fintech-sre"
RESUME = f"08-ats/jobs/{JOB}/resume.json"


def test_attested_flag_passes(workspace):
    assert flags.check_job(workspace, JOB) == []


def test_unattested_flag_fails(workspace):
    wsio.write_json(workspace / "decisions" / "attestations.json", [])
    assert flags.check_job(workspace, JOB) == [
        "08-ats/jobs/fintech-sre: b_1 is flagged (introduces 'SLO compliance', which no "
        "cited source mentions); accept, revert or edit it"
    ]


def test_edit_after_attestation_invalidates_it(workspace):
    resume = wsio.read_json(workspace / RESUME)
    new_text = resume["work"][0]["x-highlights"][0]["text"] + " across 12 regions"
    resume["work"][0]["x-highlights"][0]["text"] = new_text
    resume["work"][0]["highlights"][0] = new_text
    wsio.write_json(workspace / RESUME, resume)
    assert flags.check_job(workspace, JOB) == [
        "08-ats/jobs/fintech-sre: b_1 changed since it was flagged; re-run the claim diff"
    ]


def test_edited_text_with_matching_attestation_passes(workspace):
    resume = wsio.read_json(workspace / RESUME)
    new_text = "Cut p99 checkout latency 40% for a top-10 US bank with a Redis idempotency cache"
    resume["work"][0]["x-highlights"][0]["text"] = new_text
    resume["work"][0]["highlights"][0] = new_text
    wsio.write_json(workspace / RESUME, resume)
    wsio.write_json(workspace / "decisions" / "attestations.json", [
        {"job_slug": JOB, "bullet_id": "b_1", "text_sha256": ids.text_sha256(new_text), "action": "edit"}
    ])
    assert flags.check_job(workspace, JOB) == []


def test_flag_for_missing_bullet_is_stale(workspace):
    path = workspace / f"08-ats/jobs/{JOB}/flags.json"
    flag_list = wsio.read_json(path)
    flag_list[0]["bullet_id"] = "b_99"
    wsio.write_json(path, flag_list)
    assert flags.check_job(workspace, JOB) == [
        "08-ats/jobs/fintech-sre: flag for b_99, which is not in resume.json; re-run the claim diff"
    ]


def test_attestation_for_another_job_does_not_count(workspace):
    atts = wsio.read_json(workspace / "decisions" / "attestations.json")
    atts[0]["job_slug"] = "other-job"
    wsio.write_json(workspace / "decisions" / "attestations.json", atts)
    assert len(flags.check_job(workspace, JOB)) == 1


def test_missing_files(workspace):
    assert flags.check_job(workspace, "nope") == ["08-ats/jobs/nope/resume.json: not found"]
    (workspace / f"08-ats/jobs/{JOB}/flags.json").unlink()
    assert flags.check_job(workspace, JOB) == [
        "08-ats/jobs/fintech-sre/flags.json: not found; run the claim diff for this job"
    ]
