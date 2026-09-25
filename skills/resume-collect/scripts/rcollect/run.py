"""Running the normalizers on a raw folder, checking it against config.json, and reporting."""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from . import git, github, gitlab, jira, reviews
from .common import (MAX_REPORTED, RAW, CollectError, Result, load_config, plural, raw_folder,
                     read_pages, source_entry)

SOURCES = ("github", "gitlab", "jira")
ACTIVE = ("connector", "export")
# raw file -> evidence source, in the order link.py normalizes them
FILES = {"github.jsonl": "github", "gitlab.jsonl": "gitlab", "jira.jsonl": "jira",
         "git.jsonl": "git", "reviews.jsonl": "review"}
_NORMALIZERS = {"github": github.normalize, "gitlab": gitlab.normalize, "jira": jira.normalize}


def normalize_file(workspace: Path, cfg: dict, name: str, label: str) -> Result:
    """Normalize one raw file. label is its workspace-relative path; raw_ref always names 01-raw/."""
    source = FILES[name]
    pages = read_pages(Path(workspace) / label)
    rel = f"{RAW}/{name}"
    if source in _NORMALIZERS:
        username = source_entry(cfg, source)["username"]
        return _NORMALIZERS[source](pages, rel, label, username, cfg["time_range"])
    if source == "git":
        return git.normalize(pages, rel, label, cfg["time_range"])
    return reviews.normalize(pages, rel, label)


def check_raw(workspace: Path, cfg: dict, folder: str) -> tuple[list[str], list[str], list[str]]:
    """(errors, warnings, raw file names to normalize) for a raw folder against config.json."""
    root = Path(workspace) / folder
    present = sorted(p.name for p in root.iterdir() if p.is_file() and p.name != "_stage.json")
    errors, warnings = [], []
    for name in present:
        if name.endswith(".partial.jsonl"):
            source = name[: -len(".partial.jsonl")]
            errors.append(f"{folder}/{name}: an unfinished fetch; retry it from its cursor and rename it to "
                          f"{source}.jsonl, or delete it and run configure.py source {source} --mode skip")
        elif name not in FILES:
            warnings.append(f"{folder}/{name}: not a raw source file; ignored")
    for source in SOURCES:
        entry = source_entry(cfg, source)
        mode = entry.get("mode") if entry else None
        name = f"{source}.jsonl"
        if mode in ACTIVE and name not in present:
            how = f"run ingest_export.py --source {source}" if mode == "export" else "fetch it with the connector"
            errors.append(f"{source} is configured ({mode}) but {folder}/{name} is missing; {how}, "
                          f"or run configure.py source {source} --mode skip")
        if mode in ACTIVE and not entry.get("username"):
            errors.append(f"{source} has no username; run configure.py source {source} --mode {mode} "
                          "--username NAME")
        if name in present and mode not in ACTIVE:
            state = "set to skip" if entry else "not configured"
            errors.append(f"{folder}/{name} exists but {source} is {state}; delete the file, or run "
                          f"configure.py source {source} --mode connector|export --username NAME")
    for name, setting, script, command in (("git.jsonl", "local_repos", "ingest_git_log.py", "repos"),
                                           ("reviews.jsonl", "reviews_dir", "ingest_reviews.py", "reviews")):
        configured = bool(cfg.get(setting))
        if configured and name not in present:
            errors.append(f"{setting} is set but {folder}/{name} is missing; run {script}")
        if name in present and not configured:
            errors.append(f"{folder}/{name} exists but {setting} is not set; delete the file, "
                          f"or run configure.py {command}")
    return errors, warnings, [name for name in FILES if name in present]


def _counts(counter: Counter) -> str:
    return ", ".join(f"{key} {n}" for key, n in sorted(counter.items()))


def report(result: Result, username: str | None = None) -> list[str]:
    """Lines describing one normalizer's result."""
    kinds = Counter(d.kind for d in result.drafts)
    lines = [f"{result.source}: {plural(result.items, 'item')} read from {result.label}, {len(result.drafts)} kept"
             + (f" ({_counts(kinds)})" if kinds else "")]
    filtered = []
    if result.not_mine:
        owner = f"{username}'s" if username else "the engineer's"
        filtered.append(f"{result.not_mine} not {owner}")
    if result.out_of_range:
        filtered.append(f"{result.out_of_range} outside the time range")
    if filtered:
        lines.append("  filtered: " + ", ".join(filtered))
    if result.bad:
        lines.append(f"  bad rows: {len(result.bad)}" + (f" (first {MAX_REPORTED} shown)"
                                                        if len(result.bad) > MAX_REPORTED else ""))
        lines += [f"  {line}" for line in result.bad[:MAX_REPORTED]]
    return lines


def nothing_found(result: Result, username: str) -> list[str]:
    """Lines explaining an empty result, for exit 3."""
    if result.not_mine:
        lines = [f"{result.source}: none of the items in {result.label} belongs to {username!r}"]
    elif result.out_of_range:
        lines = [f"{result.source}: every item for {username!r} in {result.label} is outside the time range"]
    else:
        lines = [f"{result.source}: no items in {result.label}"]
    if result.queries:
        lines.append("  queries used:")
        lines += [f"    {query}" for query in result.queries]
    if result.others:
        lines.append("  most frequent authors seen: "
                     + ", ".join(f"{who} ({n})" for who, n in result.others.most_common(5)))
    lines.append("  ask the engineer for another username or email, or check the time range; never guess")
    return lines


def normalize_main(source: str, doc: str, argv=None) -> int:
    """The normalize_<source>.py command line: report on one raw file, write nothing."""
    parser = argparse.ArgumentParser(description=doc.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("--raw", help="workspace-relative raw file (default: 01-raw.tmp/ while collecting, "
                                      "else 01-raw/)")
    args = parser.parse_args(argv)
    workspace = args.workspace
    try:
        cfg = load_config(workspace)
        entry = source_entry(cfg, source)
        if not entry or entry.get("mode") not in ACTIVE or not entry.get("username"):
            raise CollectError(f"{source} is not configured with a username; run configure.py source {source} "
                               "--mode connector|export --username NAME")
        label = args.raw or f"{raw_folder(workspace)}/{source}.jsonl"
        if not (workspace / label).is_file():
            raise CollectError(f"{label}: not found")
        result = normalize_file(workspace, cfg, f"{source}.jsonl", label)
    except CollectError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for line in report(result, entry["username"]):
        print(line)
    if not result.drafts:
        for line in nothing_found(result, entry["username"]):
            print(line)
        return 3
    return 0
