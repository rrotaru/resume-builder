import pytest

from rcore import stages, wsio

BULLET = {"id": "b_9", "project_id": None, "work_ref": 0, "text": "Did X",
          "form": "xyz", "sources": ["ev_cbf558fa"]}


def _write_bullets(workspace, bullets):
    tmp = stages.begin(workspace, "06-bullets")
    wsio.write_json(tmp / "bullets.json", bullets)
    return tmp


def test_begin_rejects_unknown_stage(workspace):
    with pytest.raises(ValueError, match="unknown stage"):
        stages.begin(workspace, "09-nope")


def test_begin_discards_leftover_tmp(workspace):
    tmp = stages.begin(workspace, "06-bullets")
    (tmp / "junk.txt").write_text("x")
    assert list(stages.begin(workspace, "06-bullets").iterdir()) == []


def test_commit_swaps_in_new_output_and_records_inputs(workspace):
    _write_bullets(workspace, [BULLET])
    errors = stages.commit(workspace, "06-bullets", ["04-projects", "decisions/metrics.json"])
    assert errors == []
    assert not (workspace / "06-bullets.tmp").exists()
    assert not (workspace / "06-bullets.old").exists()
    assert wsio.read_json(workspace / "06-bullets" / "bullets.json") == [BULLET]
    meta = wsio.read_json(workspace / "06-bullets" / "_stage.json")
    assert meta["stage"] == "06-bullets"
    assert set(meta["inputs"]) == {"04-projects", "decisions/metrics.json"}
    assert all(v.startswith("sha256:") for v in meta["inputs"].values())


def test_commit_with_invalid_output_keeps_previous_stage(workspace):
    before = wsio.read_json(workspace / "06-bullets" / "bullets.json")
    _write_bullets(workspace, [{"id": "b_1", "text": ""}])
    errors = stages.commit(workspace, "06-bullets", ["04-projects"])
    assert errors and errors[0].startswith("06-bullets.tmp/bullets.json:")
    assert wsio.read_json(workspace / "06-bullets" / "bullets.json") == before
    assert (workspace / "06-bullets.tmp").is_dir()


def test_commit_requires_begin_and_existing_inputs(workspace):
    assert stages.commit(workspace, "06-bullets", []) == ["06-bullets.tmp: not found; run begin first"]
    _write_bullets(workspace, [BULLET])
    assert stages.commit(workspace, "06-bullets", ["04-projects/nope.json"]) == [
        "input not found: 04-projects/nope.json"
    ]


def test_hash_path_directory_ignores_stage_meta(workspace):
    before = stages.hash_path(workspace / "04-projects")
    wsio.write_json(workspace / "04-projects" / "_stage.json", {"anything": 1})
    assert stages.hash_path(workspace / "04-projects") == before
    (workspace / "04-projects" / "extra.json").write_text("{}")
    assert stages.hash_path(workspace / "04-projects") != before


def _commit_chain(workspace):
    for stage, inputs in [("04-projects", ["02-evidence"]), ("06-bullets", ["04-projects"])]:
        tmp = stages.begin(workspace, stage)
        for f in (workspace / stage).iterdir():
            if f.name != "_stage.json":
                (tmp / f.name).write_bytes(f.read_bytes())
        assert stages.commit(workspace, stage, inputs) == []


def test_status_fresh_missing_and_stale(workspace):
    _commit_chain(workspace)
    status = stages.status(workspace)
    assert status["04-projects"] == "fresh"
    assert status["06-bullets"] == "fresh"
    assert status["02-evidence"] == "missing"  # fixture has no _stage.json there

    wsio.write_json(workspace / "04-projects" / "projects.json", [])
    status = stages.status(workspace)
    assert status["04-projects"] == "fresh"
    assert status["06-bullets"] == "stale"


def test_status_propagates_staleness_downstream(workspace):
    _commit_chain(workspace)
    evidence = workspace / "02-evidence" / "evidence.jsonl"
    evidence.write_text(evidence.read_text() + "\n")
    status = stages.status(workspace)
    assert status["04-projects"] == "stale"
    assert status["06-bullets"] == "stale"


