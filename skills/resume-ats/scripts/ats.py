# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Draft the general resume or a job version into 08-ats.tmp/, then check every version and commit 08-ats.

Usage:
  uv run ats.py --workspace WS                          # draft the general resume
  uv run ats.py --workspace WS --jd FILE [--job SLUG]   # draft a job version from a posting
  uv run ats.py --workspace WS --job SLUG               # redraft a job version from its saved posting
  uv run ats.py --workspace WS --revise VERSION         # revise a version without redrafting it
  uv run ats.py --workspace WS --remove SLUG            # drop a job version from the draft
  uv run ats.py --workspace WS --commit                 # check every version and commit 08-ats

A draft is 08-ats.tmp/. If it does not exist, a command begins it as a copy of
the committed 08-ats/ (or empty), so versions it does not name are kept; if it
exists, the command works in it. Drafting writes the version's resume.json:
every fact field copied from the effective profile and every bullet of
07-sanitized/bullets.json that has a place under the entry for it (never
06-bullets/). The model then writes the version's keywords.json and edits
resume.json. --commit checks every version in the draft (files, keywords,
schema, sources and fact fields, terms, placement, the general resume's
claims, lint and length), writes each report.json and each job's flags.json
(the claim diff), and commits 08-ats.

Exit codes: 0 drafted, revised, removed or committed; 1 error (inputs missing
or invalid, a bad slug or posting, no such version, a problem in the draft,
no draft for --commit, a failed commit); nothing is committed on error;
2 usage error.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import config, sources, stages, terms, wsio  # noqa: E402
from rats import check, claims, coverage, draft, lint, material, report  # noqa: E402
from rats.common import (FLAGS, GENERAL, JD, KEYWORDS, REPORT, RESUME, STAGE, TMP, AtsError, Version,  # noqa: E402
                         committed_versions, draft_versions, load_inputs, one_line, plural, recorded_inputs,
                         slug_error, slug_from, version)

FIXES = {
    "files": "fix: remove what ats does not write, and draft a version again when a file of it is missing "
             "(see SKILL.md)",
    "keywords": "fix: edit keywords.json: each keyword once, spelled as the posting (or, for the general resume, "
                "the target role's postings) spell it; a job's keywords must be in its jd.txt",
    "schema": "fix: the draft's resume.json no longer matches tailored-resume.schema.json (validate.py names the "
              "field); undo the edit, or draft the version again",
    "sources": "fix: keep every fact as drafted (leave an entry out or shorten a date, never retype one) and each "
               "bullet's sources; if the profile itself is wrong, fix it with /resume-builder:wizard and draft again",
    "terms": "fix: a denied term may not be on the resume: keep a bullet's sanitized wording; for a fact field, set "
             "a replacement value with /resume-builder:wizard and draft again; for a false positive, an allowed term "
             "the engineer agrees to (/resume-builder:wizard)",
    "placement": "fix: keep each bullet under the entry it was drafted under, with its bullet_id and sources, and "
                 "use each bullet once",
    "claims": "fix: in the general resume, reword only within what each bullet's sources say, or use the bullet's "
              "own text; a job version may go further, and its claims are flagged for checkpoint 4",
    "lint": "fix: see each line (see SKILL.md)",
}


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("--jd", type=Path, help="a job posting (UTF-8 text) to draft a job version from")
    parser.add_argument("--job", help="the job version's slug (default: from the posting's file name)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--commit", action="store_true", help="check every version in the draft and commit 08-ats")
    mode.add_argument("--revise", metavar="VERSION", help="revise a version in the draft without redrafting it")
    mode.add_argument("--remove", metavar="SLUG", help="drop a job version from the draft")
    args = parser.parse_args(argv)
    if (args.commit or args.revise or args.remove) and (args.jd or args.job):
        parser.error("--jd and --job draft a job version; they do not go with --commit, --revise or --remove")
    return args


def _error(lines, what: str) -> int:
    for line in lines:
        print(f"error: {line}", file=sys.stderr)
    print(what, file=sys.stderr)
    return 1


def _ensure_draft(workspace: Path) -> str:
    """Begin 08-ats.tmp/ as a copy of the committed stage unless a draft exists; say which."""
    if (workspace / TMP).is_dir():
        names = [v.name for v in draft_versions(workspace)]
        return "continuing the draft" + (f" with {', '.join(names)}" if names else "")
    stages.begin(workspace, STAGE, from_current=True)  # also restores an interrupted commit's 08-ats.old/
    names = [v.name for v in draft_versions(workspace)]
    return f"a copy of the committed {STAGE}/ with {', '.join(names)}" if names else "a new draft"


