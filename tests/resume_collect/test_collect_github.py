"""GitHub: REST, GraphQL and gh CLI shapes, roles, filtering and bad rows."""
from rcollect import github
from collect_samples import run

REST_PR = {
    "number": 7, "title": "  Add   cache ", "body": "<!-- tpl -->Closes #3 and acme/infra#9. See PAY-42.",
    "html_url": "https://github.com/acme/pay/pull/7", "url": "https://api.github.com/repos/acme/pay/pulls/7",
    "user": {"login": "JRivera"}, "state": "closed", "created_at": "2025-03-01T10:00:00Z",
    "closed_at": "2025-03-02T10:00:00Z", "merged_at": "2025-03-02T09:00:00Z",
    "merge_commit_sha": "ABCDEF0123456789ABCDEF0123456789ABCDEF01",
    "labels": [{"name": "perf"}, {"name": "perf"}], "additions": 10, "deletions": 2, "changed_files": 3,
    "head": {"ref": "pay-77-cache"}, "base": {"repo": {"full_name": "acme/pay"}},
}
SEARCH_PR = {
    "number": 8, "title": "Tidy", "body": None, "html_url": "https://github.com/acme/pay/pull/8",
    "repository_url": "https://api.github.com/repos/acme/pay", "user": {"login": "mchen"},
    "state": "closed", "created_at": "2025-04-01T00:00:00Z", "closed_at": "2025-04-02T00:00:00Z",
    "pull_request": {"merged_at": None}, "labels": [],
}
GH_CLI_PR = {
    "number": 9, "title": "CLI shape", "body": "", "url": "https://github.com/acme/web/pull/9",
    "author": {"login": "jrivera"}, "state": "MERGED", "createdAt": "2025-05-01T00:00:00Z",
    "closedAt": "2025-05-03T00:00:00Z", "mergedAt": "2025-05-02T00:00:00Z", "additions": 1, "deletions": 1,
    "changedFiles": 1, "headRefName": "main", "mergeCommit": {"oid": "1" * 40},
    "labels": {"nodes": [{"name": "ui"}]},
}


def only(result):
    assert len(result.drafts) == 1, result.bad
    return result.drafts[0]


def test_rest_pull_request_authored():
    draft = only(run(github.normalize, REST_PR))
    assert (draft.kind, draft.engineer_role, draft.native_key) == ("pr", "author", "acme/pay#7")
    assert draft.title == "Add cache"
    assert draft.excerpt == "Closes #3 and acme/infra#9. See PAY-42."
    assert (draft.created_at, draft.closed_at, draft.state) == (
        "2025-03-01T10:00:00Z", "2025-03-02T09:00:00Z", "merged")
    assert draft.url == "https://github.com/acme/pay/pull/7"
    assert draft.stats == {"additions": 10, "deletions": 2, "files": 3}
    assert draft.labels == ["perf"]
    assert draft.merge_shas == {"abcdef0123456789abcdef0123456789abcdef01"}
    assert draft.raw_ref == "01-raw/x.jsonl:1#/items/0"
    assert {("github", "acme/pay#3"), ("github", "acme/infra#9"), ("jira", "PAY-42"),
            ("jira", "PAY-77")} <= draft.refs


def test_gh_cli_and_graphql_shapes():
    draft = only(run(github.normalize, GH_CLI_PR))
    assert (draft.native_key, draft.state, draft.closed_at) == ("acme/web#9", "merged", "2025-05-02T00:00:00Z")
    assert draft.labels == ["ui"] and draft.merge_shas == {"1" * 40}
    assert draft.stats == {"additions": 1, "deletions": 1, "files": 1}


def test_reviewed_pull_request_from_the_query():
    result = run(github.normalize, SEARCH_PR, query="is:pr reviewed-by:jrivera -author:jrivera")
    draft = only(result)
    assert (draft.kind, draft.engineer_role, draft.state, draft.stats) == ("review", "reviewer", "closed", None)
    assert draft.native_key == "acme/pay#8" and draft.merge_shas == set()


