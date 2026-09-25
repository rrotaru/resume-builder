# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Build 02-evidence/evidence.jsonl from the raw data and commit 01-raw and 02-evidence.

Usage:
  uv run link.py --workspace WS

Reads 01-raw.tmp/ while a collection is in progress (and commits it as
01-raw), else the committed 01-raw/. Checks the raw files against config.json,
normalizes every source, merges duplicates, drops commits that an authored
pull request already covers, assigns evidence IDs over all items at once,
links each item to the items it references, and commits 02-evidence with the
counts in _stage.json extra.

Exit codes: 0 committed; 1 error (no or invalid config.json, data notice not
accepted, no raw data, raw files that do not match config.json, an unfinished
fetch, a failed commit); nothing is committed on error; 2 usage error.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import schema, stages, wsio  # noqa: E402
from rcollect import merge, run  # noqa: E402
from rcollect.common import RAW, RAW_TMP, CollectError, load_config, plural, raw_folder, source_entry  # noqa: E402

STAGE = "02-evidence"


def _fail(lines: list[str]) -> int:
    for line in lines:
        print(f"error: {line}", file=sys.stderr)
    print(f"{STAGE} not committed", file=sys.stderr)
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    args = parser.parse_args(argv)
    workspace = args.workspace
    try:
        cfg = load_config(workspace)
    except CollectError as exc:
        return _fail([str(exc)])
    folder = raw_folder(workspace)
    if not (workspace / folder).is_dir():
        return _fail([f"no raw data in {RAW}/ or {RAW_TMP}/; run stage.py begin 01-raw and collect first"])
    errors, warnings, files = run.check_raw(workspace, cfg, folder)
    for line in warnings:
        print(f"warning: {line}")
    if errors:
        return _fail(errors)

    results = []
    try:
        for name in files:
            results.append(run.normalize_file(workspace, cfg, name, f"{folder}/{name}"))
    except CollectError as exc:
        return _fail([str(exc)])
    records, duplicates = merge.build([d for r in results for d in r.drafts])
    spec = schema.load_schema("evidence")
    invalid = [f"{r['raw_ref']}: {e}" for r in records for e in schema.validate(r, spec)]
    if invalid:
        return _fail(invalid)

    for result in results:
        entry = source_entry(cfg, result.source)
        for line in run.report(result, entry.get("username") if entry else None):
            print(line)
    if folder == RAW_TMP:
        problems = stages.commit(workspace, RAW, [])
        if problems:
            return _fail(problems)
        print(f"committed {RAW}")
    tmp = stages.begin(workspace, STAGE)
    wsio.write_jsonl(tmp / "evidence.jsonl", records)
    per_source = Counter(r["source"] for r in records)
    extra = {
        "items": dict(sorted(per_source.items())),
        "skipped_rows": sum(len(r.bad) for r in results),
        "filtered": sum(r.not_mine + r.out_of_range for r in results),
        "duplicates": duplicates,
    }
    problems = stages.commit(workspace, STAGE, [RAW], extra=extra)
    if problems:
        return _fail(problems)
    links = sum(len(r["links"]) for r in records)
    summary = ", ".join(f"{source} {n}" for source, n in sorted(per_source.items())) or "none"
    print(f"removed {plural(duplicates, 'duplicate')}; {plural(links, 'link')}")
    print(f"committed {STAGE}: {plural(len(records), 'item')} ({summary})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
