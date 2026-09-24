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
