# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""List the wizard's open questions (checkpoint 3), in the order to ask them.

Usage:
  uv run questions.py --workspace WS [--all]

Reads 03-profile/ (profile.json, source.json), 04-projects/projects.json,
05-terms/candidates.json, 07-sanitized/new-terms.json and decisions/ (profile,
terms, metrics, projects, wizard). Lists, in order: answers a re-import moved
(moved:), metrics whose project is gone (metric-gone:), undecided terms (term:),
fact fields holding a denied term (fact:), missing profile fields (profile:)
and top projects without a metric (metric:). Each question names the
answer.py commands that resolve it. Skipped questions are left out unless
--all is given. Writes nothing.

Exit codes: 0 listed (possibly none); 1 an invalid file (named); 2 usage error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rwizard import questions  # noqa: E402
from rwizard.common import WizardError, plural  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("--all", action="store_true", help="also list the questions skipped earlier")
    args = parser.parse_args(argv)
    try:
        found, notes = questions.compute(questions.context(args.workspace))
    except WizardError as exc:
        for line in exc.lines:
            print(f"error: {line}", file=sys.stderr)
        return 1
    for line in notes:
        print(line)
    skipped = sum(1 for q in found if q.skipped)
    for question in found:
        if question.skipped and not args.all:
            continue
        print(f"{question.key}  {question.text}" + ("  (skipped)" if question.skipped else ""))
        for line in question.details:
            print(f"    {line}")
        print(f"  answer: {question.answer}")
    count = len(found) - skipped
    summary = f"wizard: {plural(count, 'open question')}" if count else "wizard: no open questions"
    if skipped:
        summary += f", {skipped} skipped" + ("" if args.all else " (questions.py --all lists them)")
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
