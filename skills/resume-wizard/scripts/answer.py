# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Record one of the engineer's answers in decisions/ (checkpoint 3).

Usage:
  uv run answer.py --workspace WS profile POINTER VALUE     # a fact, e.g. /work/1/endDate 2022-12
  uv run answer.py --workspace WS add POINTER VALUE         # one item of a list, e.g. /skills/0/keywords Kafka
  uv run answer.py --workspace WS unset POINTER             # remove a profile answer
  uv run answer.py --workspace WS confirm ENTRY             # keep a moved answer where it is
  uv run answer.py --workspace WS move ENTRY TO             # move a moved answer to another entry
  uv run answer.py --workspace WS term TERM (--replacement TEXT | --allow) [--kind KIND]
  uv run answer.py --workspace WS remove-term TERM
  uv run answer.py --workspace WS metric PJ --value N --unit UNIT --statement TEXT
  uv run answer.py --workspace WS relink-metric M PJ
  uv run answer.py --workspace WS remove-metric M
  uv run answer.py --workspace WS skip QUESTION             # a profile: or metric: question the engineer declines
  uv run answer.py --workspace WS unskip QUESTION

Profile answers follow the overlay rules of rcore.profile: arrays of objects are
padded with {} up to the index, so /work/1/endDate on an empty file writes
{"work": [{}, {"endDate": ...}]}. The index may be at most one past the end
of the effective array ("-" means one past the end). Only JSON Resume fact
fields are accepted, dates must be YYYY, YYYY-MM or YYYY-MM-DD, and no value
may contain a denied term. The first answer in an entry records, in
decisions/wizard.json, which imported entry it was given for. Term decisions
must leave decisions/terms.json valid: no allowed term containing a denied one
and no replacement containing a denied term. A metric's statement must state
its value. Every file is validated and replaced atomically; on error nothing
changes.

Exit codes: 0 recorded (or nothing to change, said so); 1 rejected, files
unchanged; 2 usage error.
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import profile as core_profile  # noqa: E402
from rcore import terms as core_terms  # noqa: E402
from rcore import wsio  # noqa: E402
from rwizard import metrics as metrics_mod  # noqa: E402
from rwizard import profile as rprofile  # noqa: E402
from rwizard import questions  # noqa: E402
from rwizard import terms as terms_mod  # noqa: E402
from rwizard.common import (CANDIDATES, METRICS, NEW_TERMS, PROFILE, PROJECTS, TERMS, UNCHANGED,  # noqa: E402
                            WIZARD_PROFILE, WizardError, check_schema, load, load_terms, patterns_for, plural,
                            save_json)
from rwizard.state import imported_identity, load_state, save_state, split_entry  # noqa: E402

NEXT = "run questions.py to see what is left"


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("profile", help="record a fact in decisions/profile.json")
    cmd.add_argument("pointer")
    cmd.add_argument("value")
    cmd = sub.add_parser("add", help="add one item to a list field (keywords, courses, roles)")
    cmd.add_argument("pointer")
    cmd.add_argument("value")
    sub.add_parser("unset", help="remove a profile answer").add_argument("pointer")
    sub.add_parser("confirm", help="keep a moved answer where it is").add_argument("entry")
    cmd = sub.add_parser("move", help="move a moved answer to another entry of the same list")
    cmd.add_argument("entry")
    cmd.add_argument("to")
    cmd = sub.add_parser("term", help="deny a term with a replacement, or allow it")
    cmd.add_argument("term")
    how = cmd.add_mutually_exclusive_group(required=True)
    how.add_argument("--replacement")
    how.add_argument("--allow", action="store_true")
    cmd.add_argument("--kind", choices=terms_mod.KINDS)
    sub.add_parser("remove-term", help="remove a term decision").add_argument("term")
    cmd = sub.add_parser("metric", help="record a confirmed metric for a project")
    cmd.add_argument("project")
    cmd.add_argument("--value", required=True)
    cmd.add_argument("--unit", required=True)
    cmd.add_argument("--statement", required=True)
    cmd = sub.add_parser("relink-metric", help="attach a metric to another project")
    cmd.add_argument("metric")
    cmd.add_argument("project")
    sub.add_parser("remove-metric", help="remove a metric").add_argument("metric")
    sub.add_parser("skip", help="decline a profile: or metric: question").add_argument("question")
    sub.add_parser("unskip", help="ask a skipped question again").add_argument("question")
    return parser.parse_args(argv)


# Profile ---------------------------------------------------------------------------

