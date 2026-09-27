"""Helpers for the resume-build tests: a first run from an empty workspace, step by step.

The fixture's files stand in for the engineer's sources and the model's output,
and every decision is recorded through the scripts, so each stage the run
commits equals the fixture's saved one.
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
from pathlib import Path

import answer
import apply
import attest
import ats
import check_profile
import configure
import decide
import extract_text
import ingest_export
import ingest_reviews
import link
import match_projects
import pytest
import scan
import signals
import write
from conftest import FIXTURE_WORKSPACE
from rats import material
from rbuild import common, steps
from rcore import stages, workspace as rworkspace, wsio

FALCON = "pj_da2a2b53"
MONTH = (2026, 9)
TODAY = datetime.date(2026, 9, 27)
NOW = "2026-09-27T12:00:00Z"
ROLE = "Senior Backend Engineer"
GENERAL_KEYWORDS = ["Go", "Python", "Redis", "PostgreSQL", "metrics", "Kubernetes"]
JOB_KEYWORDS = ["Go", "Redis", "PostgreSQL", "SLO compliance", "on-call", "metrics", "Kubernetes",
                "incident response"]
B1_GENERAL = ("Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency cache "
              "in Go")
B1_JOB = B1_GENERAL + ", raising checkout SLO compliance"
B1_SANITIZED = ("Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency cache "
                "for real-time fraud-detection platform in Go")
# The engineer's checkpoint 3 answers, as the wizard records them.
WIZARD_ANSWERS = [
    ["term", "Project Falcon", "--replacement", "real-time fraud-detection platform"],
    ["term", "Contoso Bank", "--replacement", "a top-10 US bank"],
    ["term", "Go", "--allow", "--kind", "other"],
    ["profile", "/basics/email", "jordan.rivera@example.com"],
    ["skip", "profile:/basics/phone"],
    ["profile", "/basics/location/city", "Denver"],
    ["profile", "/basics/location/region", "CO"],
    ["profile", "/certificates/-/name", "AWS Certified Solutions Architect - Associate"],
    ["profile", "/certificates/0/issuer", "Amazon Web Services"],
    ["profile", "/certificates/0/date", "2024-05"],
    ["metric", FALCON, "--value", "40", "--unit", "%", "--statement", "p99 checkout latency reduced 40%"],
]


def ws_arg(workspace) -> list[str]:
    return ["--workspace", str(workspace)]


def fix_time(monkeypatch) -> None:
    """Fix today, the stage commit time and the month resume-ats counts experience to."""
    monkeypatch.setattr(common, "today", lambda: TODAY)
    monkeypatch.setattr(stages, "_now", lambda: NOW)
    monkeypatch.setattr(material, "current_month", lambda: MONTH)


def fixture(rel: str) -> Path:
    return FIXTURE_WORKSPACE / rel


def same_as_fixture(workspace, rel: str) -> bool:
    return (Path(workspace) / rel).read_bytes() == fixture(rel).read_bytes()


def next_line(workspace) -> str:
    return steps.next_step(steps.survey(workspace))


def states(workspace) -> dict[str, str]:
    return {step.name: step.state for step in steps.survey(workspace)}


def run(module, workspace, *args) -> int:
    return module.main([*ws_arg(workspace), *map(str, args)])


def edit_json(path: Path, change) -> None:
    data = wsio.read_json(path)
    change(data)
    wsio.write_json(path, data)


def set_text(resume: dict, section: str, entry: int, index: int, text: str) -> None:
    resume[section][entry]["x-highlights"][index]["text"] = text


def without(records: list[dict], *keys: str) -> list[dict]:
    return [{k: v for k, v in r.items() if k not in keys} for r in records]


# The steps of a first run -----------------------------------------------------------------

def sources(root: Path) -> Path:
    """The engineer's own files, outside the workspace: an export, a review, the old resume and a posting."""
    folder = root / "engineer"
    (folder / "reviews").mkdir(parents=True)
    shutil.copy(fixture("exports/jira.csv"), folder / "jira.csv")
    shutil.copy(fixture("reviews/2025-H1.txt"), folder / "reviews" / "2025-H1.txt")
    shutil.copy(fixture("03-profile/resume.txt"), folder / "resume.txt")
    shutil.copy(fixture("08-ats/jobs/fintech-sre/jd.txt"), folder / "fintech-sre.txt")
    moment = datetime.datetime(2025, 7, 15, 12, tzinfo=datetime.timezone.utc).timestamp()
    os.utime(folder / "reviews" / "2025-H1.txt", (moment, moment))  # the date the saved review line records
    return folder


def configure_sources(workspace: Path, engineer: Path) -> None:
    """Checkpoint 1: the data notice and the sources, recorded with configure.py."""
    for args in (["notice", "--accept"], ["time-range", "--start", "2023-01-01", "--end", "none"],
                 ["source", "github", "--mode", "connector", "--username", "jrivera"],
                 ["source", "jira", "--mode", "export", "--username", "jordan.rivera", "--export",
                  engineer / "jira.csv"],
                 ["reviews", engineer / "reviews"], ["resume", engineer / "resume.txt"]):
        assert run(configure, workspace, *args) == 0