def test_negated_or_other_reviewer_query_does_not_count():
    for query in ("is:pr -reviewed-by:jrivera", "is:pr reviewed-by:jriverax", "involves:jrivera", None):
        result = run(github.normalize, SEARCH_PR, query=query)
        assert result.drafts == [] and result.not_mine == 1
        assert result.others == {"mchen": 1}


def test_reviewed_pull_request_from_embedded_reviews():
    item = {**SEARCH_PR, "reviews": [
        {"user": {"login": "someone"}, "submitted_at": "2025-04-01T01:00:00Z"},
        {"user": {"login": "jrivera"}, "submitted_at": "2025-04-01T09:00:00Z"},
        {"user": {"login": "jrivera"}, "submitted_at": "2025-04-01T05:00:00Z"}]}
    draft = only(run(github.normalize, item))
    assert (draft.kind, draft.created_at) == ("review", "2025-04-01T05:00:00Z")
    graphql = {**SEARCH_PR, "latestReviews": {"nodes": [{"author": {"login": "jrivera"}, "submittedAt": None}]}}
    assert only(run(github.normalize, graphql)).created_at == "2025-04-01T00:00:00Z"


def test_author_wins_over_reviewer():
    item = {**REST_PR, "reviews": [{"user": {"login": "jrivera"}}]}
    assert only(run(github.normalize, item, query="reviewed-by:jrivera")).kind == "pr"


def test_issues_assigned_or_opened():
    issue = {"number": 3, "title": "Bug", "html_url": "https://github.com/acme/pay/issues/3",
             "repository_url": "https://api.github.com/repos/acme/pay", "user": {"login": "mchen"},
             "assignees": [{"login": "jrivera"}], "state": "open", "created_at": "2025-01-01T00:00:00Z"}
    draft = only(run(github.normalize, issue))
    assert (draft.kind, draft.engineer_role, draft.state, draft.closed_at) == ("issue", "assignee", "open", None)
    opened = {**issue, "user": {"login": "jrivera"}, "assignees": []}
    assert only(run(github.normalize, opened)).engineer_role == "author"
    cli = {**issue, "isPullRequest": False, "url": issue["html_url"], "html_url": None, "assignees": [],
           "assignee": {"login": "jrivera"}}
    assert only(run(github.normalize, cli)).engineer_role == "assignee"
    other = {**issue, "assignees": []}
    result = run(github.normalize, other)
    assert result.drafts == [] and result.not_mine == 1


def test_bad_rows_name_line_and_item():
    result = run(github.normalize, "text", {"title": "x"}, {**REST_PR, "number": None, "html_url": None},
                 {**REST_PR, "title": None}, {**REST_PR, "created_at": "soon"}, REST_PR)
    assert len(result.drafts) == 1 and result.items == 6
    assert result.bad == [
        "01-raw/x.jsonl:1#/items/0: not an object",
        "01-raw/x.jsonl:1#/items/1: cannot tell the repository",
        "01-raw/x.jsonl:1#/items/2: no number",
        "01-raw/x.jsonl:1#/items/3: no title",
        "01-raw/x.jsonl:1#/items/4: created_at 'soon' is not a timestamp",
    ]


def test_number_and_repository_from_the_web_url():
    item = {"title": "t", "html_url": "https://ghe.example.com/team/svc/pull/12", "user": {"login": "jrivera"},
            "created_at": "2025-01-01T00:00:00Z"}
    draft = only(run(github.normalize, item))
    assert (draft.native_key, draft.kind) == ("team/svc#12", "pr")


def test_time_range_filters():
    result = run(github.normalize, REST_PR, time_range={"start": "2025-04-01", "end": None})
    assert result.drafts == [] and result.out_of_range == 1 and result.not_mine == 0
