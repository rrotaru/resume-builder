# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Lint the draft versions in 08-ats.tmp/: bullet shape and characters, duplicates, dates, contact details and length.

Usage: uv run ats_lint.py --workspace WS [VERSION ...]

VERSION is general or a job slug; without one, every version in the draft.
Errors stop ats.py --commit; warnings go to the version's report.json. The
length rule: under 96 months of experience (the union of the profile's job
dates) one page, else two, at 50 estimated lines a page.

Exit codes: 0 no lint errors; 1 a lint error, or no draft or version; 2 usage error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rats import check, lint, material, report  # noqa: E402
from rats.common import RESUME, AtsError, load_inputs  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("versions", nargs="*", metavar="VERSION")
    args = parser.parse_args(argv)
    try:
        versions = check.chosen(args.workspace, args.versions)
        found = material.build(args.workspace, load_inputs(args.workspace))
    except AtsError as exc:
        for line in exc.lines:
            print(f"error: {line}", file=sys.stderr)
        return 1
    failed = False
    for target in versions:
        resume, problems = check.resume(args.workspace, target)
        if resume is None:
            failed = True
            for line in problems:
                print(f"error: {line}")
            continue
        errors, warnings, length = lint.lint(resume, found)
        print(f"{target.name}: estimated {length['estimated_lines']} of {length['line_budget']} lines; "
              f"{report.length_line(length)}")
        for line in errors:
            print(f"error: {target.draft(RESUME)}: {line}")
        for line in warnings:
            print(f"warning: {line}")
        failed = failed or bool(errors)
    print("lint failed" if failed else "lint passed", file=sys.stderr if failed else sys.stdout)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