def fetch(workspace: Path) -> None:
    """The collection in 01-raw.tmp/: the connector's saved pages, the export and the reviews."""
    tmp = stages.begin(workspace, "01-raw")
    shutil.copy(fixture("01-raw/github.jsonl"), tmp / "github.jsonl")
    assert run(ingest_export, workspace, "--source", "jira") == 0
    assert run(ingest_reviews, workspace) == 0


def groups_draft() -> list[dict]:
    """The fixture's groups as the model wrote them: without IDs."""
    return without(wsio.read_json(fixture("04-projects/groups.json")), "id")


def write_keywords(workspace: Path, version: str, keywords: list[str]) -> None:
    folder = "general" if version == "general" else f"jobs/{version}"
    (Path(workspace) / "08-ats.tmp" / folder / "keywords.json").write_text(
        json.dumps(keywords, indent=2) + "\n", encoding="utf-8")


def draft_path(workspace: Path, version: str = "general") -> Path:
    folder = "general" if version == "general" else f"jobs/{version}"
    return Path(workspace) / "08-ats.tmp" / folder / "resume.json"


def first_run(root: Path, check=lambda label: None) -> Path:
    """A whole first run in root/ws, the engineer's files in root/engineer. check(label) runs after each step."""
    workspace, engineer = root / "ws", sources(root)
    check("start")
    rworkspace.init_workspace(workspace, ROLE)
    check("init")
    configure_sources(workspace, engineer)
    fetch(workspace)
    check("fetched")
    assert run(link, workspace) == 0
    check("collected")
    assert run(extract_text, workspace) == 0
    check("extracted")
    wsio.write_json(workspace / "03-profile.tmp" / "profile.json", wsio.read_json(fixture("03-profile/profile.json")))
    check("mapped")
    assert run(check_profile, workspace, "--commit") == 0
    check("imported")
    assert run(signals, workspace) == 0
    check("signals")
    wsio.write_json(workspace / "04-projects.tmp" / "groups.json", groups_draft())
    check("grouped")
    assert run(match_projects, workspace) == 0
    assert run(decide, workspace, "set-role", FALCON, "lead") == 0  # checkpoint 2
    assert run(match_projects, workspace, "--commit") == 0
    check("analyzed")
    assert run(scan, workspace) == 0
    wsio.write_json(workspace / "05-terms.tmp" / "candidates.json",
                    without(wsio.read_json(fixture("05-terms/candidates.json")), "found_in"))
    check("candidates")
    assert run(scan, workspace, "--commit") == 0
    check("scanned")
    for args in WIZARD_ANSWERS:  # checkpoint 3
        assert run(answer, workspace, *args) == 0, args
    check("wizard")
    assert run(write, workspace) == 0
    wsio.write_json(workspace / "06-bullets.tmp" / "bullets.json",
                    without(wsio.read_json(fixture("06-bullets/bullets.json")), "id"))
    shutil.copy(fixture("06-bullets/stories.md"), workspace / "06-bullets.tmp" / "stories.md")
    check("bullets")
    assert run(write, workspace, "--commit") == 0
    check("written")
    assert run(apply, workspace) == 0
    wsio.write_json(workspace / "07-sanitized.tmp" / "new-terms.json", [])
    check("new terms")
    assert run(apply, workspace, "--commit") == 0
    check("applied")
    assert run(ats, workspace) == 0
    write_keywords(workspace, "general", GENERAL_KEYWORDS)
    edit_json(draft_path(workspace), lambda r: set_text(r, "work", 0, 0, B1_GENERAL))
    check("general drafted")
    assert run(ats, workspace, "--commit") == 0
    check("general")
    assert run(ats, workspace, "--jd", engineer / "fintech-sre.txt") == 0
    write_keywords(workspace, "fintech-sre", JOB_KEYWORDS)
    edit_json(draft_path(workspace, "fintech-sre"), lambda r: set_text(r, "work", 0, 0, B1_JOB))
    assert run(ats, workspace, "--commit") == 0
    check("job")
    assert run(attest, workspace, "accept", "fintech-sre", "b_1") == 0  # checkpoint 4
    check("attested")
    return workspace


# A first run, built once per test module and copied for each test ----------------------------

def build_once(tmp_path_factory) -> Path:
    """The root of a first run (root/ws, root/engineer), for a module-scoped fixture."""
    with pytest.MonkeyPatch.context() as patch:
        fix_time(patch)
        root = tmp_path_factory.mktemp("first-run")
        first_run(root)
    return root


def copy_of(root: Path, tmp_path: Path, monkeypatch) -> Path:
    """A copy of a first run's workspace. Its config.json still names the run's engineer/ files: leave them as they
    are."""
    fix_time(monkeypatch)
    shutil.copytree(root / "ws", tmp_path / "ws")
    return tmp_path / "ws"


def survey(workspace) -> dict:
    """Each step by name."""
    return {step.name: step for step in steps.survey(workspace)}
