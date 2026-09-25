import subprocess

from rcore import validation, workspace, wsio


def test_init_creates_valid_workspace(tmp_path):
    ws = tmp_path / "resume-workspace"
    messages = workspace.init_workspace(ws, "Staff Engineer")
    assert "created config.json" in messages
    assert "created decisions/terms.json" in messages
    assert wsio.read_json(ws / "config.json")["target_role"] == "Staff Engineer"
    assert wsio.read_json(ws / "decisions" / "profile.json") == {}
    assert wsio.read_json(ws / "decisions" / "wizard.json") == {"anchors": [], "skipped": []}
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


WARNING = "warning: workspace is inside a git repository but was not excluded; do not commit it"


def test_workspace_at_repo_root_is_not_excluded(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert workspace.exclude_from_git(tmp_path) is None
    assert WARNING in workspace.init_workspace(tmp_path)


def test_init_warns_when_exclude_cannot_be_written(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.setattr(workspace, "exclude_from_git", lambda ws: None)
    messages = workspace.init_workspace(tmp_path / "ws")
    assert WARNING in messages


def test_excluded_workspace_does_not_warn(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    messages = workspace.init_workspace(tmp_path / "ws")
    assert WARNING not in messages
    assert "workspace is inside a git repo; added /ws/ to .git/info/exclude" in messages


def test_exclude_path_resolves_from_a_subfolder(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    ws = tmp_path / "a" / "b" / "ws"
    workspace.init_workspace(ws)
    assert "/a/b/ws/" in (tmp_path / ".git" / "info" / "exclude").read_text().splitlines()
    assert not (ws / ".git").exists() and not (tmp_path / "a" / ".git").exists()


def test_special_characters_are_escaped(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    ws = tmp_path / "a[1]"
    (tmp_path / "a1").mkdir()
    workspace.init_workspace(ws)
    assert "/a\\[1]/" in (tmp_path / ".git" / "info" / "exclude").read_text().splitlines()
    check = ["git", "-C", str(tmp_path), "check-ignore", "-q"]
    assert subprocess.run([*check, "a[1]/config.json"]).returncode == 0
    assert subprocess.run([*check, "a1/config.json"]).returncode == 1


def test_gitignore_escaping():
    assert workspace.gitignore_escape("a[1]*?!\\b") == "a\\[1]\\*\\?\\!\\\\b"
    assert workspace.gitignore_escape("#notes/x#") == "\\#notes/x#"
