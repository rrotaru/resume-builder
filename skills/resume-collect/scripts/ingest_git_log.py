# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Read the engineer's commits from the local repositories into 01-raw.tmp/git.jsonl.

Usage:
  uv run ingest_git_log.py --workspace WS

Reads config.json local_repos and git_authors (configure.py repos and
git-authors). Every branch, remote branch and tag is read, merge commits are
skipped, and a commit is kept only when its author email or name equals one of
git_authors (ignoring case) and its author date is inside the time range. Run
stage.py begin 01-raw first.

Exit codes: 0 done; 1 error (no or invalid config.json, data notice not
accepted, no repos or authors configured, a folder that is not a git work
tree, 01-raw.tmp/ missing); 2 usage error; 3 no commit by the authors in any
repository (the file is still written; the report names the most frequent
authors in each repository).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import config  # noqa: E402
from rcollect import git  # noqa: E402
from rcollect.common import CollectError, load_config, plural, require_raw_tmp, write_pages  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    args = parser.parse_args(argv)
    workspace = args.workspace
    try:
        cfg = load_config(workspace)
        if not cfg["local_repos"]:
            raise CollectError("no local repositories; run configure.py repos PATH ...")
        authors = cfg.get("git_authors") or []
        if not authors:
            raise CollectError("no git author identities; run configure.py git-authors EMAIL ...")
        tmp = require_raw_tmp(workspace)
        pages, notes, counts = [], [], []
        for value in cfg["local_repos"]:
            repo = config.resolve_path(workspace, value)
            commits, repo_notes = git.read_repo(repo, authors, cfg["time_range"])
            pages += [{"items": [commit]} for commit in commits]
            notes += repo_notes
            counts.append((repo, len(commits)))
    except CollectError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    write_pages(tmp / "git.jsonl", pages)
    for repo, count in counts:
        print(f"{repo}: {plural(count, 'commit')}")
    for note in notes:
        print(note)
    print(f"wrote {plural(len(pages), 'commit')} to {tmp.name}/git.jsonl")
    if not pages:
        print("no commits matched: ask the engineer which email or name their commits use; never guess")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
