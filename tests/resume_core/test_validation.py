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
