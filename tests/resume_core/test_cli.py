"""Each CLI runs as a standalone script (the way skills call it) and sets its exit code."""
import json
import subprocess
import sys

from conftest import CORE_SCRIPTS


def run(script, *args):
    return subprocess.run([sys.executable, str(CORE_SCRIPTS / script), *map(str, args)],
                          capture_output=True, text=True)


def test_validate_cli(workspace):
    ok = run("validate.py", "--workspace", workspace)
    assert ok.returncode == 0 and "validation passed" in ok.stdout
    (workspace / "config.json").write_text("{}")
    bad = run("validate.py", "--workspace", workspace, "config.json")
    assert bad.returncode == 1 and "missing required property" in bad.stdout


def test_check_sources_cli(workspace):
    ok = run("check_sources.py", "--workspace", workspace, "08-ats/general/resume.json")
    assert ok.returncode == 0
    bad = run("check_sources.py", "--workspace", workspace, "03-profile/profile.json")
    assert bad.returncode == 1


def test_check_terms_cli(workspace):
    assert run("check_terms.py", "--workspace", workspace, "08-ats/general/resume.json").returncode == 0
    bad = run("check_terms.py", "--workspace", workspace, "06-bullets/bullets.json")
    assert bad.returncode == 1 and "Project Falcon" in bad.stdout


def test_check_flags_cli(workspace):
    assert run("check_flags.py", "--workspace", workspace, "fintech-sre").returncode == 0
    assert run("check_flags.py", "--workspace", workspace, "missing-job").returncode == 1


def test_stage_cli_round_trip(workspace):
    tmp = run("stage.py", "--workspace", workspace, "begin", "05-terms").stdout.strip()
    (workspace / "05-terms.tmp" / "candidates.json").write_text("[]")
    assert tmp.endswith("05-terms.tmp")
    committed = run("stage.py", "--workspace", workspace, "commit", "05-terms", "--inputs", "04-projects")
    assert committed.returncode == 0, committed.stdout
    status = json.loads(run("stage.py", "--workspace", workspace, "status").stdout)
    assert status["05-terms"] == "fresh"


def test_init_workspace_cli(tmp_path):
    result = run("init_workspace.py", "--workspace", tmp_path / "ws", "--target-role", "SRE")
    assert result.returncode == 0 and "workspace ready" in result.stdout


def test_check_terms_cli_fails_closed_without_terms_file(workspace):
    (workspace / "decisions" / "terms.json").unlink()
    result = run("check_terms.py", "--workspace", workspace, "07-sanitized/bullets.json")
    assert result.returncode == 1
    assert result.stdout.splitlines() == ["decisions/terms.json: not found; run init_workspace.py"]


def test_check_sources_cli_reports_missing_file(workspace):
    result = run("check_sources.py", "--workspace", workspace, "06-bullets/nope.json")
    assert result.returncode == 1
    assert result.stdout.splitlines() == ["06-bullets/nope.json: not found"]


def test_stage_cli_from_current_and_extra(workspace):
    tmp = run("stage.py", "--workspace", workspace, "begin", "08-ats", "--from-current").stdout.strip()
    assert tmp.endswith("08-ats.tmp")
    assert (workspace / "08-ats.tmp" / "jobs" / "fintech-sre" / "resume.json").is_file()
    committed = run("stage.py", "--workspace", workspace, "commit", "08-ats",
                    "--inputs", "07-sanitized", "--extra", '{"skipped_rows": 3}')
    assert committed.returncode == 0, committed.stdout
    meta = json.loads((workspace / "08-ats" / "_stage.json").read_text())
    assert meta["extra"] == {"skipped_rows": 3}


def test_stage_cli_rejects_bad_extra(workspace):
    run("stage.py", "--workspace", workspace, "begin", "05-terms")
    (workspace / "05-terms.tmp" / "candidates.json").write_text("[]")
    for bad in ["{not json", "[1, 2]"]:
        result = run("stage.py", "--workspace", workspace, "commit", "05-terms", "--extra", bad)
        assert result.returncode == 2 and "--extra" in result.stderr
    assert (workspace / "05-terms.tmp").is_dir()
