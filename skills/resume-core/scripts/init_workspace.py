# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Create a resume-builder workspace (never overwrites existing files).

Usage: uv run init_workspace.py --workspace WS [--target-role "Senior Backend Engineer"]
"""
import argparse
import sys
from pathlib import Path

from rcore import workspace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("--target-role", default="")
    args = parser.parse_args()
    for message in workspace.init_workspace(args.workspace, args.target_role):
        print(message)
    print(f"workspace ready: {args.workspace.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
