"""Helpers for the resume-write tests: a small made-up workspace and its bullets and stories.

The workspace has two projects: pj_0000000a (rank 1, a story, metric m_1 of
40%, items 1 and 2, 2025-02 to 2025-05) and pj_0000000b (rank 2, item 3,
2025-06). Item 4 is in no project, item 5 is a performance review whose full
text is in 01-raw/reviews.jsonl. The profile has two jobs (/work/0 from
2023-01, ongoing; /work/1 2019-06 to 2022-12 with one highlight) and a profile
project with a description.
"""
from __future__ import annotations

import json
from pathlib import Path

from rcore import config, wsio

PA, PB = "pj_0000000a", "pj_0000000b"
REVIEW_TEXT = "2025 H1 review\n\nJordan led the cache work and cut on-call pages by 30%.\n"


def eid(n: int) -> str:
    return f"ev_{n:08x}"


def item(n: int, title: str, excerpt: str = "", kind: str = "pr", created: str = "2025-03-01",
         raw_ref: str | None = None) -> dict:
    review = kind == "perf_review"
    return {"id": eid(n), "source": "review" if review else "github", "kind": kind,
            "native_key": f"northwind/ledger#{n}", "url": None, "title": title, "excerpt": excerpt,
            "engineer_role": "subject" if review else "author", "created_at": f"{created}T00:00:00Z",
            "closed_at": None, "state": None, "labels": [], "links": [], "raw_ref": raw_ref}


def project(pid: str, evidence, name: str, rank: int, start: str, end: str, prompt: bool) -> dict:
    return {"id": pid, "internal_name": name, "summary": f"{name}.", "evidence_ids": sorted(eid(n) for n in evidence),
            "role": "lead", "scope": "team", "start": start, "end": end, "rank": rank,
            "rank_reasons": ["authored the core PR"], "metric_prompt": prompt}


def metric(mid: str, pid: str, value, statement: str, evidence=()) -> dict:
    return {"id": mid, "project_id": pid, "value": value, "unit": "%", "statement": statement,
            "evidence_ids": sorted(eid(n) for n in evidence)}


EVIDENCE = [
    item(1, "Checkout latency", "Reduce p99 checkout latency.", kind="epic", created="2025-02-10"),
    item(2, "Add idempotency cache", "Cache in front of checkout in 3 regions.", created="2025-03-04"),
    item(3, "Fix export retries", "Retries ledger exports.", created="2025-06-02"),
    item(4, "Bump dependencies", "Routine bump to 12 packages.", created="2025-06-20"),
    item(5, "2025 H1 review", "Jordan led the cache work.", kind="perf_review", created="2025-07-15",
         raw_ref="01-raw/reviews.jsonl:1#/items/0"),
]
PROJECTS = [project(PA, [1, 2], "Checkout latency", 1, "2025-02", "2025-05", True),
            project(PB, [3], "Ledger export retries", 2, "2025-06", "2025-06", False)]
PROFILE = {
    "basics": {"name": "Jordan Rivera"},
    "work": [{"name": "Northwind", "position": "Senior Engineer", "startDate": "2023-01", "highlights": [],
              "x-lines": {"first": 3, "last": 4}},
             {"name": "Tailspin", "position": "Engineer", "startDate": "2019-06", "endDate": "2022-12",
              "highlights": ["Migrated the order service to Go, serving 2M requests per day"],
              "x-lines": {"first": 5, "last": 7}}],
    "projects": [{"name": "ledger-lint", "startDate": "2021-04",
                  "description": "Linter for ledger files; 300 GitHub stars", "x-lines": {"first": 9, "last": 10}}],
}
METRICS = [metric("m_1", PA, 40, "p99 checkout latency reduced 40%", [1, 2])]
STORIES = ("# Stories\n\n## Checkout latency\n\n"
           "- **Situation:** Checkout missed its p99 latency target.\n"
           "- **Task:** Jordan led the fix.\n"
           "- **Action:** Built an idempotency cache in 3 regions.\n"
           "- **Result:** p99 checkout latency fell 40%.\n")


def bullet(text: str, sources, project_id: str | None = None, work_ref: int | None = None,
           form: str = "xyz") -> dict:
    return {"project_id": project_id, "work_ref": work_ref, "text": text, "form": form, "sources": list(sources)}


def good_bullets() -> list[dict]:
    """A draft that passes every check for the sample workspace."""
    return [
        bullet("Cut p99 checkout latency 40% by building an idempotency cache", [eid(2), eid(1), "metric:m_1"],
               PA, 0, "xyz_quantified"),
        bullet("Made ledger exports retry on failure", [eid(3)], PB, 0),
        bullet("Cut on-call pages by 30% as lead of the cache work", [eid(5)], None, 0),
        bullet("Migrated the order service to Go, serving 2M requests per day", ["resume:/work/1/highlights/0"],
               None, 1),
        bullet("Built ledger-lint, a linter for ledger files with 300 GitHub stars",
               ["resume:/projects/0/description"]),
    ]


def make_workspace(root: Path, projects=PROJECTS, evidence=EVIDENCE, profile=PROFILE, wizard=None,
                   metrics=METRICS, review_text: str | None = REVIEW_TEXT) -> Path:
    """A workspace with these inputs; None leaves a file out."""
    ws = root / "ws"
    wsio.write_json(ws / "config.json", config.default_config("Senior Backend Engineer"))
    wsio.write_json(ws / "decisions" / "terms.json", [])
    if projects is not None:
        wsio.write_json(ws / "04-projects" / "projects.json", list(projects))
    if evidence is not None:
        wsio.write_jsonl(ws / "02-evidence" / "evidence.jsonl", list(evidence))
    if profile is not None:
        wsio.write_json(ws / "03-profile" / "profile.json", profile)
    if wizard is not None:
        wsio.write_json(ws / "decisions" / "profile.json", wizard)
    if metrics is not None:
        wsio.write_json(ws / "decisions" / "metrics.json", list(metrics))
    if review_text is not None:
        (ws / "01-raw").mkdir(parents=True, exist_ok=True)
        (ws / "01-raw" / "reviews.jsonl").write_text(json.dumps({"items": [{"text": review_text}]}) + "\n",
                                                    encoding="utf-8")
    return ws


def draft(ws: Path, bullets=None, stories: str | None = STORIES) -> None:
    """Write the model's draft into 06-bullets.tmp/."""
    wsio.write_json(ws / "06-bullets.tmp" / "bullets.json", good_bullets() if bullets is None else bullets)
    if stories is not None:
        (ws / "06-bullets.tmp" / "stories.md").write_text(stories, encoding="utf-8")
