# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Report the keyword coverage of the draft versions in 08-ats.tmp/: covered, missing with evidence, missing without.

Usage: uv run keywords.py --workspace WS [VERSION ...]

VERSION is general or a job slug; without one, every version in the draft.
Each version's keywords.json lists its keywords: the target role's for the
general resume, the posting's for a job (each must be in its jd.txt). A
keyword is covered when the resume's visible text holds it, missing with
evidence when a sanitized bullet, the evidence of a project, a performance
review, a metric or the profile holds it, and missing without evidence
otherwise. A keyword enters the skills only through the wizard
(answer.py add /skills/<i>/keywords KEYWORD).

Exit codes: 0 coverage printed; 1 keywords.json missing or invalid, or no draft or version; 2 usage error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rats import check, coverage, material, report  # noqa: E402
from rats.common import KEYWORDS, AtsError, load_inputs  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("versions", nargs="*", metavar="VERSION")
    args = parser.parse_args(argv)
    try:
        versions = check.chosen(args.workspace, args.versions)
        inputs = load_inputs(args.workspace)
        found = material.build(args.workspace, inputs)
    except AtsError as exc:
        for line in exc.lines:
            print(f"error: {line}", file=sys.stderr)
        return 1
    failed = False
    for target in versions:
        if not (args.workspace / target.draft(KEYWORDS)).is_file():
            failed = True
            print(f"error: {target.draft(KEYWORDS)}: not found; write the "
                  f"{'posting' if target.is_job else 'target role'}'s keywords first (see SKILL.md)")
            continue
        keywords, problems = check.keywords(args.workspace, target, inputs.target_role)
        resume, resume_problems = check.resume(args.workspace, target)
        for line in problems + resume_problems:
            print(f"error: {line}")
        if problems or resume is None:
            failed = True
            continue
        for line in report.keyword_lines(target.name, coverage.cover(resume, keywords, found)):
            print(line)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
