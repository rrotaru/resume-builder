from rcore import sources, wsio

TAILORED = ["08-ats/general/resume.json", "08-ats/jobs/fintech-sre/resume.json"]


def test_fixture_bullets_and_resumes_pass(workspace):
    known = sources.load_known(workspace)
    for rel in ["06-bullets/bullets.json", "07-sanitized/bullets.json", *TAILORED]:
        assert sources.check_file(workspace, rel, known) == []


def test_load_known(workspace):
    known = sources.load_known(workspace)
    assert known.evidence_ids == {"ev_191cc8ce", "ev_56410ed1", "ev_99a74656", "ev_cbf558fa"}
    assert known.metric_ids == {"m_1"}
    assert known.profile["basics"]["name"] == "Jordan Rivera"
    assert known.wizard["basics"]["email"] == "jordan.rivera@example.com"


def test_load_known_tolerates_missing_files(tmp_path):
    known = sources.load_known(tmp_path)
    assert known.evidence_ids == set() and known.profile == {}


def test_source_error_cases(workspace):
    known = sources.load_known(workspace)
    assert sources.source_error("ev_191cc8ce", known) is None
    assert sources.source_error("ev_deadbeef", known) == "unknown evidence id"
    assert sources.source_error("metric:m_1", known) is None
    assert sources.source_error("metric:m_9", known) == "unknown metric id"
    assert sources.source_error("resume:/work/1/highlights/0", known) is None
    assert sources.source_error("resume:/work/7", known) == "does not resolve in 03-profile/profile.json"
    assert sources.source_error("wizard:/basics/email", known) is None
    assert sources.source_error("wizard:/basics/phone", known) == "does not resolve in decisions/profile.json"
    assert sources.source_error("gut-feeling", known) == "unrecognized source reference"


def test_bullet_without_sources_fails(workspace):
    path = workspace / "06-bullets" / "bullets.json"
    bullets = wsio.read_json(path)
    bullets[1]["sources"] = []
    bullets[2]["sources"] = ["ev_deadbeef"]
    wsio.write_json(path, bullets)
    assert sources.check_file(workspace, "06-bullets/bullets.json") == [
        "06-bullets/bullets.json: bullet b_2: has no sources",
        "06-bullets/bullets.json: bullet b_3: ev_deadbeef: unknown evidence id",
    ]


def test_resume_highlights_must_match_x_highlights(workspace):
    path = workspace / TAILORED[0]
    resume = wsio.read_json(path)
    resume["work"][0]["highlights"][0] = "Edited without updating x-highlights"
    wsio.write_json(path, resume)
    assert sources.check_file(workspace, TAILORED[0]) == [
        "08-ats/general/resume.json: /work/0: highlights do not match x-highlights"
    ]


def test_imported_highlights_without_x_highlights_fail(workspace):
    assert sources.check_file(workspace, "03-profile/profile.json") == [
        "03-profile/profile.json: /work/1: highlights do not match x-highlights"
    ]


def test_pointer_sources_must_name_a_single_value(workspace):
    known = sources.load_known(workspace)
    profile_err = "must point to a single value in 03-profile/profile.json"
    wizard_err = "must point to a single value in decisions/profile.json"
    assert sources.source_error("resume:", known) == profile_err
    assert sources.source_error("resume:/work", known) == profile_err
    assert sources.source_error("resume:/work/1", known) == profile_err
    assert sources.source_error("resume:/work/1/highlights", known) == profile_err
    assert sources.source_error("wizard:", known) == wizard_err
    assert sources.source_error("wizard:/basics", known) == wizard_err
    assert sources.source_error("resume:work/1/highlights/0", known) == (
        "does not resolve in 03-profile/profile.json"
    )


def test_pointer_sources_accept_strings_and_numbers_only():
    known = sources.KnownSources(profile={"s": "x", "n": 3, "f": 1.5, "b": True, "z": None})
    for ok in ["resume:/s", "resume:/n", "resume:/f"]:
        assert sources.source_error(ok, known) is None
    for bad in ["resume:/b", "resume:/z"]:
        assert sources.source_error(bad, known) == "must point to a single value in 03-profile/profile.json"


def test_container_pointer_in_bullet_fails(workspace):
    path = workspace / "06-bullets" / "bullets.json"
    bullets = wsio.read_json(path)
    bullets[2]["sources"] = ["resume:/work"]
    wsio.write_json(path, bullets)
    assert sources.check_file(workspace, "06-bullets/bullets.json") == [
        "06-bullets/bullets.json: bullet b_3: resume:/work: "
        "must point to a single value in 03-profile/profile.json"
    ]


def test_unreadable_files_are_reported_not_raised(workspace):
    assert sources.check_file(workspace, "06-bullets/nope.json") == ["06-bullets/nope.json: not found"]
    (workspace / "06-bullets" / "bullets.json").write_text("[{", encoding="utf-8")
    [error] = sources.check_file(workspace, "06-bullets/bullets.json")
    assert error.startswith("06-bullets/bullets.json: invalid JSON")


def test_unreadable_known_source_file_is_reported(workspace):
    (workspace / "decisions" / "metrics.json").write_bytes(b"\xff\xfe")
    errors = sources.check_file(workspace, "07-sanitized/bullets.json")
    assert errors[0] == "decisions/metrics.json: not UTF-8 text"


def _edit_general(workspace, change):
    path = workspace / TAILORED[0]
    resume = wsio.read_json(path)
    change(resume)
    wsio.write_json(path, resume)


