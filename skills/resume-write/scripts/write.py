# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Print what to write bullets and stories about, then check the model's bullets and stories and commit 06-bullets.

Usage:
  uv run write.py --workspace WS                  # begin 06-bullets and print the material
  uv run write.py --workspace WS --from-current   # the same, starting from the committed bullets and stories
  uv run write.py --workspace WS --commit         # check 06-bullets.tmp/ and commit 06-bullets

Reads 04-projects/projects.json (never groups.json), 02-evidence/evidence.jsonl,
each performance review's full text in 01-raw/, 03-profile/profile.json,
decisions/profile.json and decisions/metrics.json. Without --commit it begins
06-bullets.tmp/ (fresh, or with --from-current a copy of the committed stage)
and prints the jobs and projects of the profile with their resume text, each
project with its job, metrics and evidence, and the performance reviews. The
model then writes 06-bullets.tmp/bullets.json and 06-bullets.tmp/stories.md.
With --commit the script checks both: each bullet cites its own project's
evidence, performance reviews, its project's metrics and the profile; states
the value of each metric it cites (form xyz_quantified exactly then); writes
only numbers its sources state; names its place (work_ref, or a profile
project); and together the bullets cover every project, metric and resume
highlight. stories.md holds one STAR story per project with a metric prompt.
Then it assigns bullet IDs (a bullet whose text is unchanged keeps its ID)
and commits 06-bullets.

Exit codes: 0 begun, or committed with --commit; 1 error (projects or
evidence missing, an invalid input, a bullet or story problem, no
06-bullets.tmp/ for --commit, no 06-bullets/ for --from-current, a failed
commit); nothing is committed on error; 2 usage error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import stages, validation, wsio  # noqa: E402
from rwrite import bullets, material, report, stories  # noqa: E402
from rwrite.common import (COMMITTED, DRAFT, EVIDENCE, METRICS, PROFILE, PROJECTS, RAW, STAGE, STORIES,  # noqa: E402
                           TMP, WIZARD_PROFILE, WriteError, load_inputs, plural)


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--commit", action="store_true", help="check 06-bullets.tmp/ and commit 06-bullets")
    mode.add_argument("--from-current", action="store_true",
                      help="begin from a copy of the committed bullets and stories, to revise them")
    return parser.parse_args(argv)


def _error(lines, what: str) -> int:
    for line in lines:
        print(f"error: {line}", file=sys.stderr)
    print(what, file=sys.stderr)
    return 1


def _begin(workspace: Path, from_current: bool) -> int:
    what = f"{STAGE} not begun"
    try:
        inputs = load_inputs(workspace)
        if from_current and not (workspace / STAGE).is_dir():
            raise WriteError(f"{STAGE}/ not found: nothing to revise; run write.py without --from-current")
    except WriteError as exc:
        return _error(exc.lines, what)
    found = material.build(workspace, inputs)
    stages.begin(workspace, STAGE, from_current=from_current)
    for line in report.begin_warnings(found):
        print(f"warning: {line}")
    for line in report.notes(found):
        print(f"note: {line}")
    for line in [report.header(found), *report.jobs(found), *report.profile_projects(found),
                 *report.projects(found), *report.reviews(found)]:
        print(line)
    files = f"{DRAFT} and {STORIES}"
    if from_current:
        print(f"began {TMP}/ from the committed bullets and stories: revise {files}, then run write.py --commit")
    else:
        print(f"began {TMP}/: write {files}, then run write.py --commit")
    return 0


def _previous(workspace: Path) -> tuple[list[dict], list[str]]:
    """The last committed bullets, for carrying IDs; [] with a warning when they are not valid."""
    if not (workspace / COMMITTED).is_file():
        return [], []
    if validation.validate_paths(workspace, [COMMITTED]):
        return [], [f"{COMMITTED} is not valid; no bullet IDs are carried from the last run"]
    return wsio.read_json(workspace / COMMITTED), []


def _commit(workspace: Path) -> int:
    what = f"{STAGE} not committed"
    try:
        if not (workspace / TMP).is_dir():
            raise WriteError(f"{TMP}/ not found; run write.py first")
        inputs = load_inputs(workspace)
        draft, error = wsio.load(workspace, DRAFT)
        if error:
            raise WriteError(f"{error}; write the bullets first (see SKILL.md)")
        text, error = wsio.load(workspace, STORIES, "text")
        if error:
            raise WriteError(f"{error}; write the stories first: sanitize apply needs {STAGE}/stories.md "
                             "(see SKILL.md)")
    except WriteError as exc:
        return _error(exc.lines, what)
    found = material.build(workspace, inputs)
    bullet_problems = bullets.check(draft, found)
    story_problems = stories.check(text, found)
    for problems, fix in ((bullet_problems, bullets.FIX), (story_problems, stories.FIX)):
        for line in problems:
            print(line)
        if problems:
            print(f"  {fix}")
    if bullet_problems or story_problems:
        print(f"write check failed: {plural(len(bullet_problems) + len(story_problems), 'problem')}; {what}",
              file=sys.stderr)
        return 1
    previous, warnings = _previous(workspace)
    records = bullets.assign_ids(draft, previous)
    places = [bullets.place(r) for r in records]
    wsio.write_json(workspace / DRAFT, records)
    inputs_used = [PROJECTS, EVIDENCE] + [rel for rel in (RAW, PROFILE, WIZARD_PROFILE, METRICS)
                                          if (workspace / rel).exists()]
    told = stories.told(found.projects)
    quantified = sum(1 for r in records if r["form"] == "xyz_quantified")
    extra = {"bullets": len(records), "quantified": quantified, "stories": len(told)}
    errors = stages.commit(workspace, STAGE, inputs_used, extra=extra)
    if errors:
        return _error(errors, f"commit of {STAGE} failed; previous output left in place")
    warnings += report.gone_metric_warnings(found) + found.raw_warnings
    warnings += report.unplaced_warnings(records, places, found)
    for line in warnings:
        print(f"warning: {line}")
    for line in report.committed(records, places, found):
        print(line)
    print(f"committed {STAGE}: {plural(len(records), 'bullet')} ({quantified} quantified), "
          f"{plural(len(told), 'story', 'stories')}")
    return 0


def main(argv=None) -> int:
    args = _parse(argv)
    return _commit(args.workspace) if args.commit else _begin(args.workspace, args.from_current)


if __name__ == "__main__":
    sys.exit(main())
