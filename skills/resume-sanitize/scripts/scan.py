# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Find likely sensitive terms before the wizard, and commit the model's candidates as 05-terms.

Usage:
  uv run scan.py --workspace WS            # begin 05-terms and print the likely terms
  uv run scan.py --workspace WS --commit   # check 05-terms.tmp/candidates.json and commit 05-terms

Reads 04-projects/projects.json (names, summaries, rank reasons), the title and
excerpt of each project's evidence and of each performance review in
02-evidence/evidence.jsonl, each review's full text in 01-raw/, every string in
03-profile/profile.json, and decisions/terms.json. Without --commit it begins a
fresh 05-terms.tmp/ (discarding a draft) and prints the projects and the likely
terms decisions/terms.json does not decide yet: codename phrases, URLs, emails,
money and capitalized names. The model then writes 05-terms.tmp/candidates.json
(term, kind, proposed_replacement). With --commit the script checks it, fills
in found_in (the places each term appears) and commits 05-terms.

Exit codes: 0 begun, or committed with --commit; 1 error (projects or evidence
missing, an invalid input or decisions/terms.json, a candidate problem, no
05-terms.tmp/, a failed commit); nothing is committed on error; 2 usage error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import stages, terms, wsio  # noqa: E402
from rsanitize import proposals, report  # noqa: E402
from rsanitize.common import (EVIDENCE, PROFILE, PROJECTS, RAW, SCAN_STAGE, SCAN_TMP,  # noqa: E402
                              SanitizeError, decided_keys, load, load_terms, plural)
from rsanitize.texts import scan_texts  # noqa: E402

DRAFT = f"{SCAN_TMP}/candidates.json"


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("--commit", action="store_true",
                        help="check 05-terms.tmp/candidates.json and commit 05-terms")
    return parser.parse_args(argv)


def _inputs(workspace: Path):
    projects = load(workspace, PROJECTS, f"{PROJECTS} not found; run /resume-builder:analyze first")
    evidence = load(workspace, EVIDENCE, f"{EVIDENCE} not found; run /resume-builder:collect first")
    profile = load(workspace, PROFILE)
    entries = load_terms(workspace)
    return projects, evidence, profile, entries


def _error(lines, what: str) -> int:
    for line in lines:
        print(f"error: {line}", file=sys.stderr)
    print(what, file=sys.stderr)
    return 1


def _begin(workspace: Path) -> int:
    try:
        projects, evidence, profile, entries = _inputs(workspace)
    except SanitizeError as exc:
        return _error(exc.lines, f"{SCAN_STAGE} not begun")
    scanned = scan_texts(workspace, projects, evidence, profile)
    decided = decided_keys(entries)
    likely = report.likely_terms(scanned.texts, set())
    shown = [g for g in likely if terms.key(g[1]) not in decided]
    stages.begin(workspace, SCAN_STAGE)
    for line in scanned.warnings:
        print(f"warning: {line}")
    for line in report.scan_header(scanned, projects):
        print(line)
    print(f"likely terms not in decisions/terms.json: {len(shown)}")
    for line in report.likely_lines(shown):
        print(line)
    if len(likely) > len(shown):
        print(f"{plural(len(likely) - len(shown), 'likely term')} decided in decisions/terms.json already")
    print(f"began {SCAN_TMP}/: write {DRAFT}, then run scan.py --commit")
    return 0


def _commit(workspace: Path) -> int:
    try:
        if not (workspace / SCAN_TMP).is_dir():
            raise SanitizeError(f"{SCAN_TMP}/ not found; run scan.py first")
        projects, evidence, profile, entries = _inputs(workspace)
        draft, error = wsio.load(workspace, DRAFT)
        if error:
            raise SanitizeError(f"{error}; write the candidates first (see SKILL.md)")
    except SanitizeError as exc:
        return _error(exc.lines, f"{SCAN_STAGE} not committed")
    scanned = scan_texts(workspace, projects, evidence, profile)
    checked = proposals.check(draft, DRAFT, scanned.texts, entries)
    if checked.problems:
        for line in checked.problems:
            print(line)
        print(f"  {proposals.FIX_CANDIDATES}")
        print(f"candidates check failed: {plural(len(checked.problems), 'problem')}; {SCAN_STAGE} not committed",
              file=sys.stderr)
        return 1
    for line in scanned.warnings:
        print(f"warning: {line}")
    for line in checked.notes:
        print(f"note: {line}")
    wsio.write_json(workspace / DRAFT, checked.records)
    inputs = [PROJECTS, EVIDENCE] + [rel for rel in (RAW, PROFILE) if (workspace / rel).exists()]
    errors = stages.commit(workspace, SCAN_STAGE, inputs, extra={"candidates": len(checked.records)})
    if errors:
        return _error(errors, f"commit of {SCAN_STAGE} failed; previous output left in place")
    decided = decided_keys(entries)
    for record in checked.records:
        state = "decided" if terms.key(record["term"]) in decided else "to decide in the wizard"
        print(f"  {record['kind']:<8}  {record['term']!r} -> {record['proposed_replacement']!r}  "
              f"({proposals.describe_places(record['found_in'])}; {state})")
    undecided = sum(1 for r in checked.records if terms.key(r["term"]) not in decided)
    print(f"committed {SCAN_STAGE}: {plural(len(checked.records), 'candidate')} ({undecided} to decide in the wizard)")
    return 0


def main(argv=None) -> int:
    args = _parse(argv)
    return _commit(args.workspace) if args.commit else _begin(args.workspace)


if __name__ == "__main__":
    sys.exit(main())
