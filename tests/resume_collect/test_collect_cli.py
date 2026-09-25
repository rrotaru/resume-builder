"""The collect command lines end to end, on copies of the fixture workspace."""
import json
import os
import shutil
from datetime import datetime, timezone

import configure
import ingest_export
import ingest_git_log
import ingest_reviews
import link
import normalize_github
import normalize_gitlab
import normalize_jira
import pytest

from collect_samples import collecting, sample_repo, set_config, write_lines
from conftest import FIXTURE_WORKSPACE
from rcollect.common import NOTICE
from rcore import sources, stages, validation, wsio

FIXTURE_PATH = "/home/jordan/resume-workspace"


def ws_arg(workspace):
    return ["--workspace", str(workspace)]


def date_review(workspace, day="2025-07-15"):
    """Give the fixture review the modification date its saved raw line records."""
    moment = datetime.fromisoformat(f"{day}T12:00:00").replace(tzinfo=timezone.utc).timestamp()
    os.utime(workspace / "reviews" / "2025-H1.txt", (moment, moment))


def begin_raw(workspace):
    shutil.rmtree(workspace / "01-raw")
    return stages.begin(workspace, "01-raw")


# configure.py ----------------------------------------------------------------

def test_show(workspace, capsys):
    assert configure.main([*ws_arg(workspace), "show"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "time range: 2023-01-01 to open"
    assert out[1] == "github: connector, username jrivera"
    assert out[2] == "gitlab: not configured"
    assert out[3] == f"jira: export, username jordan.rivera, export exports/jira.csv -> {workspace.resolve()}" \
                     "/exports/jira.csv"
    assert out[4:8] == ["local repos: none", "git authors: none",
                        f"reviews folder: reviews -> {workspace.resolve()}/reviews",
                        f"resume: old-resume.pdf -> {workspace.resolve()}/old-resume.pdf"]
    assert out[-1] == "data notice: accepted at 2026-09-24T15:00:00Z"


def test_notice(workspace, capsys):
    set_config(workspace, data_notice_acknowledged_at=None)
    assert configure.main([*ws_arg(workspace), "notice"]) == 0
    assert capsys.readouterr().out.startswith(NOTICE + "\n\nnot accepted yet")
    assert wsio.read_json(workspace / "config.json")["data_notice_acknowledged_at"] is None
    assert configure.main([*ws_arg(workspace), "notice", "--accept"]) == 0
    stamp = wsio.read_json(workspace / "config.json")["data_notice_acknowledged_at"]
    assert capsys.readouterr().out == f"data notice accepted at {stamp}\n"
    assert datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
    assert configure.main([*ws_arg(workspace), "notice", "--accept"]) == 0
    assert capsys.readouterr().out == f"data notice already accepted at {stamp}\n"


def test_time_range(workspace, capsys):
    assert configure.main([*ws_arg(workspace), "time-range", "--start", "2022-01-01", "--end", "none"]) == 0
    assert wsio.read_json(workspace / "config.json")["time_range"] == {"start": "2022-01-01", "end": None}
    before = (workspace / "config.json").read_bytes()
    for start, end, message in (("2022-02-30", "none", "--start '2022-02-30' is not a real YYYY-MM-DD date"),
                                ("2022-W01-1", "none", "is not a real YYYY-MM-DD date"),
                                ("2024-01-01", "2023-01-01", "--start 2024-01-01 is after --end 2023-01-01")):
        assert configure.main([*ws_arg(workspace), "time-range", "--start", start, "--end", end]) == 1
        assert message in capsys.readouterr().err
    assert (workspace / "config.json").read_bytes() == before


def test_sources(workspace, tmp_path, capsys, monkeypatch):
    export = tmp_path / "gl.json"
    export.write_text("[]", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert configure.main([*ws_arg(workspace), "source", "gitlab", "--mode", "export", "--username", "jr",
                           "--export", "gl.json"]) == 0
    assert configure.main([*ws_arg(workspace), "source", "github", "--mode", "skip"]) == 0
    cfg = wsio.read_json(workspace / "config.json")
    assert [s["type"] for s in cfg["sources"]] == ["github", "jira", "gitlab"]
    assert cfg["sources"][0] == {"type": "github", "mode": "skip", "username": None, "export_path": None}
    assert cfg["sources"][2]["export_path"] == str(export.resolve())
    capsys.readouterr()
    for args, message in (
            (["github", "--mode", "connector"], "--mode connector needs --username"),
            (["jira", "--mode", "export", "--username", "x"], "--mode export needs --export PATH"),
            (["jira", "--mode", "export", "--username", "x", "--export", "missing.csv"], "missing.csv: not found"),
            (["jira", "--mode", "connector", "--username", "x", "--export", "gl.json"],
             "--export applies to --mode export only")):
        assert configure.main([*ws_arg(workspace), "source", *args]) == 1
        assert message in capsys.readouterr().err


def test_repos_authors_reviews_and_resume(workspace, tmp_path, capsys):
    sample_repo(tmp_path / "pay")
    assert configure.main([*ws_arg(workspace), "repos", str(tmp_path / "pay"), str(tmp_path / "pay")]) == 0
    assert configure.main([*ws_arg(workspace), "git-authors", "jordan@example.com", "Jordan Rivera"]) == 0
    assert configure.main([*ws_arg(workspace), "reviews", str(tmp_path / "pay")]) == 0
    assert configure.main([*ws_arg(workspace), "resume", str(tmp_path / "pay" / "books.py")]) == 0
    cfg = wsio.read_json(workspace / "config.json")
    assert cfg["local_repos"] == [str((tmp_path / "pay").resolve())]
    assert cfg["git_authors"] == ["jordan@example.com", "Jordan Rivera"]
    assert cfg["reviews_dir"] == str((tmp_path / "pay").resolve())
    assert cfg["resume_path"] == str((tmp_path / "pay" / "books.py").resolve())
    capsys.readouterr()
    for args, message in ((["repos", str(tmp_path)], "not a git work tree"),
                          (["git-authors", " "], "an empty git author identity"),
                          (["reviews", str(tmp_path / "nope")], "not an existing folder"),
                          (["resume", str(tmp_path)], "not an existing file")):
        assert configure.main([*ws_arg(workspace), *args]) == 1
        assert message in capsys.readouterr().err
    assert configure.main([*ws_arg(workspace), "repos"]) == 0
    assert configure.main([*ws_arg(workspace), "reviews", "none"]) == 0
    cfg = wsio.read_json(workspace / "config.json")
    assert cfg["local_repos"] == [] and cfg["reviews_dir"] is None


def test_configure_needs_a_valid_config(tmp_path, capsys):
    assert configure.main([*ws_arg(tmp_path), "show"]) == 1
    assert "run /resume-builder:init first" in capsys.readouterr().err


# The data notice and 01-raw.tmp ----------------------------------------------

SCRIPTS = [
    (ingest_export, ["--source", "jira"]), (ingest_git_log, []), (ingest_reviews, []),
    (normalize_github, []), (normalize_gitlab, []), (normalize_jira, []), (link, []),
]


@pytest.mark.parametrize("script, args", SCRIPTS, ids=lambda v: getattr(v, "__name__", ""))
def test_every_script_needs_the_notice(workspace, capsys, script, args):
    set_config(workspace, data_notice_acknowledged_at=None)
    before = sorted(p.name for p in workspace.iterdir())
    assert script.main([*ws_arg(workspace), *args]) == 1
    assert "the data notice has not been accepted" in capsys.readouterr().err
    assert sorted(p.name for p in workspace.iterdir()) == before


@pytest.mark.parametrize("script, args", SCRIPTS[:3], ids=lambda v: getattr(v, "__name__", ""))
def test_ingest_scripts_need_a_begun_raw_stage(workspace, tmp_path, capsys, script, args):
    sample_repo(tmp_path / "pay")
    set_config(workspace, local_repos=[str(tmp_path / "pay")], git_authors=["jordan@example.com"])
    assert script.main([*ws_arg(workspace), *args]) == 1
    assert "01-raw.tmp/ not found; run stage.py begin 01-raw first" in capsys.readouterr().err


# Ingest ----------------------------------------------------------------------

def test_ingest_export_writes_the_fixture_raw_file(workspace, capsys):
    tmp = begin_raw(workspace)
    assert ingest_export.main([*ws_arg(workspace), "--source", "jira"]) == 0
    assert capsys.readouterr().out.startswith(f"loaded 2 items from {workspace.resolve()}/exports/jira.csv")
    written = (tmp / "jira.jsonl").read_text(encoding="utf-8").replace(str(workspace.resolve()), FIXTURE_PATH)
    assert written == (FIXTURE_WORKSPACE / "01-raw" / "jira.jsonl").read_text(encoding="utf-8")
    assert ingest_export.main([*ws_arg(workspace), "--source", "github"]) == 1
    assert "github is not an export source" in capsys.readouterr().err


def test_ingest_git_log(workspace, tmp_path, capsys):
    shas = sample_repo(tmp_path / "pay")
    set_config(workspace, local_repos=[str(tmp_path / "pay")],
               git_authors=["jordan@example.com", "Jordan Rivera"])
    tmp = begin_raw(workspace)
    assert ingest_git_log.main(ws_arg(workspace)) == 0
    assert capsys.readouterr().out.splitlines() == [f"{tmp_path / 'pay'}: 3 commits",
                                                    "wrote 3 commits to 01-raw.tmp/git.jsonl"]
    lines = (tmp / "git.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["items"][0]["sha"] for line in lines] == [shas["feature"], shas["rename"],
                                                                       shas["first"]]
    set_config(workspace, git_authors=["nobody@example.com"])
    assert ingest_git_log.main(ws_arg(workspace)) == 3
    out = capsys.readouterr().out
    assert "most frequent authors there:" in out and out.endswith("never guess\n")
    assert (tmp / "git.jsonl").read_text() == ""
    set_config(workspace, git_authors=[])
    assert ingest_git_log.main(ws_arg(workspace)) == 1
    assert "no git author identities" in capsys.readouterr().err
    set_config(workspace, git_authors=["x@y.z"], local_repos=[str(tmp_path)])
    assert ingest_git_log.main(ws_arg(workspace)) == 1
    assert "not a git work tree" in capsys.readouterr().err


def test_ingest_reviews(workspace, capsys):
    date_review(workspace)
    (workspace / "reviews" / "notes.rtf").write_text("x", encoding="utf-8")
    (workspace / "reviews" / "scan.txt").write_text("Too short.", encoding="utf-8")
    tmp = begin_raw(workspace)
    assert ingest_reviews.main(ws_arg(workspace)) == 0
    assert capsys.readouterr().out.splitlines() == [
        "2025-H1.txt: 2025-07-15 (the file's modification date)",
        f"skipped scan.txt: no text found in {workspace.resolve()}/reviews/scan.txt. "
        "Provide another file, or paste the text.",
        "skipped notes.rtf: unsupported format; save it as PDF, DOCX, TXT or Markdown",
        f"wrote 1 review from {workspace.resolve()}/reviews to 01-raw.tmp/reviews.jsonl",
    ]
    written = (tmp / "reviews.jsonl").read_text(encoding="utf-8").replace(str(workspace.resolve()), FIXTURE_PATH)
    assert written == (FIXTURE_WORKSPACE / "01-raw" / "reviews.jsonl").read_text(encoding="utf-8")
    (workspace / "reviews" / "2025-H1.txt").unlink()
    assert ingest_reviews.main(ws_arg(workspace)) == 3
    assert "no review text found" in capsys.readouterr().out


# normalize_*.py ----------------------------------------------------------------

def test_normalize_reports_and_writes_nothing(workspace, capsys):
    before = sorted(str(p) for p in workspace.rglob("*"))
    assert normalize_jira.main(ws_arg(workspace)) == 0
    assert capsys.readouterr().out.splitlines() == [
        "jira: 2 items read from 01-raw/jira.jsonl, 1 kept (epic 1)", "  filtered: 1 not jordan.rivera's"]
    assert sorted(str(p) for p in workspace.rglob("*")) == before
    collecting(workspace)
    assert normalize_github.main(ws_arg(workspace)) == 0
    assert capsys.readouterr().out == ("github: 2 items read from 01-raw.tmp/github.jsonl, "
                                       "2 kept (pr 1, review 1)\n")


def test_normalize_exit_3_shows_queries_and_authors(workspace, capsys):
    set_config(workspace, sources=[{"type": "github", "mode": "connector", "username": "jriv",
                                    "export_path": None}])
    assert normalize_github.main(ws_arg(workspace)) == 3
    assert capsys.readouterr().out.splitlines() == [
        "github: 2 items read from 01-raw/github.jsonl, 0 kept",
        "  filtered: 2 not jriv's",
        "github: none of the items in 01-raw/github.jsonl belongs to 'jriv'",
        "  queries used:",
        "    is:pr author:jrivera created:>=2023-01-01",
        "    is:pr reviewed-by:jrivera -author:jrivera created:>=2023-01-01",
        "  most frequent authors seen: jrivera (1), mchen (1)",
        "  ask the engineer for another username or email, or check the time range; never guess",
    ]
    assert normalize_gitlab.main(ws_arg(workspace)) == 1
    assert "gitlab is not configured with a username" in capsys.readouterr().err


def test_normalize_raw_option(workspace, capsys):
    write_lines(workspace / "extra.jsonl", ["{bad", {"items": [{"key": "PAY-1"}]}])
    assert normalize_jira.main([*ws_arg(workspace), "--raw", "extra.jsonl"]) == 3
    out = capsys.readouterr().out.splitlines()
    assert out[:4] == ["jira: 1 item read from extra.jsonl, 0 kept", "  bad rows: 2",
                       "  extra.jsonl:1: invalid JSON: Expecting property name enclosed in double quotes",
                       '  extra.jsonl:2#/items/0: neither a Jira REST issue ("key", "fields") nor a CSV row '
                       '("Issue key")']
    assert out[4] == "jira: no items in extra.jsonl"
    assert normalize_jira.main([*ws_arg(workspace), "--raw", "missing.jsonl"]) == 1


# link.py -----------------------------------------------------------------------

def test_fixture_end_to_end(workspace, capsys):
    """From the Jira export, the review file and the saved GitHub pages to the fixture's evidence."""
    date_review(workspace)
    tmp = begin_raw(workspace)
    assert ingest_export.main([*ws_arg(workspace), "--source", "jira"]) == 0
    assert ingest_reviews.main(ws_arg(workspace)) == 0
    shutil.copy(FIXTURE_WORKSPACE / "01-raw" / "github.jsonl", tmp / "github.jsonl")
    capsys.readouterr()
    assert link.main(ws_arg(workspace)) == 0
    assert capsys.readouterr().out.splitlines() == [
        "github: 2 items read from 01-raw.tmp/github.jsonl, 2 kept (pr 1, review 1)",
        "jira: 2 items read from 01-raw.tmp/jira.jsonl, 1 kept (epic 1)",
        "  filtered: 1 not jordan.rivera's",
        "review: 1 item read from 01-raw.tmp/reviews.jsonl, 1 kept (perf_review 1)",
        "committed 01-raw",
        "removed 0 duplicates; 2 links",
        "committed 02-evidence: 4 items (github 2, jira 1, review 1)",
    ]
    evidence = workspace / "02-evidence" / "evidence.jsonl"
    assert evidence.read_bytes() == (FIXTURE_WORKSPACE / "02-evidence" / "evidence.jsonl").read_bytes()
    meta = wsio.read_json(workspace / "02-evidence" / "_stage.json")
    assert list(meta["inputs"]) == ["01-raw"]
    assert meta["extra"] == {"items": {"github": 2, "jira": 1, "review": 1}, "skipped_rows": 0,
                             "filtered": 1, "duplicates": 0}
    assert wsio.read_json(workspace / "01-raw" / "_stage.json")["inputs"] == {}
    assert not tmp.exists()
    status = stages.status(workspace)
    assert status["01-raw"] == status["02-evidence"] == "fresh"
    assert validation.validate_workspace(workspace) == []
    assert sources.check_file(workspace, "06-bullets/bullets.json") == []


def test_link_rebuilds_from_the_committed_raw(workspace, capsys):
    assert link.main(ws_arg(workspace)) == 0
    assert "committed 01-raw" not in capsys.readouterr().out
    assert (workspace / "02-evidence" / "evidence.jsonl").read_bytes() == (
        FIXTURE_WORKSPACE / "02-evidence" / "evidence.jsonl").read_bytes()


def test_link_drops_squash_commits_and_counts_bad_rows(workspace, capsys):
    tmp = collecting(workspace)
    set_config(workspace, local_repos=["/nowhere"], git_authors=["jordan@example.com"])
    squash = {"sha": "c" * 40, "repo": "/r", "remote": "github.com/northwind/ledger", "author_name": "J",
              "author_email": "jordan@example.com", "authored_at": "2025-03-11T09:30:00Z",
              "message": "PAY-42: Add Redis idempotency cache (#101)", "files": 23, "additions": 812,
              "deletions": 140}
    own = {**squash, "sha": "d" * 40, "message": "Tune cache TTL for PAY-42",
           "authored_at": "2025-03-20T00:00:00Z"}
    write_lines(tmp / "git.jsonl", [{"items": [squash]}, {"items": [own]}, "not json"])
    assert link.main(ws_arg(workspace)) == 0
    out = capsys.readouterr().out
    assert "  01-raw.tmp/git.jsonl:3: invalid JSON: Expecting value" in out
    assert "removed 1 duplicate; 3 links" in out
    records = wsio.read_jsonl(workspace / "02-evidence" / "evidence.jsonl")
    commits = [r for r in records if r["source"] == "git"]
    assert [c["native_key"] for c in commits] == ["d" * 40]
    assert commits[0]["links"] == ["ev_99a74656"]
    assert commits[0]["url"] == f"https://github.com/northwind/ledger/commit/{'d' * 40}"
    meta = wsio.read_json(workspace / "02-evidence" / "_stage.json")
    assert meta["extra"]["skipped_rows"] == 1 and meta["extra"]["duplicates"] == 1


@pytest.mark.parametrize("change, expected", [
    (lambda ws: (ws / "01-raw.tmp" / "github.jsonl").rename(ws / "01-raw.tmp" / "github.partial.jsonl"),
     "01-raw.tmp/github.partial.jsonl: an unfinished fetch"),
    (lambda ws: (ws / "01-raw.tmp" / "jira.jsonl").unlink(),
     "jira is configured (export) but 01-raw.tmp/jira.jsonl is missing; run ingest_export.py --source jira"),
    (lambda ws: write_lines(ws / "01-raw.tmp" / "gitlab.jsonl", []),
     "01-raw.tmp/gitlab.jsonl exists but gitlab is not configured"),
    (lambda ws: set_config(ws, sources=[{"type": "github", "mode": "skip", "username": None, "export_path": None},
                                        {"type": "jira", "mode": "export", "username": "jordan.rivera",
                                         "export_path": "exports/jira.csv"}]),
     "01-raw.tmp/github.jsonl exists but github is set to skip"),
    (lambda ws: write_lines(ws / "01-raw.tmp" / "git.jsonl", []),
     "01-raw.tmp/git.jsonl exists but local_repos is not set"),
    (lambda ws: set_config(ws, local_repos=["/r"]), "local_repos is set but 01-raw.tmp/git.jsonl is missing"),
    (lambda ws: set_config(ws, reviews_dir=None), "01-raw.tmp/reviews.jsonl exists but reviews_dir is not set"),
])
def test_link_refuses_raw_data_that_does_not_match_the_config(workspace, capsys, change, expected):
    collecting(workspace)
    change(workspace)
    before = (workspace / "02-evidence" / "evidence.jsonl").read_bytes()
    assert link.main(ws_arg(workspace)) == 1
    err = capsys.readouterr().err
    assert f"error: {expected}" in err and err.endswith("02-evidence not committed\n")
    assert (workspace / "02-evidence" / "evidence.jsonl").read_bytes() == before
    assert (workspace / "01-raw.tmp").is_dir() and not (workspace / "01-raw").exists()


def test_link_warns_about_other_files_and_needs_raw_data(workspace, capsys):
    (workspace / "01-raw" / "notes.txt").write_text("x", encoding="utf-8")
    assert link.main(ws_arg(workspace)) == 0
    assert "warning: 01-raw/notes.txt: not a raw source file; ignored" in capsys.readouterr().out
    shutil.rmtree(workspace / "01-raw")
    assert link.main(ws_arg(workspace)) == 1
    assert "no raw data in 01-raw/ or 01-raw.tmp/" in capsys.readouterr().err
