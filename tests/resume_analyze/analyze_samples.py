"""Helpers for the resume-analyze tests: made-up evidence items, groups and small workspaces."""
from __future__ import annotations

import json
from pathlib import Path

from rcore import config, wsio


def eid(n: int) -> str:
    """A valid evidence ID for a small number: ev_00000001."""
    return f"ev_{n:08x}"


def item(n: int, kind: str = "pr", source: str | None = None, role: str | None = None,
         created: str = "2025-01-01T00:00:00Z", closed: str | None = None, links=(), key: str | None = None,
         title: str | None = None, stats: dict | None = None, raw_ref: str | None = None) -> dict:
    """One evidence item. Defaults follow the kind: a pr is authored on GitHub, a ticket assigned in Jira."""
    source = source or {"ticket": "jira", "epic": "jira", "commit": "git", "perf_review": "review"}.get(kind, "github")
    role = role or {"review": "reviewer", "ticket": "assignee", "epic": "assignee",
                    "perf_review": "subject"}.get(kind, "author")
    key = key or {"jira": f"PAY-{n}", "git": f"{n:040x}", "review": f"review-{n}",
                  "gitlab": f"group/app!{n}"}.get(source, f"northwind/ledger#{n}")
    record = {"id": eid(n), "source": source, "kind": kind, "native_key": key, "url": None,
              "title": title or f"{kind} {n}", "excerpt": "", "engineer_role": role, "created_at": created,
              "closed_at": closed, "state": None, "labels": [], "links": [eid(m) for m in links],
              "raw_ref": raw_ref}
    if stats is not None:
        record["stats"] = stats
    return record


def group(numbers, rank: int = 1, name: str | None = None, **fields) -> dict:
    """One group of the model's draft, holding the items with those numbers."""
    return {"internal_name": name or f"project {rank}", "summary": "A made-up project.",
            "evidence_ids": [eid(n) for n in numbers], "role": "core", "scope": "team", "rank": rank,
            "rank_reasons": [f"reason {rank}"], **fields}


def make_workspace(root: Path, evidence: list[dict], raw: dict | None = None, **cfg_changes) -> Path:
    """A workspace with config.json (GitHub jrivera, GitLab jr, Jira jordan.rivera), evidence and raw files."""
    ws = root / "ws"
    cfg = config.default_config("Senior Backend Engineer")
    cfg["sources"] = [{"type": "github", "mode": "connector", "username": "jrivera", "export_path": None},
                      {"type": "gitlab", "mode": "connector", "username": "jr", "export_path": None},
                      {"type": "jira", "mode": "connector", "username": "jordan.rivera", "export_path": None}]
    cfg.update(cfg_changes)
    wsio.write_json(ws / "config.json", cfg)
    wsio.write_jsonl(ws / "02-evidence" / "evidence.jsonl", evidence)
    (ws / "decisions").mkdir(parents=True, exist_ok=True)
    for name, pages in (raw or {}).items():
        path = ws / "01-raw" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(page) + "\n" for page in pages), encoding="utf-8")
    return ws


def write_draft(ws: Path, groups: list[dict]) -> None:
    wsio.write_json(ws / "04-projects.tmp" / "groups.json", groups)


def write_decisions(ws: Path, decisions: list[dict]) -> None:
    wsio.write_json(ws / "decisions" / "projects.json", decisions)