def test_begin_from_current_copies_committed_output_without_meta(workspace):
    wsio.write_json(workspace / "08-ats" / "_stage.json", {"stage": "08-ats"})
    tmp = stages.begin(workspace, "08-ats", from_current=True)
    assert not (tmp / "_stage.json").exists()
    assert (wsio.read_json(tmp / "general" / "resume.json")
            == wsio.read_json(workspace / "08-ats" / "general" / "resume.json"))
    assert (tmp / "jobs" / "fintech-sre" / "flags.json").is_file()


def test_begin_from_current_lets_one_job_be_replaced(workspace):
    tmp = stages.begin(workspace, "08-ats", from_current=True)
    general = wsio.read_json(tmp / "general" / "resume.json")
    wsio.write_json(tmp / "jobs" / "other" / "resume.json", general)
    assert stages.commit(workspace, "08-ats", ["07-sanitized"]) == []
    assert (workspace / "08-ats" / "jobs" / "fintech-sre" / "resume.json").is_file()
    assert (workspace / "08-ats" / "jobs" / "other" / "resume.json").is_file()


def test_begin_from_current_without_committed_stage_is_empty(workspace):
    assert list(stages.begin(workspace, "out", from_current=True).iterdir()) == []


def test_begin_from_current_discards_leftover_tmp(workspace):
    tmp = stages.begin(workspace, "06-bullets")
    (tmp / "junk.txt").write_text("x")
    tmp = stages.begin(workspace, "06-bullets", from_current=True)
    assert sorted(p.name for p in tmp.iterdir()) == ["bullets.json"]


def test_status_and_begin_recover_from_interrupted_swap(workspace):
    before = wsio.read_json(workspace / "06-bullets" / "bullets.json")
    (workspace / "06-bullets").rename(workspace / "06-bullets.old")
    stages.status(workspace)
    assert wsio.read_json(workspace / "06-bullets" / "bullets.json") == before
    assert not (workspace / "06-bullets.old").exists()

    (workspace / "04-projects").rename(workspace / "04-projects.old")
    stages.begin(workspace, "04-projects")
    assert (workspace / "04-projects" / "projects.json").is_file()
    assert not (workspace / "04-projects.old").exists()


def test_commit_recovers_before_swapping(workspace):
    (workspace / "06-bullets").rename(workspace / "06-bullets.old")
    tmp = stages.tmp_dir(workspace, "06-bullets")
    tmp.mkdir()
    wsio.write_json(tmp / "bullets.json", [{"id": "b_1", "text": ""}])
    assert stages.commit(workspace, "06-bullets", [])  # invalid output
    assert (workspace / "06-bullets" / "bullets.json").is_file()


@pytest.mark.parametrize("rel", ["/etc/passwd", "../outside", "04-projects/../../x", "..",
                                 r"C:\x", r"04-projects\..\..\x"])
def test_commit_rejects_inputs_outside_the_workspace(workspace, rel):
    _write_bullets(workspace, [BULLET])
    assert stages.commit(workspace, "06-bullets", ["04-projects", rel]) == [
        f"input must be workspace-relative: {rel}"
    ]


@pytest.mark.parametrize("rel", ["", ".", "./", "./.", "04-projects/.."])
def test_commit_rejects_the_workspace_root_as_input(workspace, rel):
    _write_bullets(workspace, [BULLET])
    assert stages.commit(workspace, "06-bullets", ["04-projects", rel]) == [
        f"input must be workspace-relative: {rel}"
    ]


def test_commit_rejects_an_input_that_resolves_to_the_workspace_root(workspace):
    (workspace / "root-link").symlink_to(workspace, target_is_directory=True)
    _write_bullets(workspace, [BULLET])
    assert stages.commit(workspace, "06-bullets", ["root-link"]) == [
        "input must be workspace-relative: root-link"
    ]


def test_input_spelling_is_normalized_so_staleness_propagates(workspace):
    for stage, inputs in [("04-projects", ["02-evidence"]), ("06-bullets", ["./04-projects"])]:
        tmp = stages.begin(workspace, stage)
        for f in (workspace / stage).iterdir():
            if f.name != "_stage.json":
                (tmp / f.name).write_bytes(f.read_bytes())
        assert stages.commit(workspace, stage, inputs) == []
    assert list(wsio.read_json(workspace / "06-bullets" / "_stage.json")["inputs"]) == ["04-projects"]
    evidence = workspace / "02-evidence" / "evidence.jsonl"
    evidence.write_text(evidence.read_text() + "\n")
    status = stages.status(workspace)
    assert status["04-projects"] == "stale"
    assert status["06-bullets"] == "stale"
