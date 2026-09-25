"""Helpers for the resume-collect tests: raw pages and workspaces ready to collect."""
import json
import os
import subprocess
from pathlib import Path

from rcollect.common import Page
from rcore import wsio

OPEN = {"start": None, "end": None}
RAW_REL = "01-raw/x.jsonl"


def page(*items, query=None, line=1):
    """One raw page holding items, as read_pages returns it."""
    return [Page(line, list(items), query)]


def run(normalize, *items, query=None, username="jrivera", time_range=OPEN):
    """Normalize items given as one page, labelled like a committed raw file."""
    return normalize(page(*items, query=query), RAW_REL, RAW_REL, username, time_range)


def write_lines(path: Path, lines) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join((line if isinstance(line, str) else json.dumps(line)) + "\n" for line in lines),
                    encoding="utf-8")
    return path


def set_config(workspace: Path, **changes) -> dict:
    cfg = wsio.read_json(workspace / "config.json")
    cfg.update(changes)
    wsio.write_json(workspace / "config.json", cfg)
    return cfg


def collecting(workspace: Path) -> Path:
    """Turn the fixture's committed 01-raw into a collection in progress (01-raw.tmp/)."""
    raw = workspace / "01-raw"
    raw.rename(workspace / "01-raw.tmp")
    return workspace / "01-raw.tmp"


def git(repo: Path, *args: str, env: dict | None = None) -> str:
    """Run git in repo, isolated from the user's and the system's git config."""
    full_env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", **(env or {})}
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=full_env,
                         check=True)
    return out.stdout.strip()


def commit(repo: Path, message: str, name: str, email: str, when: str, files: dict | None = None,
           remove: tuple = ()) -> str:
    """Commit files (path -> str or bytes) as the given author at an ISO time; return the hash."""
    for rel in remove:
        git(repo, "rm", "-q", rel)
    for rel, content in (files or {}).items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    git(repo, "add", "-A")
    env = {"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_DATE": when,
           "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email, "GIT_COMMITTER_DATE": when}
    git(repo, "commit", "-q", "--allow-empty", "-m", message, env=env)
    return git(repo, "rev-parse", "HEAD")


def sample_repo(path: Path) -> dict:
    """A repository with two authors, a rename, a binary file, a merge commit and an old commit.

    Returns the hashes by name. The engineer is jordan@example.com, or the name Jordan Rivera.
    """
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "remote", "add", "origin", "git@github.com:acme/pay.git")
    shas = {}
    shas["old"] = commit(path, "Old work", "Jordan Rivera", "jordan@example.com", "2022-06-01T12:00:00Z",
                         {"old.txt": "old\n"})
    shas["first"] = commit(path, "Add ledger\n\nBody for PAY-42.\n", "J. Rivera", "JORDAN@example.com",
                           "2022-12-31T23:00:00-02:00",
                           {"ledger.py": "a\nb\nc\n", "logo.png": b"\x89PNG\x00\x01\x02"})
    shas["other"] = commit(path, "Other work", "M. Chen", "mchen@example.com", "2023-02-01T00:00:00Z",
                           {"other.txt": "x\n"})
    shas["lookalike"] = commit(path, "Lookalike", "Someone", "xjordan@example.com", "2023-02-02T00:00:00Z",
                               {"look.txt": "x\n"})
    shas["rename"] = commit(path, "Rename ledger (#7)", "Jordan Rivera", "jr@personal.test",
                            "2023-03-01T00:00:00Z", {"books.py": "a\nb\nC\n"}, remove=("ledger.py",))
    git(path, "checkout", "-q", "-b", "feature")
    shas["feature"] = commit(path, "Feature work", "Jordan Rivera", "jordan@example.com", "2023-04-01T00:00:00Z",
                             {"feature.txt": "f\n"})
    git(path, "checkout", "-q", "main")
    env = {"GIT_AUTHOR_NAME": "Jordan Rivera", "GIT_AUTHOR_EMAIL": "jordan@example.com",
           "GIT_AUTHOR_DATE": "2023-04-02T00:00:00Z", "GIT_COMMITTER_NAME": "Jordan Rivera",
           "GIT_COMMITTER_EMAIL": "jordan@example.com", "GIT_COMMITTER_DATE": "2023-04-02T00:00:00Z"}
    git(path, "merge", "-q", "--no-ff", "-m", "Merge feature", "feature", env=env)
    shas["merge"] = git(path, "rev-parse", "HEAD")
    return shas
