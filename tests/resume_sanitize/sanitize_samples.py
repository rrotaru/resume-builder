"""Helpers for the resume-sanitize tests: small made-up workspaces."""
from __future__ import annotations

import json
from pathlib import Path

from rcore import config, wsio


def eid(n: int) -> str:
    return f"ev_{n:08x}"


def item(n: int, title: str, excerpt: str = "", kind: str = "pr", raw_ref: str | None = None) -> dict:
    """One evidence item; a perf_review is a performance review."""
    source = "review" if kind == "perf_review" else "github"
    return {"id": eid(n), "source": source, "kind": kind, "native_key": f"northwind/ledger#{n}", "url": None,
            "title": title, "excerpt": excerpt, "engineer_role": "subject" if kind == "perf_review" else "author",
            "created_at": f"2025-01-{n:02d}T00:00:00Z", "closed_at": None, "state": None, "labels": [], "links": [],
            "raw_ref": raw_ref}


def project(pid: str, evidence: list[int], name: str = "Ledger export", summary: str = "Made exports reliable.",
            rank: int = 1, reasons=("authored 3 of 4 pull requests",)) -> dict:
    return {"id": pid, "internal_name": name, "summary": summary, "evidence_ids": sorted(eid(n) for n in evidence),
            "role": "core", "scope": "team", "start": "2025-01", "end": "2025-01", "rank": rank,
            "rank_reasons": list(reasons), "metric_prompt": rank <= 3}


def term(name: str, replacement: str | None, kind: str = "codename") -> dict:
    return {"term": name, "replacement": replacement, "kind": kind}


def make_workspace(root: Path, projects=(), evidence=(), profile: dict | None = None, terms=(),
                   raw: dict | None = None, bullets=None, stories: str | None = None,
                   candidates=None) -> Path:
    """A workspace holding whichever of these files are given (decisions/terms.json always)."""
    ws = root / "ws"
    wsio.write_json(ws / "config.json", config.default_config("Senior Backend Engineer"))
    wsio.write_json(ws / "decisions" / "terms.json", list(terms))
    if projects:
        wsio.write_json(ws / "04-projects" / "projects.json", list(projects))
    if evidence:
        wsio.write_jsonl(ws / "02-evidence" / "evidence.jsonl", list(evidence))
    if profile is not None:
        wsio.write_json(ws / "03-profile" / "profile.json", profile)
    for name, pages in (raw or {}).items():
        path = ws / "01-raw" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(page) + "\n" for page in pages), encoding="utf-8")
    if bullets is not None:
        wsio.write_json(ws / "06-bullets" / "bullets.json", bullets)
    if stories is not None:
        (ws / "06-bullets").mkdir(parents=True, exist_ok=True)
        (ws / "06-bullets" / "stories.md").write_text(stories, encoding="utf-8")
    if candidates is not None:
        wsio.write_json(ws / "05-terms" / "candidates.json", candidates)
    return ws


def bullet(n: int, text: str, project_id: str | None = None) -> dict:
    return {"id": f"b_{n}", "project_id": project_id, "work_ref": None if project_id else 0, "text": text,
            "form": "xyz", "sources": [eid(1)]}


def proposal(name: str, replacement: str = "a generic name", kind: str = "codename") -> dict:
    return {"term": name, "kind": kind, "proposed_replacement": replacement}
