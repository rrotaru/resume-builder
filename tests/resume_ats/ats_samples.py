"""Helpers for the resume-ats tests: the fixture workspace with the month fixed, and the fixture's ats flow.

The fixture's 08-ats/ was built on 2026-09 (88 months of experience), so the
tests fix the current month there.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from conftest import FIXTURE_WORKSPACE
from rats import common, material
from rcore import wsio

MONTH = (2026, 9)
GENERAL_KEYWORDS = ["Go", "Python", "Redis", "PostgreSQL", "metrics", "Kubernetes"]
JOB_KEYWORDS = ["Go", "Redis", "PostgreSQL", "SLO compliance", "on-call", "metrics", "Kubernetes",
                "incident response"]
B1_GENERAL = ("Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency cache "
              "in Go")
B1_JOB = B1_GENERAL + ", raising checkout SLO compliance"
B1_SANITIZED = ("Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency cache "
                "for real-time fraud-detection platform in Go")


def fix_month(monkeypatch, month=MONTH):
    monkeypatch.setattr(material, "current_month", lambda: month)


def ws_arg(workspace) -> list[str]:
    return ["--workspace", str(workspace)]


def build(workspace):
    return material.build(workspace, common.load_inputs(workspace))


def edit(path: Path, change) -> None:
    data = wsio.read_json(path)
    change(data)
    wsio.write_json(path, data)


def set_text(resume: dict, section: str, entry: int, index: int, text: str) -> None:
    resume[section][entry]["x-highlights"][index]["text"] = text


def write_keywords(workspace, version: str, keywords) -> None:
    folder = "general" if version == "general" else f"jobs/{version}"
    path = Path(workspace) / "08-ats.tmp" / folder / "keywords.json"
    path.write_text(json.dumps(keywords, indent=2) + "\n", encoding="utf-8")


def posting(tmp_path: Path, name: str = "fintech-sre.txt") -> Path:
    """A copy of the fixture's posting outside the workspace."""
    path = tmp_path / name
    shutil.copy(FIXTURE_WORKSPACE / "08-ats" / "jobs" / "fintech-sre" / "jd.txt", path)
    return path


def draft_resume(workspace, version: str = "general") -> dict:
    folder = "general" if version == "general" else f"jobs/{version}"
    return wsio.read_json(Path(workspace) / "08-ats.tmp" / folder / "resume.json")


def resume_path(workspace, version: str = "general") -> Path:
    folder = "general" if version == "general" else f"jobs/{version}"
    return Path(workspace) / "08-ats.tmp" / folder / "resume.json"
