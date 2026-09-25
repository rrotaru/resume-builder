"""Project decisions (decisions/projects.json): checks, applying them, orphans, and decide.py's edits."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rcore import schema

from . import groups as groups_mod
from .common import DECISIONS, STAGE, TMP, AnalyzeError, load_list, shorten

# action -> (fields it needs, fields it may also have). Every record may carry evidence_ids.
FIELDS = {
    "exclude": ((), ()),
    "merge": (("merge_with",), ()),
    "split": (("split_groups",), ()),
    "rename": (("name",), ("summary",)),
    "set_role": (("role",), ()),
    "set_scope": (("scope",), ()),
    "set_rank": (("rank",), ()),
}
# Recording one of these replaces an earlier decision with the same action for the same project.
REPLACING = ("exclude", "rename", "set_role", "set_scope", "set_rank")
FIX = ("fix: record project decisions only with decide.py: discard the named decision (decide.py discard N) "
       "and record it again")


def describe(decision: dict) -> str:
    pid, action = decision["project_id"], decision["action"]
    if action == "merge":
        return f"merge {pid} with {', '.join(decision.get('merge_with', []))}"
    if action == "split":
        groups = decision.get("split_groups", [])
        return f"split {len(groups)} {'group' if len(groups) == 1 else 'groups'} off {pid}"
    if action == "rename":
        return f"rename {pid} to {shorten(decision.get('name', ''))!r}"
    if action in ("set_role", "set_scope", "set_rank"):
        return f"{action} {pid} {decision.get(action[4:], '')}"
    return f"{action} {pid}"


def _label(n: int, decision: dict) -> str:
    return f"decision {n} ({describe(decision)})"


def check_records(decisions: list[dict]) -> list[str]:
    """Fields each action needs or does not use. The schema has no conditionals, so this is checked here."""
    problems = []
    for n, decision in enumerate(decisions, start=1):
        action = decision["action"]
        needs, optional = FIELDS[action]
        where = f"{DECISIONS}: {_label(n, decision)}"
        for name in needs:
            if name not in decision:
                problems.append(f"{where}: needs {name}")
            elif decision[name] in ([], ""):
                problems.append(f"{where}: {name} is empty")
        for name in decision:
            if name not in ("project_id", "action", "evidence_ids", *needs, *optional):
                problems.append(f"{where}: {name} is not used by {action}")
        if action == "merge" and decision["project_id"] in decision.get("merge_with", []):
            problems.append(f"{where}: a project cannot merge with itself")
        if action == "split":
            for k, group in enumerate(decision.get("split_groups", []), start=1):
                if not group:
                    problems.append(f"{where}: split group {k} is empty")
    return problems


def load(workspace: Path) -> list[dict]:
    """decisions/projects.json, checked; [] when missing. Raises AnalyzeError."""
    decisions = load_list(workspace, DECISIONS, "project-decisions")
    problems = check_records(decisions)
    if problems:
        raise AnalyzeError(problems)
    return decisions


# Applying --------------------------------------------------------------------

@dataclass(eq=False)
class Project:
    id: str
    internal_name: str
    summary: str
    evidence: list[str]
    role: str
    scope: str
    rank_reasons: list[str]
    applied: list[str] = field(default_factory=list)
    origin: str = ""  # how the project got its ID, for the report


@dataclass
class Orphan:
    number: int
    decision: dict
    reason: str


@dataclass
class Outcome:
    projects: list[Project]
    excluded: list[tuple[Project, int]] = field(default_factory=list)
    orphans: list[Orphan] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    applied: int = 0
    gone: dict[str, str] = field(default_factory=dict)  # project ID -> what happened to it


def from_groups(stored_groups: list[dict]) -> list[Project]:
    """Projects before decisions: the stored groups (with IDs) in rank order."""
    return [Project(g["id"], g["internal_name"], g["summary"], sorted(g["evidence_ids"]), g["role"], g["scope"],
                    list(g["rank_reasons"])) for g in sorted(stored_groups, key=lambda g: g["rank"])]


def apply(projects: list[Project], decisions: list[dict]) -> Outcome:
    """Apply decisions in file order to projects in rank order."""
    out = Outcome(list(projects))
    order, gone = out.projects, out.gone

    def find(project_id: str) -> Project | None:
        return next((p for p in order if p.id == project_id), None)

    def missing(project_id: str) -> str:
        return gone.get(project_id, f"{project_id} is not a project in this run")

    for n, decision in enumerate(decisions, start=1):
        project, action = find(decision["project_id"]), decision["action"]
        if project is None:
            out.orphans.append(Orphan(n, decision, missing(decision["project_id"])))
            continue
        notes: list[str] = []
        if action == "exclude":
            order.remove(project)
            gone[project.id] = f"{project.id} was excluded by decision {n}"
            out.excluded.append((project, n))
        elif action == "merge":
            others = []
            for other_id in decision["merge_with"]:
                other = find(other_id)
                if other is None or other is project or other in others:
                    if other is None:
                        notes.append(f"{_label(n, decision)}: {missing(other_id)}; nothing merged from it")
                    continue
                others.append(other)
            before = list(order)
            best = min(before.index(p) for p in [project, *others])
            for other in others:
                project.evidence = sorted(set(project.evidence) | set(other.evidence))
                project.rank_reasons += [r for r in other.rank_reasons if r not in project.rank_reasons]
                gone[other.id] = f"{other.id} was merged into {project.id} by decision {n}"
            rest = [p for p in before if p is not project and p not in others]
            order[:] = rest
            order.insert(sum(1 for p in rest if before.index(p) < best), project)
        elif action == "split":
            remaining = set(project.evidence)
            parts = []
            for k, group in enumerate(decision["split_groups"], start=1):
                take = sorted(set(group) & remaining)
                if not take:
                    notes.append(f"{_label(n, decision)}: split group {k} names none of {project.id}'s items; "
                                 "skipped")
                    continue
                remaining -= set(take)
                parts.append((group, take))
            if parts and not remaining:
                out.orphans.append(Orphan(n, decision, f"splitting it would leave {project.id} with no items"))
                continue
            project.evidence = sorted(remaining)
            taken = {p.id for p in order} | set(gone)
            at = order.index(project)
            for j, (group, take) in enumerate(parts, start=2):
                part_id = groups_mod.unique_id(group, taken)
                taken.add(part_id)
                order.insert(at + j - 1, Project(part_id, f"{project.internal_name} (part {j})", "", take,
                                                 project.role, project.scope, [], ["split"],
                                                 f"split off {project.id} by decision {n}"))
        elif action == "rename":
            project.internal_name = decision["name"]
            if "summary" in decision:
                project.summary = decision["summary"]
        elif action in ("set_role", "set_scope"):
            setattr(project, action[4:], decision[action[4:]])
        elif action == "set_rank":
            order.remove(project)
            order.insert(min(decision["rank"], len(order) + 1) - 1, project)
        out.notes += notes
        project.applied.append(action)
        out.applied += 1
    return out


def closest(decision: dict, projects: list[Project]) -> tuple[Project, int, int] | None:
    """The current project sharing the most of a decision's evidence_ids: (project, shared, snapshot size)."""
    snapshot = set(decision.get("evidence_ids", []))
    best = None
    for project in projects:
        shared = len(snapshot & set(project.evidence))
        if shared and (best is None or (shared, groups_mod.jaccard(snapshot, set(project.evidence))) >
                       (best[1], groups_mod.jaccard(snapshot, set(best[0].evidence)))):
            best = (project, shared, len(snapshot))
    return best


