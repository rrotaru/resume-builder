# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Fail if any bullet has no sources or cites a source that does not exist.

Usage: uv run check_sources.py --workspace WS FILE [FILE ...]
FILE is a bullets file (JSON array) or a tailored resume.json, relative to WS.
"""
import argparse
import sys
from pathlib import Path

from rcore import sources


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    known = sources.load_known(args.workspace)
    errors = [e for rel in args.files for e in sources.check_file(args.workspace, rel, known)]
    for error in errors:
        print(error)
    if errors:
        print(f"source check failed: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("source check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
