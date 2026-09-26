"""Helpers for the resume-wizard tests: small made-up workspaces."""
from __future__ import annotations

import copy
from pathlib import Path

from rcore import wsio

NORTHWIND = {"name": "Northwind Payments", "position": "Senior Software Engineer", "startDate": "2023-01"}
TAILSPIN = {"name": "Tailspin Toys", "position": "Software Engineer", "startDate": "2019-06", "endDate": "2022-12"}
CONTOSO = {"name": "Contoso", "position": "Engineer", "startDate": "2018-01", "endDate": "2019-05"}
COMPLETE_BASICS = {"name": "Jordan Rivera", "email": "j@example.com", "phone": "555-0100",
                   "location": {"city": "Denver"}, "url": "https://jr.dev"}
SCHOOL = {"institution": "State University", "studyType": "BS", "area": "Computer Science", "endDate": "2019"}
CERT = {"name": "CKA", "issuer": "CNCF", "date": "2024"}


def complete_profile(**changes) -> dict:
    """An imported profile the wizard has nothing to ask about."""
    doc = {"basics": COMPLETE_BASICS, "work": [NORTHWIND, TAILSPIN], "education": [SCHOOL], "certificates": [CERT]}
    doc.update(changes)
    return copy.deepcopy(doc)


def project(pid: str, rank: int = 1, prompt: bool = True, evidence=("ev_00000001",), name: str | None = None) -> dict:
    return {"id": pid, "internal_name": name or f"Project {rank}", "summary": "Made exports reliable.",
            "evidence_ids": sorted(evidence), "role": "core", "scope": "team", "start": "2025-01", "end": "2025-03",
            "rank": rank, "rank_reasons": ["authored 3 of 4 pull requests"], "metric_prompt": prompt}


def metric(mid: str, pid: str, value=40, statement: str = "latency cut 40%", evidence=None) -> dict:
    record = {"id": mid, "project_id": pid, "value": value, "unit": "%", "statement": statement}
    if evidence is not None:
        record["evidence_ids"] = sorted(evidence)
    return record


def candidate(term: str, replacement: str = "a generic name", kind: str = "codename", found=("pj_0000000a",)):
    return {"term": term, "kind": kind, "proposed_replacement": replacement, "found_in": list(found)}


def make_workspace(root: Path, imported: dict | None = None, wizard: dict | None = None, state: dict | None = None,
                   terms=(), metrics=(), projects=None, decisions=(), candidates=None, new_terms=None,
                   source_format: str | None = None) -> Path:
    """A workspace with decisions/ and whichever other files are given."""
    ws = root / "ws"
    wsio.write_json(ws / "decisions" / "terms.json", list(terms))
    wsio.write_json(ws / "decisions" / "metrics.json", list(metrics))
    wsio.write_json(ws / "decisions" / "projects.json", list(decisions))
    wsio.write_json(ws / "decisions" / "profile.json", wizard or {})
    if state is not None:
        wsio.write_json(ws / "decisions" / "wizard.json", state)
    if imported is not None:
        wsio.write_json(ws / "03-profile" / "profile.json", imported)
    if source_format is not None:
        wsio.write_json(ws / "03-profile" / "source.json",
                        {"path": "/r.json", "format": source_format, "sha256": "sha256:" + "0" * 64,
                         "text_sha256": None})
    if projects is not None:
        wsio.write_json(ws / "04-projects" / "projects.json", list(projects))
    if candidates is not None:
        wsio.write_json(ws / "05-terms" / "candidates.json", list(candidates))
    if new_terms is not None:
        wsio.write_json(ws / "07-sanitized" / "new-terms.json", list(new_terms))
    return ws


def snapshot(ws: Path) -> dict:
    """The bytes of every file under decisions/, to check that nothing changed."""
    return {p.name: p.read_bytes() for p in sorted((ws / "decisions").iterdir()) if p.is_file()}
