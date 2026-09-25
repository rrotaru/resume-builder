# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Record the engineer's checkpoint 2 decisions in decisions/projects.json.

Usage:
  uv run decide.py --workspace WS list
  uv run decide.py --workspace WS exclude PJ
  uv run decide.py --workspace WS rename PJ --name NAME [--summary TEXT]
  uv run decide.py --workspace WS set-role PJ lead|core|supporting
  uv run decide.py --workspace WS set-scope PJ team|cross-team|org|company
  uv run decide.py --workspace WS set-rank PJ N
  uv run decide.py --workspace WS merge PJ --with PJ [PJ ...]
  uv run decide.py --workspace WS split PJ --group EV[,EV ...] [--group ...]
  uv run decide.py --workspace WS relink N PJ
  uv run decide.py --workspace WS discard N

Decisions name the current projects: 04-projects.tmp/projects.json while
checkpoint 2 is in progress, else the committed 04-projects/projects.json.
Each decision stores the project's evidence IDs, so an orphaned one can be
re-linked later. exclude, rename, set-role, set-scope and set-rank replace an
earlier decision of the same kind for the same project. relink records decision
N again for another project; discard removes it. The file is validated and
replaced atomically. Run match_projects.py afterwards to see the result.

Exit codes: 0 done; 1 error (no current projects, an unknown project or evidence
ID, an invalid split, a rank out of range, an invalid decisions file); the file
is unchanged on error; 2 usage error.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from ranalyze import decisions  # noqa: E402
from ranalyze.common import DECISIONS, AnalyzeError, load_list, save_json  # noqa: E402

ACTIONS = {"exclude": "exclude", "rename": "rename", "set-role": "set_role", "set-scope": "set_scope",
           "set-rank": "set_rank", "merge": "merge", "split": "split"}


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="print the decisions, numbered from 1")
    sub.add_parser("exclude", help="leave a project out").add_argument("project")
    rename = sub.add_parser("rename", help="set a project's name, and optionally its summary")
    rename.add_argument("project")
    rename.add_argument("--name", required=True)
    rename.add_argument("--summary")
    role = sub.add_parser("set-role", help="set a project's role")
    role.add_argument("project")
    role.add_argument("role", choices=["lead", "core", "supporting"])
    scope = sub.add_parser("set-scope", help="set a project's scope")
    scope.add_argument("project")
    scope.add_argument("scope", choices=["team", "cross-team", "org", "company"])
    rank = sub.add_parser("set-rank", help="move a project to a rank")
    rank.add_argument("project")
    rank.add_argument("rank", type=int)
    merge = sub.add_parser("merge", help="move other projects' evidence into a project")
    merge.add_argument("project")
    merge.add_argument("--with", dest="merge_with", nargs="+", required=True, metavar="PJ")
    split = sub.add_parser("split", help="split groups of evidence off a project")
    split.add_argument("project")
    split.add_argument("--group", dest="groups", action="append", required=True, metavar="EV[,EV ...]")
    relink = sub.add_parser("relink", help="record decision N again for another project")
    relink.add_argument("number", type=int)
    relink.add_argument("project")
    sub.add_parser("discard", help="remove decision N").add_argument("number", type=int)
    return parser.parse_args(argv)


def _number(chosen: list[dict], number: int) -> dict:
    if not 1 <= number <= len(chosen):
        raise AnalyzeError(f"there is no decision {number}; decide.py list shows them")
    return chosen[number - 1]


def _values(args) -> dict:
    if args.command == "rename":
        return {"name": args.name, "summary": args.summary}
    if args.command in ("set-role", "set-scope"):
        return {args.command[4:]: getattr(args, args.command[4:])}
    if args.command == "set-rank":
        return {"rank": args.rank}
    if args.command == "merge":
        return {"merge_with": args.merge_with}
    if args.command == "split":
        return {"split_groups": [[e for e in re.split(r"[\s,]+", group) if e] for group in args.groups]}
    return {}


def main(argv=None) -> int:
    args = _parse(argv)
    workspace = args.workspace
    target = workspace / DECISIONS
    try:
        chosen = load_list(workspace, DECISIONS, "project-decisions")
        if args.command == "list":
            for n, decision in enumerate(chosen, start=1):
                print(f"{n}. {decisions.describe(decision)}")
            if not chosen:
                print("no project decisions")
            return 0
        if args.command == "discard":
            gone = _number(chosen, args.number)
            updated = [d for d in chosen if d is not gone]
            decisions.validate_file(updated)
            save_json(target, updated)
            print(f"discarded decision {args.number}: {decisions.describe(gone)}")
            print("run match_projects.py to see the projects without it")
            return 0
        where, projects = decisions.current_projects(workspace)
        if args.command == "relink":
            old = _number(chosen, args.number)
            rest = [d for d in chosen if d is not old]
            record = decisions.make(projects, where, old["action"], args.project, **decisions.values_of(old))
        else:
            rest = chosen
            record = decisions.make(projects, where, ACTIONS[args.command], args.project, **_values(args))
        updated = decisions.add(rest, record)
        decisions.validate_file(updated, record)
        save_json(target, updated)
    except AnalyzeError as exc:
        for line in exc.lines:
            print(f"error: {line}", file=sys.stderr)
        print(f"{DECISIONS} unchanged", file=sys.stderr)
        return 1
    verb = f"re-linked decision {args.number} as" if args.command == "relink" else "recorded"
    print(f"{verb} decision {len(updated)}: {decisions.describe(record)}")
    print("run match_projects.py to see the projects with it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
