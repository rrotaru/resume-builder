"""Create a workspace with default config and empty decision files."""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import config, wsio

EMPTY_DECISIONS = {
    "terms.json": [],
    "projects.json": [],
    "metrics.json": [],
    "profile.json": {},
    "attestations.json": [],
}


def _git(cwd: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(cwd), *args],
                             capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


def exclude_from_git(workspace: Path) -> str | None:
    """If the workspace is inside a git repo, add it to .git/info/exclude.

    Returns the excluded pattern, or None when not in a repo or when the
    workspace is the repository root.
    """
    top = _git(workspace, "rev-parse", "--show-toplevel")
    git_path = _git(workspace, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude")
    if top is None or git_path is None:
        return None
    relative = workspace.resolve().relative_to(Path(top).resolve()).as_posix()
    if relative == ".":
        return None
    exclude = Path(git_path)
    pattern = "/" + relative + "/"
    existing = exclude.read_text(encoding="utf-8").splitlines() if exclude.is_file() else []
    if pattern not in existing:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as fh:
            fh.write(pattern + "\n")
    return pattern


def init_workspace(workspace: Path, target_role: str = "") -> list[str]:
    """Create missing workspace files. Never overwrites existing ones.

    Returns human-readable messages describing what was done.
    """
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    messages = []
    cfg = workspace / "config.json"
    if cfg.exists():
        messages.append("config.json exists; left unchanged")
    else:
        wsio.write_json(cfg, config.default_config(target_role))
        messages.append("created config.json")
    for name, empty in EMPTY_DECISIONS.items():
        path = workspace / "decisions" / name
        if not path.exists():
            wsio.write_json(path, empty)
            messages.append(f"created decisions/{name}")
    pattern = exclude_from_git(workspace)
    if pattern:
        messages.append(f"workspace is inside a git repo; added {pattern} to .git/info/exclude")
    return messages
