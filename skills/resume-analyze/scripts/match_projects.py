# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Check the model's project groups, carry IDs forward, apply the engineer's decisions, and commit 04-projects.

Usage:
  uv run match_projects.py --workspace WS            # check, then write the projects for checkpoint 2
  uv run match_projects.py --workspace WS --commit   # the same, then commit 04-projects

Reads 04-projects.tmp/groups.json (the model's groups), 04-projects.tmp/signals.json,
02-evidence/evidence.jsonl, the committed 04-projects/groups.json (the last run's
groups), decisions/projects.json and config.json. A group sharing half or more
of its combined items with a group of the last run keeps that group's ID; any
other gets rcore.ids.project_id of its evidence. Decisions apply in file order.
Writes groups.json (with IDs) and projects.json into 04-projects.tmp/ and prints
the projects, exclusions, notes, warnings and orphaned decisions.

Exit codes: 0 written (and committed with --commit); 1 error (no 04-projects.tmp/,
a missing or invalid signals.json or groups.json, signals.json out of date with
the evidence, config.json or 01-raw/, a group problem, an invalid decision, a
failed commit); nothing is
committed on error; 2 usage error; 3 orphaned decisions: the files are written
for review, and nothing is committed until each is re-linked or discarded.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import config, schema, stages, wsio  # noqa: E402
from ranalyze import clusters, decisions, groups, report  # noqa: E402
from ranalyze.common import (DECISIONS, EVIDENCE, METRICS, RAW, STAGE, TMP, AnalyzeError,  # noqa: E402
                             evidence_hash, last_timestamp, load_config, load_evidence, load_list, month,
                             plural)

SIGNALS = f"{TMP}/signals.json"


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("--commit", action="store_true", help="commit 04-projects if nothing is orphaned")
    return parser.parse_args(argv)


def _load_signals(workspace: Path, cfg: dict, evidence: list[dict]) -> dict:
    """The signals the groups were made from, checked against what signals.py would write now.

    The evidence hash gives the usual reason. Recomputing also catches a changed username in
    config.json or a changed raw record, which the commit would otherwise record as current.
    """
    data, error = wsio.load(workspace, SIGNALS)
    if error:
        raise AnalyzeError(f"{error}; run signals.py")
    errors = schema.validate(data, schema.load_schema("signals"))
    if errors:
        raise AnalyzeError([f"{SIGNALS}: {e}" for e in errors] + ["run signals.py again"])
    current = evidence_hash(workspace)
    if data["evidence_sha256"] != current:
        raise AnalyzeError(f"{EVIDENCE} changed since signals.py ran; run signals.py and group again")
    if clusters.compute(workspace, cfg, evidence, current)[0] != data:
        raise AnalyzeError(f"{SIGNALS} no longer matches config.json and {RAW}/ (a username or a raw record "
                           "changed since signals.py ran); run signals.py and group again")
    return data


def _load_draft(workspace: Path):
    data, error = wsio.load(workspace, groups.DRAFT)
    if error:
        raise AnalyzeError(f"{error}; write the groups first (see SKILL.md)")
    return data


def _previous(workspace: Path) -> tuple[list[dict], list[str]]:
    rel = f"{STAGE}/groups.json"
    try:
        return load_list(workspace, rel, "project-groups"), []
    except AnalyzeError:
        return [], [f"{rel} is not valid; no IDs are carried from the last run"]


def _metric_warnings(workspace: Path, outcome: decisions.Outcome) -> list[str]:
    metrics, error = wsio.load(workspace, METRICS)
    if error or not isinstance(metrics, list):
        return []
    current = {p.id for p in outcome.projects}
    warnings = []
    for metric in metrics:
        pid = metric.get("project_id") if isinstance(metric, dict) else None
        if isinstance(pid, str) and pid not in current:
            what = outcome.gone.get(pid, f"{pid} is not a project in this run")
            warnings.append(f"{METRICS} {metric.get('id')}: {what}; the wizard re-links or removes this metric")
    return warnings


def _record(project: decisions.Project, rank: int, prompt: bool, by_id: dict) -> dict:
    items = [by_id[e] for e in project.evidence]
    return {"id": project.id, "internal_name": project.internal_name, "summary": project.summary,
            "evidence_ids": sorted(project.evidence), "role": project.role, "scope": project.scope,
            "start": month(min(i["created_at"] for i in items)), "end": month(max(map(last_timestamp, items))),
            "rank": rank, "rank_reasons": project.rank_reasons, "metric_prompt": prompt}


def _error(lines) -> int:
    for line in lines:
        print(f"error: {line}", file=sys.stderr)
    print(f"{STAGE} not written", file=sys.stderr)
    return 1


def main(argv=None) -> int:
    args = _parse(argv)
    workspace = args.workspace
    try:
        if not (workspace / TMP).is_dir():
            raise AnalyzeError(f"{TMP}/ not found; run signals.py first, or stage.py begin {STAGE} "
                               "--from-current to reuse the committed grouping")
        cfg = load_config(workspace)
        evidence = load_evidence(workspace)
        signals = _load_signals(workspace, cfg, evidence)
        draft = _load_draft(workspace)
        settings = cfg["metric_prompts"]
        config.metric_prompt_count(0, settings["percent"], settings["min"], settings["max"])
    except ValueError as exc:
        return _error([f"config.json {exc}"])
    except AnalyzeError as exc:
        return _error(exc.lines)
    by_id = {item["id"]: item for item in evidence}
    problems = groups.check(draft, by_id)
    if problems:
        for line in problems:
            print(line)
        print(f"  {groups.FIX}")
        print(f"groups check failed: {plural(len(problems), 'problem')}; {STAGE} not written", file=sys.stderr)
        return 1
    try:
        chosen = decisions.load(workspace)
    except AnalyzeError as exc:
        for line in exc.lines:
            print(line)
        print(f"  {decisions.FIX}")
        print(f"{DECISIONS} is not valid; {STAGE} not written", file=sys.stderr)
        return 1

    previous, warnings = _previous(workspace)
    assigned = groups.assign_ids(draft, previous)
    stored = groups.with_ids(draft, assigned)
    origin = {group_id: (f"carried from the last run (similarity {float(similarity):.2f})" if old else "new")
              for group_id, old, similarity in assigned}
    projects = decisions.from_groups(stored)
    for project in projects:
        project.origin = origin[project.id]
    outcome = decisions.apply(projects, chosen)
    prompts = config.metric_prompt_count(len(outcome.projects), settings["percent"], settings["min"],
                                         settings["max"])
    records = [_record(p, rank, rank <= prompts, by_id) for rank, p in enumerate(outcome.projects, start=1)]
    tmp = workspace / TMP
    wsio.write_json(tmp / "groups.json", stored)
    wsio.write_json(tmp / "projects.json", records)

    carried = sum(1 for _, old, _ in assigned if old)
    for line in warnings + _metric_warnings(workspace, outcome):
        print(f"warning: {line}")
    for line in groups.cluster_notes(draft, signals["clusters"]) + outcome.notes:
        print(f"note: {line}")
    for line in report.checkpoint(records, outcome, evidence, clusters.mentions(evidence), prompts, carried,
                                  len(assigned) - carried):
        print(line)
    print(f"wrote {TMP}/groups.json and {TMP}/projects.json")
    if outcome.orphans:
        for line in report.orphans(outcome):
            print(line)
        print(f"{plural(len(outcome.orphans), 'orphaned decision')}: re-link or discard each one; "
              f"{STAGE} not committed", file=sys.stderr)
        return 3
    if not args.commit:
        return 0

    inputs = [EVIDENCE, "config.json"] + [rel for rel in (RAW, DECISIONS) if (workspace / rel).exists()]
    grouped = {e for r in records for e in r["evidence_ids"]}
    extra = {"projects": len(records), "excluded": len(outcome.excluded), "metric_prompts": prompts,
             "carried": carried, "new": len(assigned) - carried, "decisions": outcome.applied,
             "unassigned": sum(1 for item in evidence if item["id"] not in grouped)}
    errors = stages.commit(workspace, STAGE, inputs, extra=extra)
    if errors:
        for line in errors:
            print(line)
        print(f"commit of {STAGE} failed; previous output left in place", file=sys.stderr)
        return 1
    print(f"committed {STAGE}: {plural(len(records), 'project')} ({len(outcome.excluded)} excluded), "
          f"metric prompts for {prompts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