class _Profile:
    """The profile files one command reads and changes."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        imported = load(workspace, PROFILE)
        self.imported = imported if imported is not None else {}
        self.wizard = load(workspace, WIZARD_PROFILE, {})
        self.state = load_state(workspace)
        self.entries = load_terms(workspace)
        self.before = copy.deepcopy(self.wizard)
        self.state_before = self.state.to_json()

    @property
    def effective(self) -> dict:
        return core_profile.overlay(self.imported, self.wizard)

    def check_terms(self, value: str, pointer: str) -> None:
        found = core_terms.terms_in(value, patterns_for(self.entries))
        if found:
            raise WizardError(f"{pointer}: {value!r} contains the denied term {found[0]!r}; give a value without it")

    def check_not_pending(self, entry: str | None) -> None:
        if rprofile.is_pending(entry, rprofile.moved_answers(self.imported, self.wizard, self.state)):
            raise WizardError(f"{WIZARD_PROFILE} {entry} is waiting for answer.py move, confirm or unset "
                              f"(moved:{entry} in questions.py); resolve that first")

    def save(self) -> None:
        rprofile.anchor_new_entries(self.before, self.wizard, self.imported, self.state)
        check_schema(self.wizard, "resume", WIZARD_PROFILE)
        if self.wizard != self.before:
            save_json(self.workspace, WIZARD_PROFILE, self.wizard)
        if self.state.to_json() != self.state_before:
            save_state(self.workspace, self.state)


def _profile(workspace: Path, args) -> list[str]:
    files = _Profile(workspace)
    target = rprofile.target(args.pointer, files.effective)
    value = rprofile.check_value(target.field, args.value, target.pointer)
    files.check_terms(value, target.pointer)
    files.check_not_pending(target.entry)
    rprofile.set_value(files.wizard, target, value)
    files.save()
    added = f" (a new entry, {target.entry})" if target.new_entry else ""
    return [f"recorded {target.pointer} {value!r} in {WIZARD_PROFILE}{added}"]


def _add(workspace: Path, args) -> list[str]:
    files = _Profile(workspace)
    target = rprofile.target(args.pointer, files.effective, for_add=True)
    value = args.value.strip()
    if not value:
        raise WizardError(f"{target.pointer}: the value is empty")
    files.check_terms(value, target.pointer)
    files.check_not_pending(target.entry)
    current = wsio.resolve_pointer(files.effective, target.pointer) if _resolves(files.effective, target) else []
    if isinstance(current, list) and value in current:
        return [f"{value!r} is already in the profile at {target.pointer}; nothing recorded"]
    rprofile.add_item(files.wizard, target, value)
    files.save()
    return [f"added {value!r} to {target.pointer} in {WIZARD_PROFILE}"]


def _resolves(doc, target) -> bool:
    try:
        wsio.resolve_pointer(doc, target.pointer)
    except KeyError:
        return False
    return True


def _unset(workspace: Path, args) -> list[str]:
    files = _Profile(workspace)
    rprofile.tokens(args.pointer)
    rprofile.unset(files.wizard, args.pointer)
    files.save()
    return [f"removed {args.pointer} from {WIZARD_PROFILE}; the imported value applies again"]


def _confirm(workspace: Path, args) -> list[str]:
    files = _Profile(workspace)
    entry = rprofile.check_entry(args.entry)
    if rprofile.answer_at(files.wizard, entry) is None:
        raise WizardError(f"{WIZARD_PROFILE} has no answer at {entry}")
    now = imported_identity(files.imported, entry)
    files.state.anchors[entry] = now
    files.save()
    section = split_entry(entry)[1]
    where = f"'{core_profile.describe(section, now)}'" if now is not None else f"a new {section} entry"
    return [f"confirmed the answer at {entry} for {where}"]


def _move(workspace: Path, args) -> list[str]:
    files = _Profile(workspace)
    source, dest = rprofile.check_entry(args.entry), rprofile.check_entry(args.to)
    rprofile.move(files.wizard, source, dest, files.effective)
    files.state.anchors.pop(source, None)
    files.save()
    return [f"moved the answer at {source} to {dest}"]


# Terms -----------------------------------------------------------------------------

def _term(workspace: Path, args) -> list[str]:
    entries = load_terms(workspace)
    kind = args.kind
    if kind is None:
        key = core_terms.key(args.term)
        proposals = (load(workspace, CANDIDATES) or []) + load(workspace, NEW_TERMS, [])
        kind = next((p["kind"] for p in proposals if core_terms.key(p["term"]) == key), None)
        if kind is None:
            raise WizardError(f"{args.term!r} is not a candidate or new term; give --kind "
                              f"({', '.join(terms_mod.KINDS)})")
    updated = terms_mod.record(entries, args.term, None if args.allow else args.replacement, kind)
    save_json(workspace, TERMS, updated)
    decision = next(e for e in updated if core_terms.key(e["term"]) == core_terms.key(args.term))
    lines = [f"recorded {terms_mod.describe(decision)} in {TERMS}"]
    lines += core_terms.allowed_notices(updated)
    imported = load(workspace, PROFILE) or {}
    effective = core_profile.overlay(imported, load(workspace, WIZARD_PROFILE, {}))
    hits, _ = questions.fact_hits(effective, updated)
    if hits:
        lines.append(f"{plural(len(hits), 'fact field')} of the profile {'holds' if len(hits) == 1 else 'hold'} "
                     "a denied term: questions.py lists them as fact: questions")
    return lines


def _remove_term(workspace: Path, args) -> list[str]:
    data, error = wsio.load(workspace, TERMS)
    if error:
        raise WizardError(error)
    save_json(workspace, TERMS, terms_mod.remove(data, args.term))
    return [f"removed {args.term!r} from {TERMS}"]


# Metrics ---------------------------------------------------------------------------

def _metric(workspace: Path, args) -> list[str]:
    projects, metrics = load(workspace, PROJECTS), load(workspace, METRICS, [])
    project = metrics_mod.project(projects, args.project)
    value = metrics_mod.parse_value(args.value)
    unit = args.unit.strip()
    if not unit:
        raise WizardError("the unit is empty; give one, such as %, ms, requests/s or incidents")
    statement = args.statement.strip()
    if not statement:
        raise WizardError("the statement is empty; write one sentence that states the value")
    if not metrics_mod.states_value(statement, value):
        raise WizardError(f"the statement {statement!r} does not state the value {value}; write the number "
                          "in the statement as it is recorded")
    record = {"id": metrics_mod.next_id(metrics), "project_id": project["id"], "value": value,
              "unit": unit, "statement": statement, "evidence_ids": sorted(project["evidence_ids"])}
    metrics.append(record)
    check_schema(metrics, "metrics", METRICS)
    save_json(workspace, METRICS, metrics)
    return [f"recorded {metrics_mod.describe(record)} for {project['id']} {project['internal_name']!r} in {METRICS}"]


def _relink_metric(workspace: Path, args) -> list[str]:
    projects, metrics = load(workspace, PROJECTS), load(workspace, METRICS, [])
    metric = metrics_mod.find(metrics, args.metric)
    project = metrics_mod.project(projects, args.project)
    metric["project_id"], metric["evidence_ids"] = project["id"], sorted(project["evidence_ids"])
    check_schema(metrics, "metrics", METRICS)
    save_json(workspace, METRICS, metrics)
    return [f"re-linked {metric['id']} to {project['id']} {project['internal_name']!r}"]


def _remove_metric(workspace: Path, args) -> list[str]:
    metrics = load(workspace, METRICS, [])
    metric = metrics_mod.find(metrics, args.metric)
    save_json(workspace, METRICS, [m for m in metrics if m is not metric])
    return [f"removed {metrics_mod.describe(metric)} from {METRICS}; a bullet citing metric:{metric['id']} "
            "needs /resume-builder:write again"]


# Skips -----------------------------------------------------------------------------

def _skip(workspace: Path, args) -> list[str]:
    ctx = questions.context(workspace)
    found, _ = questions.compute(ctx)
    question = next((q for q in found if q.key == args.question), None)
    if question is None:
        raise WizardError(f"{args.question} is not an open question; questions.py lists them")
    if question.skipped:
        return [f"{args.question} is skipped already"]
    if not question.skippable:
        raise WizardError(f"{args.question} cannot be skipped; answer it as questions.py says")
    ctx.state.skip(args.question, ctx.imported)
    save_state(workspace, ctx.state)
    return [f"skipped {args.question}; the wizard will not ask it again"]


def _unskip(workspace: Path, args) -> list[str]:
    state = load_state(workspace)
    if not state.unskip(args.question):
        raise WizardError(f"{args.question} is not skipped")
    save_state(workspace, state)
    return [f"{args.question} will be asked again"]


HANDLERS = {"profile": _profile, "add": _add, "unset": _unset, "confirm": _confirm, "move": _move,
            "term": _term, "remove-term": _remove_term, "metric": _metric, "relink-metric": _relink_metric,
            "remove-metric": _remove_metric, "skip": _skip, "unskip": _unskip}


def main(argv=None) -> int:
    args = _parse(argv)
    try:
        lines = HANDLERS[args.command](args.workspace, args)
    except WizardError as exc:
        for line in exc.lines:
            print(f"error: {line}", file=sys.stderr)
        print(UNCHANGED, file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    print(NEXT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
