"""Local git repositories: reading the engineer's commits and normalizing them."""
import pytest

from rcollect import git
from rcollect.common import CollectError, Page
from collect_samples import OPEN, sample_repo

AUTHORS = ["jordan@example.com", "jordan rivera"]
SINCE_2023 = {"start": "2023-01-01", "end": None}


@pytest.mark.parametrize("url, expected", [
    ("git@github.com:acme/pay.git", "github.com/acme/pay"),
    ("https://github.com/acme/pay.git", "github.com/acme/pay"),
    ("https://user:token@GitLab.com/grp/sub/proj/", "gitlab.com/grp/sub/proj"),
    ("ssh://git@git.example.com:2222/grp/proj.git", "git.example.com/grp/proj"),
    ("/srv/repos/pay.git", None),
    ("file:///srv/repos/pay.git", None),
    ("", None),
])
def test_remote_path(url, expected):
    assert git.remote_path(url) == expected


def test_matches_email_or_name_exactly():
    assert git.matches("Anyone", "JORDAN@example.com", AUTHORS)
    assert git.matches("Jordan RIVERA", "other@x.test", AUTHORS)
    assert not git.matches("Jordan Rivera Jr", "xjordan@example.com", AUTHORS)


def test_read_repo_keeps_the_engineers_commits_in_range(tmp_path):
    shas = sample_repo(tmp_path / "pay")
    commits, notes = git.read_repo(tmp_path / "pay", AUTHORS, SINCE_2023)
    assert notes == []
    assert [c["sha"] for c in commits] == [shas["feature"], shas["rename"], shas["first"]]
    first = commits[-1]
    assert first["authored_at"] == "2022-12-31T23:00:00-02:00"
    assert first["message"] == "Add ledger\n\nBody for PAY-42."
    assert (first["files"], first["additions"], first["deletions"]) == (2, 3, 0)
    assert first["remote"] == "github.com/acme/pay" and first["repo"] == str(tmp_path / "pay")
    everything, _ = git.read_repo(tmp_path / "pay", AUTHORS, OPEN)
    assert shas["old"] in [c["sha"] for c in everything]
    assert shas["merge"] not in [c["sha"] for c in everything]


def test_read_repo_reports_no_match_with_frequent_authors(tmp_path):
    sample_repo(tmp_path / "pay")
    commits, notes = git.read_repo(tmp_path / "pay", ["nobody@example.com"], OPEN)
    assert commits == []
    assert notes[0].startswith(f"{tmp_path / 'pay'}: no commits by nobody@example.com in the time range (git log")
    assert "M. Chen <mchen@example.com> (1)" in notes[1]


def test_read_repo_refuses_a_folder_that_is_not_a_repository(tmp_path):
    with pytest.raises(CollectError, match="not a git work tree"):
        git.read_repo(tmp_path, AUTHORS, OPEN)


def test_normalize_commits(tmp_path):
    shas = sample_repo(tmp_path / "pay")
    commits, _ = git.read_repo(tmp_path / "pay", AUTHORS, SINCE_2023)
    result = git.normalize([Page(i + 1, [c]) for i, c in enumerate(commits)], "01-raw/git.jsonl",
                           "01-raw/git.jsonl", SINCE_2023)
    by_sha = {d.native_key: d for d in result.drafts}
    first, rename = by_sha[shas["first"]], by_sha[shas["rename"]]
    assert (first.kind, first.engineer_role, first.title, first.excerpt) == ("commit", "author", "Add ledger",
                                                                            "Body for PAY-42.")
    assert first.created_at == "2023-01-01T01:00:00Z"
    assert first.url == f"https://github.com/acme/pay/commit/{shas['first']}"
    assert first.stats == {"additions": 3, "deletions": 0, "files": 2}
    assert ("jira", "PAY-42") in first.refs
    assert rename.squash_of == ("github", "acme/pay#7") and ("github", "acme/pay#7") in rename.refs
    assert first.raw_ref == "01-raw/git.jsonl:3#/items/0"


def test_normalize_bad_rows_and_hosts():
    items = [{"sha": "xyz", "message": "m", "authored_at": "2025-01-01T00:00:00Z"},
             {"sha": "a" * 40, "authored_at": "2025-01-01T00:00:00Z"},
             {"sha": "a" * 40, "message": "m", "authored_at": "later"},
             {"sha": "B" * 40, "message": "Subject", "authored_at": "2025-01-01T00:00:00Z",
              "remote": "gitlab.com/grp/proj", "files": 1, "additions": 1, "deletions": None}]
    result = git.normalize([Page(1, items)], "01-raw/git.jsonl", "01-raw/git.jsonl", OPEN)
    assert result.bad == ["01-raw/git.jsonl:1#/items/0: no commit hash",
                          "01-raw/git.jsonl:1#/items/1: no message",
                          "01-raw/git.jsonl:1#/items/2: authored_at 'later' is not a timestamp"]
    draft = result.drafts[0]
    assert draft.native_key == "b" * 40 and draft.stats is None and draft.excerpt == ""
    assert draft.url == f"https://gitlab.com/grp/proj/-/commit/{'b' * 40}"
    assert git.commit_url("git.example.com/grp/proj", "a" * 40) is None