# decide.py -------------------------------------------------------------------

def current_projects(workspace: Path) -> tuple[str, list[dict]]:
    """(file, projects) the engineer is looking at: the checkpoint in progress, else the committed stage."""
    for rel in (f"{TMP}/projects.json", f"{STAGE}/projects.json"):
        if (Path(workspace) / rel).is_file():
            return rel, load_list(workspace, rel, "projects", missing_ok=False)
    raise AnalyzeError("no projects to decide about yet; run signals.py and match_projects.py first")


def _project(projects: list[dict], project_id: str, where: str) -> dict:
    found = next((p for p in projects if p["id"] == project_id), None)
    if found is None:
        raise AnalyzeError(f"{project_id} is not one of the current projects in {where}")
    return found


def make(projects: list[dict], where: str, action: str, project_id: str, **values) -> dict:
    """A new decision for a current project, checked against the current projects, with its evidence snapshot."""
    project = _project(projects, project_id, where)
    record: dict = {"project_id": project_id, "action": action}
    if action == "merge":
        others = values["merge_with"]
        for other in others:
            _project(projects, other, where)
        if project_id in others:
            raise AnalyzeError("a project cannot merge with itself")
        if len(set(others)) != len(others):
            raise AnalyzeError("name each project to merge once")
        record["merge_with"] = list(others)
    elif action == "split":
        seen: set[str] = set()
        for k, group in enumerate(values["split_groups"], start=1):
            if not group:
                raise AnalyzeError(f"split group {k} is empty")
            for evidence_id in group:
                if evidence_id not in project["evidence_ids"]:
                    raise AnalyzeError(f"{evidence_id} is not one of {project_id}'s items")
                if evidence_id in seen:
                    raise AnalyzeError(f"{evidence_id} is listed twice")
                seen.add(evidence_id)
        if seen >= set(project["evidence_ids"]):
            raise AnalyzeError(f"leave at least one item in {project_id}: list only the groups to split off")
        record["split_groups"] = [list(g) for g in values["split_groups"]]
    elif action == "rename":
        name = values["name"].strip()
        if not name:
            raise AnalyzeError("the name is empty")
        record["name"] = name
        if values.get("summary") is not None:
            summary = values["summary"].strip()
            if not summary:
                raise AnalyzeError("the summary is empty")
            record["summary"] = summary
    elif action in ("set_role", "set_scope"):
        record[action[4:]] = values[action[4:]]
    elif action == "set_rank":
        if not 1 <= values["rank"] <= len(projects):
            raise AnalyzeError(f"rank must be 1 to {len(projects)}, the number of current projects")
        record["rank"] = values["rank"]
    record["evidence_ids"] = sorted(project["evidence_ids"])
    return record


def add(decisions: list[dict], record: dict) -> list[dict]:
    """The decisions with record added last, replacing an earlier one of the same kind for the same project."""
    kept = decisions
    if record["action"] in REPLACING:
        kept = [d for d in decisions
                if not (d["project_id"] == record["project_id"] and d["action"] == record["action"])]
    return [*kept, record]


def values_of(decision: dict) -> dict:
    """The action's own fields of a decision, as make() takes them."""
    needs, optional = FIELDS[decision["action"]]
    return {name: decision[name] for name in (*needs, *optional) if name in decision}


def validate_file(decisions: list[dict], changed: dict | None = None) -> None:
    """Check the whole file against the schema, and the changed record's fields. Raises AnalyzeError.

    Only the changed record's fields are checked, so an older bad record can still be discarded.
    """
    errors = [f"{DECISIONS}: {e}" for e in schema.validate(decisions, schema.load_schema("project-decisions"))]
    if not errors and changed is not None:
        errors = check_records([changed])
    if errors:
        raise AnalyzeError([f"the change would make {DECISIONS} invalid:", *errors])
