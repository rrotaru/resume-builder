# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Fail if any denylisted term from decisions/terms.json appears in the given files.

Usage: uv run check_terms.py --workspace WS FILE [FILE ...]
FILE is .json, .jsonl or text (for example .md), relative to WS.
"""
import argparse
import sys
from pathlib import Path

from rcore import terms


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    patterns = terms.compile_terms(terms.load_denylist(args.workspace))
    errors = [e for rel in args.files for e in terms.check_file(args.workspace, rel, patterns)]
    for error in errors:
        print(error)
    if errors:
        print(f"terms check failed: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("terms check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