def test_summary_without_sources_fails(workspace):
    _edit_general(workspace, lambda r: r["basics"].update(summary="Backend engineer"))
    assert sources.check_file(workspace, TAILORED[0]) == [
        "08-ats/general/resume.json: bullet summary: has no sources"
    ]


def test_summary_with_valid_sources_passes(workspace):
    _edit_general(workspace, lambda r: r["basics"].update(
        summary="Backend engineer", **{"x-summary-sources": ["resume:/basics/label", "ev_191cc8ce"]}))
    assert sources.check_file(workspace, TAILORED[0]) == []


def test_summary_with_unresolved_source_fails(workspace):
    _edit_general(workspace, lambda r: r["basics"].update(
        summary="Backend engineer", **{"x-summary-sources": ["resume:/basics"]}))
    assert sources.check_file(workspace, TAILORED[0]) == [
        "08-ats/general/resume.json: bullet summary: resume:/basics: "
        "must point to a single value in 03-profile/profile.json"
    ]


def test_highlights_outside_work_and_projects_fail(workspace):
    def change(resume):
        resume["education"][0]["highlights"] = ["Graduated top of class"]
        resume["skills"][0]["highlights"] = ["Unsourced claim"]
    _edit_general(workspace, change)
    assert sources.check_file(workspace, TAILORED[0]) == [
        "08-ats/general/resume.json: /education/0: highlights are only allowed in work and projects",
        "08-ats/general/resume.json: /skills/0: highlights are only allowed in work and projects",
    ]


def test_project_highlights_must_match_x_highlights(workspace):
    _edit_general(workspace, lambda r: r.update(projects=[
        {"name": "Side project", "highlights": ["Unsourced"], "x-highlights": []}]))
    assert sources.check_file(workspace, TAILORED[0]) == [
        "08-ats/general/resume.json: /projects/0: highlights do not match x-highlights"
    ]


JOB = "08-ats/jobs/fintech-sre/resume.json"
LABEL_ERROR = "basics.label must match the target role in config.json or the imported profile's label"


def _edit_job(workspace, change):
    path = workspace / JOB
    resume = wsio.read_json(path)
    change(resume)
    wsio.write_json(path, resume)


def test_load_known_reads_target_role(workspace):
    assert sources.load_known(workspace).target_role == "Senior Backend Engineer"


def test_tailored_label_must_match_target_role_or_profile(workspace):
    _edit_job(workspace, lambda r: r["basics"].update(label="CTO"))
    assert sources.check_file(workspace, JOB) == [f"{JOB}: {LABEL_ERROR}"]
    _edit_job(workspace, lambda r: r["basics"].update(label="Backend Engineer"))  # profile label
    assert sources.check_file(workspace, JOB) == []
    _edit_job(workspace, lambda r: r["basics"].pop("label"))
    assert sources.check_file(workspace, JOB) == []


def test_label_check_applies_only_to_tailored_resumes(workspace):
    known = sources.load_known(workspace)
    resume = {"basics": {"label": "CTO"}}
    assert sources.check_resume(resume, known, "03-profile/profile.json") == []
    assert sources.check_resume(resume, known, "08-ats.tmp/general/resume.json") == [
        f"08-ats.tmp/general/resume.json: {LABEL_ERROR}"
    ]
    assert sources.check_resume(resume, known, "x", tailored=True) == [f"x: {LABEL_ERROR}"]
    assert sources.check_resume({"basics": {"label": ["CTO"]}}, known, "x", tailored=True) == [
        f"x: {LABEL_ERROR}"
    ]


def test_label_check_without_config_or_profile_fails(tmp_path):
    known = sources.load_known(tmp_path)
    assert known.target_role is None
    assert sources.check_resume({"basics": {"label": "CTO"}}, known, "x", tailored=True) == [
        f"x: {LABEL_ERROR}"
    ]


def _job_spellings(workspace):
    return [
        f"./{JOB}",
        "08-ats//jobs/fintech-sre/resume.json",
        "08-ats/jobs/fintech-sre/./resume.json",
        "08-ats/jobs/../jobs/fintech-sre/resume.json",
        str(workspace / JOB),
    ]


def test_label_check_applies_to_every_spelling_of_a_tailored_path(workspace):
    _edit_job(workspace, lambda r: r["basics"].update(label="CTO"))
    for rel in _job_spellings(workspace):
        assert sources.check_file(workspace, rel) == [f"{rel}: {LABEL_ERROR}"], rel


def test_unknown_resume_paths_get_the_tailored_checks(workspace):
    known = sources.load_known(workspace)
    resume = {"basics": {"label": "CTO"}}
    for rel in ["x", "08-ats/jobs/a/b/resume.json", "notes/resume.json", "/abs/03-profile/profile.json"]:
        assert sources.check_resume(resume, known, rel) == [f"{rel}: {LABEL_ERROR}"], rel
    for rel in ["03-profile/profile.json", "./07-sanitized/profile.json", "decisions//profile.json",
                "07-sanitized.tmp/profile.json"]:
        assert sources.check_resume(resume, known, rel) == [], rel


def test_absolute_profile_path_inside_workspace_is_a_profile(workspace):
    rel = str(workspace / "03-profile" / "profile.json")
    assert sources.check_file(workspace, rel) == [f"{rel}: /work/1: highlights do not match x-highlights"]


def test_path_outside_the_workspace_is_an_error(workspace):
    assert sources.check_file(workspace, "../outside.json") == ["../outside.json: outside the workspace"]
