# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Record the engineer's collection choices in config.json (checkpoint 1).

Usage:
  uv run configure.py --workspace WS show
  uv run configure.py --workspace WS notice [--accept]
  uv run configure.py --workspace WS time-range --start YYYY-MM-DD|none --end YYYY-MM-DD|none
  uv run configure.py --workspace WS source github|gitlab|jira --mode connector|export|skip
                      [--username NAME] [--export PATH]
  uv run configure.py --workspace WS repos [PATH ...]
  uv run configure.py --workspace WS git-authors [EMAIL_OR_NAME ...]
  uv run configure.py --workspace WS reviews PATH|none
  uv run configure.py --workspace WS resume PATH|none

Paths given here resolve against the current directory and are stored as
absolute paths. The whole file is validated before it is written, and a
rejected change leaves it as it was.

Exit codes: 0 done; 1 error (no or invalid config.json, a bad value); 2 usage error.
"""
from __future__ import annotations

import argparse
import copy
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import config as rconfig  # noqa: E402
from rcore import schema, wsio  # noqa: E402
from rcollect import git  # noqa: E402
from rcollect.common import NOTICE, CollectError, load_config  # noqa: E402

SOURCES = ("github", "gitlab", "jira")


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("show", help="print the collection settings")
    notice = sub.add_parser("notice", help="print the data notice; --accept records that the engineer agreed")
    notice.add_argument("--accept", action="store_true")
    span = sub.add_parser("time-range", help="set the time range (none leaves an end open)")
    span.add_argument("--start", required=True)
    span.add_argument("--end", required=True)
    source = sub.add_parser("source", help="add or replace a GitHub, GitLab or Jira source")
    source.add_argument("type", choices=SOURCES)
    source.add_argument("--mode", required=True, choices=("connector", "export", "skip"))
    source.add_argument("--username")
    source.add_argument("--export", type=Path, help="export file (mode export)")
    repos = sub.add_parser("repos", help="set the local git repositories (none clears them)")
    repos.add_argument("paths", nargs="*", type=Path)
    authors = sub.add_parser("git-authors", help="set the engineer's commit emails or names")
    authors.add_argument("identities", nargs="*")
    reviews = sub.add_parser("reviews", help="set the performance review folder, or none")
    reviews.add_argument("path")
    resume = sub.add_parser("resume", help="set the existing resume file, or none")
    resume.add_argument("path")
    return parser.parse_args(argv)


def _date(value: str, name: str) -> str | None:
    if value.lower() == "none":
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value).isoformat()
    except ValueError:
        pass
    raise CollectError(f"--{name} {value!r} is not a real YYYY-MM-DD date (or none)")


def _absolute(path: Path) -> Path:
    return Path(path).expanduser().resolve()


def _save(workspace: Path, cfg: dict) -> None:
    errors = schema.validate(cfg, schema.load_schema("config"))
    if errors:
        raise CollectError("config.json would not be valid: " + "; ".join(errors))
    target = workspace / "config.json"
    tmp = target.with_name("config.json.tmp")
    wsio.write_json(tmp, cfg)
    os.replace(tmp, target)


def _show(workspace: Path, cfg: dict) -> None:
    def where(value):
        return f"{value} -> {rconfig.resolve_path(workspace, value)}" if value and not Path(
            value).expanduser().is_absolute() else value or "none"

    span = cfg["time_range"]
    print(f"time range: {span['start'] or 'open'} to {span['end'] or 'open'}")
    by_type = {s["type"]: s for s in cfg["sources"]}
    for source in SOURCES:
        entry = by_type.get(source)
        if not entry:
            print(f"{source}: not configured")
            continue
        detail = f"{entry['mode']}, username {entry.get('username') or 'none'}"
        if entry["mode"] == "export":
            detail += f", export {where(entry.get('export_path'))}"
        print(f"{source}: {detail}")
    print("local repos: " + (", ".join(where(r) for r in cfg["local_repos"]) or "none"))
    print("git authors: " + (", ".join(cfg.get("git_authors", [])) or "none"))
    print(f"reviews folder: {where(cfg['reviews_dir'])}")
    print(f"resume: {where(cfg['resume_path'])}")
    accepted = cfg["data_notice_acknowledged_at"]
    print(f"data notice: {'accepted at ' + accepted if accepted else 'not accepted'}")


def _apply(args, workspace: Path, cfg: dict) -> str:
    """Change cfg in place for the command and return what to print."""
    if args.command == "notice":
        if cfg["data_notice_acknowledged_at"]:
            return f"data notice already accepted at {cfg['data_notice_acknowledged_at']}"
        if not args.accept:
            return NOTICE + "\n\nnot accepted yet: run notice --accept only after the engineer agrees"
        cfg["data_notice_acknowledged_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return f"data notice accepted at {cfg['data_notice_acknowledged_at']}"
    if args.command == "time-range":
        start, end = _date(args.start, "start"), _date(args.end, "end")
        if start and end and start > end:
            raise CollectError(f"--start {start} is after --end {end}")
        cfg["time_range"] = {"start": start, "end": end}
        return f"time range set to {start or 'open'} to {end or 'open'}"
    if args.command == "source":
        entry = {"type": args.type, "mode": args.mode, "username": args.username, "export_path": None}
        if args.mode in ("connector", "export") and not (args.username and args.username.strip()):
            raise CollectError(f"--mode {args.mode} needs --username: the engineer's {args.type} username")
        if args.mode == "export":
            if args.export is None:
                raise CollectError("--mode export needs --export PATH")
            path = _absolute(args.export)
            if not path.is_file():
                raise CollectError(f"{path}: not found")
            entry["export_path"] = str(path)
        elif args.export is not None:
            raise CollectError("--export applies to --mode export only")
        others = [s for s in cfg["sources"] if s["type"] != args.type]
        index = next((i for i, s in enumerate(cfg["sources"]) if s["type"] == args.type), len(others))
        cfg["sources"] = others[:index] + [entry] + others[index:]
        return f"{args.type} set to {args.mode}" + (f" as {args.username}" if args.username else "")
    if args.command == "repos":
        paths = []
        for path in map(_absolute, args.paths):
            if not path.is_dir() or not git.is_work_tree(path):
                raise CollectError(f"{path}: not a git work tree")
            if str(path) not in paths:
                paths.append(str(path))
        cfg["local_repos"] = paths
        return "local repos set to " + (", ".join(paths) or "none")
    if args.command == "git-authors":
        identities = []
        for identity in (i.strip() for i in args.identities):
            if not identity:
                raise CollectError("an empty git author identity")
            if identity not in identities:
                identities.append(identity)
        cfg["git_authors"] = identities
        return "git authors set to " + (", ".join(identities) or "none")
    key, kind = ("reviews_dir", "folder") if args.command == "reviews" else ("resume_path", "file")
    if args.path.lower() == "none":
        cfg[key] = None
        return f"{key} cleared"
    path = _absolute(Path(args.path))
    if not (path.is_dir() if kind == "folder" else path.is_file()):
        raise CollectError(f"{path}: not an existing {kind}")
    cfg[key] = str(path)
    return f"{key} set to {path}"


def main(argv=None) -> int:
    args = _parse(argv)
    workspace = args.workspace
    try:
        cfg = load_config(workspace, need_notice=False)
        if args.command == "show":
            _show(workspace, cfg)
            return 0
        updated = copy.deepcopy(cfg)
        message = _apply(args, workspace, updated)
        if updated != cfg:
            _save(workspace, updated)
    except CollectError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
