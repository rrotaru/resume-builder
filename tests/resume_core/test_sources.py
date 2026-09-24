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
