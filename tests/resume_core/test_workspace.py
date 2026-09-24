import subprocess

from rcore import validation, workspace, wsio


def test_init_creates_valid_workspace(tmp_path):
    ws = tmp_path / "resume-workspace"
    messages = workspace.init_workspace(ws, "Staff Engineer")
    assert "created config.json" in messages
    assert "created decisions/terms.json" in messages
    assert wsio.read_json(ws / "config.json")["target_role"] == "Staff Engineer"
    assert wsio.read_json(ws / "decisions" / "profile.json") == {}
    assert validation.validate_workspace(ws) == []


def test_init_never_overwrites(tmp_path):
    ws = tmp_path / "ws"
    workspace.init_workspace(ws, "A")
    wsio.write_json(ws / "decisions" / "terms.json", [{"term": "Falcon", "replacement": "x", "kind": "codename"}])
    messages = workspace.init_workspace(ws, "B")
    assert messages == ["config.json exists; left unchanged"]
    assert wsio.read_json(ws / "config.json")["target_role"] == "A"
    assert wsio.read_json(ws / "decisions" / "terms.json")[0]["term"] == "Falcon"


def test_init_inside_git_repo_adds_exclude_once(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    ws = tmp_path / "sub" / "resume-workspace"
    workspace.init_workspace(ws)
    workspace.init_workspace(ws)
    exclude = (tmp_path / ".git" / "info" / "exclude").read_text().splitlines()
    assert exclude.count("/sub/resume-workspace/") == 1


def test_init_outside_git_repo(tmp_path):
    messages = workspace.init_workspace(tmp_path / "ws")
    assert not any("git" in m for m in messages)


def test_workspace_at_repo_root_is_not_excluded(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert workspace.exclude_from_git(tmp_path) is None
