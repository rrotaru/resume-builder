"""GitLab merge requests and issues."""
from rcollect import gitlab
from collect_samples import run

MR = {
    "iid": 12, "title": "Cache", "description": "Fixes #3, relates to !4 and infra/tools!5. PAY-42",
    "web_url": "https://gitlab.com/acme/pay/-/merge_requests/12", "references": {"full": "acme/pay!12"},
    "author": {"username": "jrivera"}, "reviewers": [{"username": "mchen"}], "state": "merged",
    "created_at": "2025-03-01T10:00:00.000+01:00", "merged_at": "2025-03-02T10:00:00.000Z",
    "closed_at": None, "labels": ["backend", "backend"], "source_branch": "pay-77-cache",
    "merge_commit_sha": "A" * 40, "squash_commit_sha": "b" * 40,
}


def only(result):
    assert len(result.drafts) == 1, result.bad
    return result.drafts[0]


def test_authored_merge_request():
    draft = only(run(gitlab.normalize, MR))
    assert (draft.kind, draft.engineer_role, draft.native_key, draft.state) == ("mr", "author", "acme/pay!12",
                                                                               "merged")
    assert (draft.created_at, draft.closed_at) == ("2025-03-01T09:00:00Z", "2025-03-02T10:00:00Z")
    assert draft.labels == ["backend"] and draft.stats is None
    assert draft.merge_shas == {"a" * 40, "b" * 40}
    assert {("gitlab", "acme/pay#3"), ("gitlab", "acme/pay!4"), ("gitlab", "infra/tools!5"),
            ("jira", "PAY-42"), ("jira", "PAY-77")} <= draft.refs


def test_reviewed_merge_request():
    item = {**MR, "author": {"username": "mchen"}, "reviewers": [{"username": "JRivera"}]}
    draft = only(run(gitlab.normalize, item))
    assert (draft.kind, draft.engineer_role, draft.merge_shas) == ("review", "reviewer", set())
    by_query = {**MR, "author": {"username": "mchen"}, "reviewers": []}
    query = "GET /merge_requests?reviewer_username=jrivera"
    assert only(run(gitlab.normalize, by_query, query=query)).kind == "review"
    assigned = {**by_query, "assignees": [{"username": "jrivera"}]}
    assert only(run(gitlab.normalize, assigned)).engineer_role == "assignee"
    result = run(gitlab.normalize, by_query, query="GET /merge_requests?author_username=mchen")
    assert result.drafts == [] and result.others == {"mchen": 1}


def test_issue_from_web_url_and_states():
    issue = {"iid": 3, "title": "Bug", "web_url": "https://git.example.com/acme/sub/pay/-/issues/3",
             "author": {"username": "mchen"}, "assignee": {"username": "jrivera"}, "state": "opened",
             "created_at": "2025-01-01T00:00:00Z", "labels": [{"name": "bug"}]}
    draft = only(run(gitlab.normalize, issue))
    assert (draft.kind, draft.engineer_role, draft.native_key, draft.state, draft.labels) == (
        "issue", "assignee", "acme/sub/pay#3", "open", ["bug"])


def test_bad_rows():
    result = run(gitlab.normalize, {"title": "x", "created_at": "2025-01-01"}, {**MR, "title": 5},
                 {**MR, "created_at": None})
    assert result.bad == [
        "01-raw/x.jsonl:1#/items/0: cannot tell the project and number (no references.full or web_url)",
        "01-raw/x.jsonl:1#/items/1: no title",
        "01-raw/x.jsonl:1#/items/2: created_at None is not a timestamp",
    ]