def _read_posting(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise AtsError(f"{path}: not found") from None
    except UnicodeDecodeError:
        raise AtsError(f"{path}: not UTF-8 text; save the posting's text as a .txt file") from None
    except OSError as exc:
        raise AtsError(f"{path}: cannot be read ({exc.strerror})") from None
    if not text.strip():
        raise AtsError(f"{path}: the posting is empty")
    return text


def _saved_posting(workspace: Path, target: Version) -> str:
    for rel in (target.draft(JD), target.committed(JD)):
        if (workspace / rel).is_file():
            return _read_posting(workspace / rel)
    raise AtsError(f"no saved posting for {target.name}; draft it with ats.py --jd FILE --job {target.name}")


def _job(args, workspace: Path) -> tuple[Version, str | None]:
    """The job version to draft and its posting's text (None: read the saved one)."""
    if args.jd is not None:
        slug = args.job or slug_from(args.jd)
        error = slug_error(slug) if slug else "the posting's file name gives no slug; give one with --job"
        if error:
            raise AtsError(error)
        return Version(slug), _read_posting(config.resolve_path(workspace, str(args.jd)))
    target = version(args.job)
    if not target.is_job:
        raise AtsError(slug_error(args.job))
    return target, None


def _draft(args, workspace: Path) -> int:
    what = "nothing drafted"
    try:
        inputs = load_inputs(workspace)
        found = material.build(workspace, inputs)
        if args.jd is None and args.job is None:
            target, posting = Version(GENERAL), None
        else:
            target, posting = _job(args, workspace)
            if posting is None:
                posting = _saved_posting(workspace, target)
    except AtsError as exc:
        return _error(exc.lines, what)
    began = _ensure_draft(workspace)
    folder = workspace / TMP / target.folder
    if args.jd is not None and folder.is_dir():
        shutil.rmtree(folder)  # a new posting: its keywords and tailoring start over
    folder.mkdir(parents=True, exist_ok=True)
    for name in (REPORT, FLAGS):
        (folder / name).unlink(missing_ok=True)
    if target.is_job:
        (folder / JD).write_text(posting, encoding="utf-8")
    resume = draft.build(found)
    wsio.write_json(folder / RESUME, resume)

    for line in report.stale_warnings(workspace) + report.homeless_warnings(found) + \
            report.denied_fact_warnings(found):
        print(f"warning: {line}")
    for line in report.withheld_notes(found):
        print(f"note: {line}")
    print(f"ats: drafted {target.name} in {TMP}/{target.folder}/ ({began})")
    if target.is_job:
        first = next((one_line(line) for line in posting.splitlines() if line.strip()), "")
        source = f" from {args.jd}" if args.jd is not None else ""
        print(f"posting: {target.draft(JD)}{source}: {first}")
    print(f"target role: {inputs.target_role or '(none in config.json)'}")
    _, _, length = lint.lint(resume, found)
    print(report.length_line(length))
    for line in report.places(found):
        print(line)
    placed = sum(len(e["x-highlights"]) for s in material.SECTIONS for e in resume.get(s, []))
    print(f"{target.draft(RESUME)}: every fact from the profile and {plural(placed, 'bullet')} in their places, "
          f"estimated {length['estimated_lines']} of {length['line_budget']} lines")
    if (folder / KEYWORDS).is_file():
        print(f"kept {target.draft(KEYWORDS)} from before; check it still fits")
    print(report.next_line(target))
    return 0


def _revise(args, workspace: Path) -> int:
    what = "nothing begun"
    try:
        target = version(args.revise)
        inputs = load_inputs(workspace)
        found = material.build(workspace, inputs)
        present = draft_versions(workspace) if (workspace / TMP).is_dir() else \
            [Version(n) for n in committed_versions(workspace)]
        if target not in present:
            raise AtsError(f"{target.name}: not in the draft or in {STAGE}/; draft it with ats.py")
    except AtsError as exc:
        return _error(exc.lines, what)
    began = _ensure_draft(workspace)
    resume, problems = check.resume(workspace, target)
    if resume is None:
        return _error(problems, f"{target.draft(RESUME)} cannot be revised; draft it again")
    print(f"ats: revising {target.name} in {TMP}/{target.folder}/ ({began})")
    for line in report.revise_lines(resume, found):
        print(line)
    if target.is_job:
        keywords, _ = check.keywords(workspace, target, inputs.target_role)
        flagged = claims.flags(resume, found, keywords)
        print(f"flags: {len(flagged['flags'])}")
        for line in report.flag_lines(flagged):
            print(line)
    print(f"next: edit the x-highlights texts in {target.draft(RESUME)} (to revert a bullet, use its original "
          "text), then run ats.py --commit")
    return 0


def _remove(args, workspace: Path) -> int:
    what = "nothing removed"
    try:
        target = version(args.remove)
        if not target.is_job:
            raise AtsError("--remove drops a job version; the general resume is redrafted, not removed")
        present = draft_versions(workspace) if (workspace / TMP).is_dir() else \
            [Version(n) for n in committed_versions(workspace)]
        if target not in present:
            raise AtsError(f"{target.name}: not in the draft or in {STAGE}/")
    except AtsError as exc:
        return _error(exc.lines, what)
    began = _ensure_draft(workspace)
    shutil.rmtree(workspace / TMP / target.folder)
    jobs = workspace / TMP / "jobs"
    if jobs.is_dir() and not any(jobs.iterdir()):
        jobs.rmdir()
    print(f"ats: removed {target.name} from {TMP}/ ({began}); run ats.py --commit")
    return 0


def _commit(workspace: Path) -> int:
    what = f"{STAGE} not committed"
    try:
        if not (workspace / TMP).is_dir():
            raise AtsError(f"{TMP}/ not found; draft a version with ats.py first")
        inputs = load_inputs(workspace)
        found = material.build(workspace, inputs)
    except AtsError as exc:
        return _error(exc.lines, what)
    versions, file_problems = check.files(workspace)
    problems: dict[str, list[str]] = {kind: [] for kind in FIXES}
    problems["files"] += file_problems
    if not versions and not file_problems:
        return _error([f"{TMP}/ holds no version; draft the general resume or a job version with ats.py"], what)
    known = sources.load_known(workspace)
    patterns, term_errors = terms.load_patterns(workspace)
    results = {}
    for target in versions:
        if target.is_job:
            _, error = check.posting(workspace, target)
            if error and (workspace / target.draft(JD)).is_file():
                problems["files"].append(error)
        keywords, keyword_problems = ([], []) if not (workspace / target.draft(KEYWORDS)).is_file() else \
            check.keywords(workspace, target, inputs.target_role)
        problems["keywords"] += keyword_problems
        if not (workspace / target.draft(RESUME)).is_file():
            continue
        resume, schema_problems = check.resume(workspace, target)
        if resume is None:
            problems["schema"] += schema_problems
            continue
        resume = draft.normalize(resume)
        rel = target.draft(RESUME)
        wsio.write_json(workspace / rel, resume)
        problems["sources"] += sources.check_file(workspace, rel, known)
        problems["terms"] += term_errors or terms.check_file(workspace, rel, patterns)
        problems["placement"] += check.placement(resume, found, rel)
        errors, warnings, length = lint.lint(resume, found)
        problems["lint"] += [f"{rel}: {e}" for e in errors]
        examined = list(claims.examined(resume, found, keywords))
        if not target.is_job:
            problems["claims"] += [f"{rel}: {pointer} ({bullet_id}): {reason}"
                                   for pointer, bullet_id, _, reasons in examined for reason in reasons]
        results[target] = (resume, keywords, warnings, length)
    problems["terms"] = list(dict.fromkeys(problems["terms"]))  # terms.json errors once
    if known.errors:
        problems["sources"] = list(dict.fromkeys(known.errors + problems["sources"]))
    count = sum(len(lines) for lines in problems.values())
    if count:
        for kind, lines in problems.items():
            for line in lines:
                print(line)
            if lines:
                print(f"  {FIXES[kind]}")
        print(f"ats check failed: {plural(count, 'problem')}; {what}; the draft stays in {TMP}/", file=sys.stderr)
        return 1

    summaries, flagged = [], {}
    for target, (resume, keywords, warnings, length) in results.items():
        covered = coverage.cover(resume, keywords, found)
        wsio.write_json(workspace / target.draft(REPORT), report.report_json(resume, found, covered, length, warnings))
        line = (f"{target.name}: {report.bullet_count(resume, found)}, {length['estimated_lines']} of "
                f"{length['line_budget']} lines; {report.keyword_summary(covered)}")
        extra_lines = []
        if target.is_job:
            flags = claims.flags(resume, found, keywords)
            wsio.write_json(workspace / target.draft(FLAGS), flags)
            flagged[target.name] = len(flags["flags"])
            line += f"; {flagged[target.name]} flagged"
            extra_lines = report.flag_lines(flags)
        summaries.append((target, warnings, [line] + extra_lines))
    extra = {"versions": [t.name for t in results], "flagged": flagged}
    errors = stages.commit(workspace, STAGE, recorded_inputs(workspace), extra=extra)
    if errors:
        return _error(errors, f"commit of {STAGE} failed; previous output left in place")
    for target, warnings, _ in summaries:
        for warning in warnings:
            print(f"warning: {target.name}: {warning}")
    for line in found.citations.warnings:
        print(f"warning: {line}")
    for _, _, lines in summaries:
        for line in lines:
            print(line)
    total = sum(flagged.values())
    print(f"committed {STAGE}: {', '.join(t.name for t in results)}" + (f" ({total} flagged)" if flagged else ""))
    return 0


def main(argv=None) -> int:
    args = _parse(argv)
    workspace = args.workspace
    if args.commit:
        return _commit(workspace)
    if args.revise:
        return _revise(args, workspace)
    if args.remove:
        return _remove(args, workspace)
    return _draft(args, workspace)


if __name__ == "__main__":
    sys.exit(main())
