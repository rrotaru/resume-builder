# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Load a source's export file into 01-raw.tmp/<source>.jsonl.

Usage:
  uv run ingest_export.py --workspace WS --source github|gitlab|jira

The file is the source's export_path in config.json (configure.py source S
--mode export --export PATH). Accepted: .json (an array of items, a page
object with "items" or "issues", or an array of pages), .jsonl or .ndjson
(one item or page per line), and .csv for Jira. Each item becomes one raw
line carrying the export path and its row. Run stage.py begin 01-raw first.

Exit codes: 0 done; 1 error (no or invalid config.json, data notice not
accepted, the source is not an export, 01-raw.tmp/ missing, a file that
cannot be read or parsed); 2 usage error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import config  # noqa: E402
from rcollect import exports  # noqa: E402
from rcollect.common import (CollectError, load_config, plural, require_raw_tmp, source_entry,  # noqa: E402
                             write_pages)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("--source", required=True, choices=("github", "gitlab", "jira"))
    args = parser.parse_args(argv)
    workspace = args.workspace
    try:
        cfg = load_config(workspace)
        entry = source_entry(cfg, args.source)
        if not entry or entry.get("mode") != "export" or not entry.get("export_path"):
            raise CollectError(f"{args.source} is not an export source; run configure.py source {args.source} "
                               "--mode export --username NAME --export PATH")
        path = config.resolve_path(workspace, entry["export_path"])
        if not path.is_file():
            raise CollectError(f"{path}: not found")
        tmp = require_raw_tmp(workspace)
        pages = exports.load(path, args.source)
    except CollectError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    target = tmp / f"{args.source}.jsonl"
    write_pages(target, pages)
    errors = sum(1 for page in pages if "error" in page)
    print(f"loaded {plural(len(pages) - errors, 'item')} from {path} into {tmp.name}/{target.name}"
          + (f"; {plural(errors, 'line')} not valid JSON, reported as bad rows" if errors else ""))
    print(f"next: run normalize_{args.source}.py to check them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
