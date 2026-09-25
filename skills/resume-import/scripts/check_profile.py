# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Check that the imported profile says only what the resume says, and commit 03-profile.

Usage:
  uv run check_profile.py --workspace WS             # check 03-profile.tmp/
  uv run check_profile.py --workspace WS --commit    # check it, then commit 03-profile
  uv run check_profile.py --workspace WS --committed # check the committed 03-profile/

With --commit it also warns about wizard answers (decisions/profile.json) that
this import attaches to a different entry. Warnings never block the commit.

Exit codes: 0 passed (and committed with --commit); 1 the check or the commit
failed, and nothing was committed; 2 usage error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import stages, wsio  # noqa: E402
from rimport import check, shifts  # noqa: E402

STAGE = "03-profile"


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--commit", action="store_true", help="commit 03-profile if the check passes")
    mode.add_argument("--committed", action="store_true", help="check the committed 03-profile/ instead")
    return parser.parse_args(argv)


def _object(workspace: Path, rel: str) -> dict:
    data, _ = wsio.load(workspace, rel)
    return data if isinstance(data, dict) else {}


def main(argv=None) -> int:
    args = _parse(argv)
    workspace = args.workspace
    stage_dir = STAGE if args.committed else f"{STAGE}.tmp"
    problems, mapping = check.check_stage(workspace, stage_dir)
    for line in problems:
        print(line)
    if problems:
        if mapping:
            print(f"  {check.FIX}")
        print(f"profile check failed: {len(problems)} problem(s)", file=sys.stderr)
        return 1
    if not args.commit:
        print("profile check passed")
        return 0

    new = wsio.read_json(workspace / stage_dir / "profile.json")
    old = _object(workspace, f"{STAGE}/profile.json")
    wizard = _object(workspace, "decisions/profile.json")
    for warning in shifts.warnings(old, new, wizard):
        print(f"warning: {warning}")
    errors = stages.commit(workspace, STAGE, [])
    for line in errors:
        print(line)
    if errors:
        print(f"commit of {STAGE} failed; previous output left in place", file=sys.stderr)
        return 1
    print(f"committed {STAGE}: {check.describe_sections(new)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
