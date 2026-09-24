# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Stage lifecycle for resume-builder skills.

Usage:
  uv run stage.py --workspace WS begin STAGE
  uv run stage.py --workspace WS commit STAGE --inputs REL [REL ...]
  uv run stage.py --workspace WS status
"""
import argparse
import json
import sys
from pathlib import Path

from rcore import stages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    begin = sub.add_parser("begin", help="create an empty <stage>.tmp/ and print its path")
    begin.add_argument("stage", choices=stages.STAGES)
    commit = sub.add_parser("commit", help="validate <stage>.tmp/ and swap it into place")
    commit.add_argument("stage", choices=stages.STAGES)
    commit.add_argument("--inputs", nargs="*", default=[],
                        help="workspace-relative files or folders this stage read")
    sub.add_parser("status", help="print each stage as missing, fresh or stale")
    args = parser.parse_args()

    if args.command == "begin":
        print(stages.begin(args.workspace, args.stage))
        return 0
    if args.command == "commit":
        errors = stages.commit(args.workspace, args.stage, args.inputs)
        for error in errors:
            print(error)
        if errors:
            print(f"commit of {args.stage} failed; previous output left in place", file=sys.stderr)
            return 1
        print(f"committed {args.stage}")
        return 0
    print(json.dumps(stages.status(args.workspace), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
