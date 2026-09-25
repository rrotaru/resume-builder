import json

from rcore import validation, wsio


def test_fixture_workspace_is_valid(workspace):
    assert validation.validate_workspace(workspace) == []


def test_schema_for_maps_paths():
    assert validation.schema_for("02-evidence/evidence.jsonl") == ("evidence", "jsonl")
    assert validation.schema_for("08-ats/jobs/acme/flags.json") == ("flags", "json")
    assert validation.schema_for("06-bullets.tmp/bullets.json") == ("bullets", "json")
    assert validation.schema_for("04-projects/_stage.json") == ("stage", "json")
    assert validation.schema_for("08-ats/jobs/a/b/flags.json") is None
    assert validation.schema_for("01-raw/github.jsonl") is None


def test_logical_path():
    assert validation.logical_path("06-bullets.tmp/bullets.json") == "06-bullets/bullets.json"
    assert validation.logical_path("06-bullets.tmp") == "06-bullets"
    assert validation.logical_path("config.json") == "config.json"


def test_bad_evidence_record_is_reported_with_record_number(workspace):
    path = workspace / "02-evidence" / "evidence.jsonl"
    records = wsio.read_jsonl(path)
    records[1]["id"] = "ev_BAD"
    wsio.write_jsonl(path, records)
    errors = validation.validate_paths(workspace, ["02-evidence"])
    assert len(errors) == 1
    assert errors[0].startswith("02-evidence/evidence.jsonl: record 2: $.id:")


def test_invalid_json_is_reported(workspace):
    (workspace / "04-projects" / "projects.json").write_text("[{", encoding="utf-8")
    errors = validation.validate_paths(workspace, ["04-projects/projects.json"])
    assert len(errors) == 1 and errors[0].startswith("04-projects/projects.json: ")


def test_duplicate_ids_are_reported(workspace):
    path = workspace / "06-bullets" / "bullets.json"
    bullets = wsio.read_json(path)
    bullets.append(dict(bullets[0]))
    wsio.write_json(path, bullets)
    assert validation.validate_paths(workspace, ["06-bullets"]) == [
        "06-bullets/bullets.json: duplicate id 'b_1'"
    ]


def test_tmp_folder_is_validated_with_committed_schema(workspace):
    tmp = workspace / "06-bullets.tmp"
    tmp.mkdir()
    (tmp / "bullets.json").write_text(json.dumps([{"id": "b_1"}]), encoding="utf-8")
    errors = validation.validate_paths(workspace, ["06-bullets.tmp"])
    assert errors and all(e.startswith("06-bullets.tmp/bullets.json: $[0]: missing") for e in errors)


def test_workspace_validation_skips_tmp_and_old(workspace):
    for name in ("06-bullets.tmp", "06-bullets.old"):
        (workspace / name).mkdir()
        (workspace / name / "bullets.json").write_text("not json", encoding="utf-8")
    assert validation.validate_workspace(workspace) == []


def test_missing_path_is_an_error(workspace):
    assert validation.validate_paths(workspace, ["nope.json"]) == ["nope.json: not found"]


def test_non_utf8_file_is_reported(workspace):
    (workspace / "04-projects" / "projects.json").write_bytes(b"\xff\xfe[]")
    assert validation.validate_paths(workspace, ["04-projects/projects.json"]) == [
        "04-projects/projects.json: not UTF-8 text"
    ]


GENERAL = "08-ats/general/resume.json"


def _edit(workspace, change):
    resume = wsio.read_json(workspace / GENERAL)
    change(resume)
    wsio.write_json(workspace / GENERAL, resume)
    return validation.validate_paths(workspace, [GENERAL])


def test_tailored_resumes_use_the_closed_schema():
    assert validation.schema_for(GENERAL) == ("tailored-resume", "json")
    assert validation.schema_for("08-ats/jobs/acme/resume.json") == ("tailored-resume", "json")
    assert validation.schema_for("03-profile/profile.json") == ("resume", "json")


