# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Check the raw Jira data: which tickets and epics become evidence. Writes nothing.

Usage:
  uv run normalize_jira.py --workspace WS [--raw REL]

Reads 01-raw.tmp/jira.jsonl while a collection is in progress, else
01-raw/jira.jsonl (--raw names another workspace-relative file). Prints what
link.py would keep: items per kind, filtered items, and bad rows with their
lines. link.py runs the same normalizer when it builds 02-evidence.

Exit codes: 0 evidence found; 1 error (no or invalid config.json, data notice
not accepted, jira not configured, file missing); 2 usage error; 3 no item
belongs to the configured username (the queries used are shown).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcollect import run  # noqa: E402


def main(argv=None) -> int:
    return run.normalize_main("jira", __doc__, argv)


if __name__ == "__main__":
    sys.exit(main())
