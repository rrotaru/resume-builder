# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Validate workspace files against resume-core schemas.

Usage:
  uv run validate.py --workspace WS             # every committed file
  uv run validate.py --workspace WS PATH [...]  # files or folders, relative to WS
"""
import argparse
import sys
from pathlib import Path

from rcore import validation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    if args.paths:
        errors = validation.validate_paths(args.workspace, args.paths)
    else:
        errors = validation.validate_workspace(args.workspace)
    for error in errors:
        print(error)
    if errors:
        print(f"validation failed: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