def test_tailored_resume_rejects_unknown_section(workspace):
    errors = _edit(workspace, lambda r: r.update(volunteer=[{"organization": "X", "highlights": ["Y"]}]))
    assert errors == [f"{GENERAL}: $.volunteer: unexpected property"]


def test_tailored_resume_work_entry_needs_x_highlights(workspace):
    errors = _edit(workspace, lambda r: r["work"][1].pop("x-highlights"))
    assert errors == [f"{GENERAL}: $.work[1]: missing required property 'x-highlights'"]


def test_tailored_resume_summary_sources_cannot_be_empty(workspace):
    errors = _edit(workspace, lambda r: r["basics"].update(
        summary="Backend engineer", **{"x-summary-sources": []}))
    assert errors == [f"{GENERAL}: $.basics.x-summary-sources: needs at least 1 items"]


JOB = "08-ats/jobs/fintech-sre/resume.json"


def _edit_job(workspace, change):
    resume = wsio.read_json(workspace / JOB)
    change(resume)
    wsio.write_json(workspace / JOB, resume)
    return validation.validate_paths(workspace, [JOB])


def test_tailored_work_entry_rejects_summary_and_description(workspace):
    assert _edit_job(workspace, lambda r: r["work"][0].update(summary="Led payments")) == [
        f"{JOB}: $.work[0].summary: unexpected property"
    ]
    assert _edit_job(workspace, lambda r: (r["work"][0].pop("summary"),
                                           r["work"][0].update(description="Led payments"))) == [
        f"{JOB}: $.work[0].description: unexpected property"
    ]


def test_tailored_resume_objects_are_closed(workspace):
    def change(resume):
        resume["basics"]["objective"] = "x"
        resume["basics"]["location"]["planet"] = "Earth"
        resume["basics"]["profiles"] = [{"network": "GitHub", "username": "jr", "note": "x"}]
        resume["projects"] = [{"name": "P", "x-highlights": [], "highlights": [], "keywords": ["x"]}]
        resume["education"][0]["courses"] = ["x"]
        resume["certificates"] = [{"name": "CKA", "summary": "x"}]
        resume["skills"][0]["summary"] = "x"
    assert _edit_job(workspace, change) == [
        f"{JOB}: $.basics.location.planet: unexpected property",
        f"{JOB}: $.basics.objective: unexpected property",
        f"{JOB}: $.basics.profiles[0].note: unexpected property",
        f"{JOB}: $.education[0].courses: unexpected property",
        f"{JOB}: $.skills[0].summary: unexpected property",
        f"{JOB}: $.projects[0].keywords: unexpected property",
        f"{JOB}: $.certificates[0].summary: unexpected property",
    ]


def test_tailored_resume_accepts_every_allowed_field(workspace):
    def change(resume):
        resume["basics"].update(phone="555-0100", url="https://example.com", summary="Engineer",
                                **{"x-summary-sources": ["ev_191cc8ce"]},
                                profiles=[{"network": "GitHub", "username": "jr", "url": "https://x"}])
        resume["basics"]["location"].update(address="1 Main St", postalCode="80202", countryCode="US")
        resume["work"][0].update(url="https://x", location="Denver", endDate="2024-01")
        resume["projects"] = [{"name": "P", "position": "Lead", "url": "https://x", "location": "Remote",
                               "startDate": "2023", "endDate": "2024", "highlights": [],
                               "x-highlights": [], "x-sources": ["ev_191cc8ce"]}]
        resume["education"][0].update(url="https://x", startDate="2015", score="3.8")
        resume["certificates"] = [{"name": "CKA", "date": "2024-05", "issuer": "CNCF", "url": "https://x",
                                   "x-sources": ["ev_191cc8ce"]}]
        resume["skills"][0].update(level="Expert", **{"x-sources": ["ev_191cc8ce"]})
    assert _edit_job(workspace, change) == []
