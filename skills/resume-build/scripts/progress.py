# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Print where a resume-builder run stands: each step's state, and the one command that continues it.

Usage: uv run progress.py --workspace WS

The steps are init, collect (checkpoint 1), import, analyze (checkpoint 2),
scan, wizard (checkpoint 3), write, apply, ats, review (checkpoint 4) and
render. Each stage step is missing, a draft in progress (<stage>.tmp/),
stale (with the inputs that changed, from stage metadata) or fresh; import
is also changed (the resume file changed or config.json names another) or
none (no resume). The last line names the next step and the command, in the
terms of the skill that owns it. Checkpoint 3 has no state: it comes before
write, apply or ats begins again.

Exit codes: 0 printed; 1 an invalid input (named, with what writes it);
2 usage error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rbuild import steps  # noqa: E402
from rbuild.common import BuildError  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    args = parser.parse_args(argv)
    try:
        found = steps.survey(args.workspace)
        lines = steps.lines(args.workspace, found)
    except BuildError as exc:
        for line in exc.lines:
            print(f"error: {line}", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
