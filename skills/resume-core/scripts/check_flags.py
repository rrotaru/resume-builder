# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Fail if a job version has unattested flagged rewrites or bullets changed after the claim diff.

Usage: uv run check_flags.py --workspace WS JOB_SLUG [JOB_SLUG ...]
"""
import argparse
import sys
from pathlib import Path

from rcore import flags


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("jobs", nargs="+")
    args = parser.parse_args()
    errors = [e for job in args.jobs for e in flags.check_job(args.workspace, job)]
    for error in errors:
        print(error)
    if errors:
        print(f"flags check failed: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("flags check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
