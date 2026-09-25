"""Jira REST issues (v2 and v3) and CSV rows."""
from rcollect import jira
from collect_samples import run

REST = {
    "id": "10042", "key": "PAY-42", "self": "https://acme.atlassian.net/rest/api/2/issue/10042",
    "fields": {
        "summary": "Checkout latency", "description": "See PAY-7 and https://github.com/acme/pay/pull/7",
        "issuetype": {"name": "Epic"}, "status": {"name": "Done"}, "created": "2025-02-10T09:00:00.000+0000",
        "resolutiondate": "2025-05-30T10:00:00.000+0000", "labels": ["latency"],
        "assignee": {"accountId": "5b10ac", "displayName": "Jordan Rivera"},
        "reporter": {"name": "priya", "displayName": "Priya Shah"},
    },
}
ADF = {"type": "doc", "version": 1, "content": [
    {"type": "paragraph", "content": [{"type": "text", "text": "Retry"}, {"type": "hardBreak"},
                                      {"type": "text", "text": "exports for"},
                                      {"type": "mention", "attrs": {"text": "@Jordan"}}]},
    {"type": "paragraph", "content": [{"type": "inlineCard", "attrs": {"url": "https://x.test/browse/PAY-9"}}]},
]}


def only(result):
    assert len(result.drafts) == 1, result.bad
    return result.drafts[0]


def test_rest_epic_assigned_by_display_name():
    draft = only(run(jira.normalize, REST, username="jordan rivera"))
    assert (draft.kind, draft.engineer_role, draft.native_key, draft.state) == ("epic", "assignee", "PAY-42",
                                                                                "Done")
    assert (draft.created_at, draft.closed_at) == ("2025-02-10T09:00:00Z", "2025-05-30T10:00:00Z")
    assert draft.url == "https://acme.atlassian.net/browse/PAY-42"
    assert draft.labels == ["latency"]
    assert {("jira", "PAY-7"), ("github", "acme/pay#7")} <= draft.refs


def test_reporter_and_account_id_and_filtering():
    assert only(run(jira.normalize, REST, username="PRIYA")).engineer_role == "reporter"
    assert only(run(jira.normalize, REST, username="5b10ac")).engineer_role == "assignee"
    result = run(jira.normalize, REST, username="someone")
    assert result.drafts == [] and result.others == {"Jordan Rivera": 1}


def test_adf_description_and_parent():
    item = {"key": "PAY-43", "fields": {
        "summary": "Retries", "description": ADF, "issuetype": {"name": "Story"}, "status": {"name": "To Do"},
        "created": "2025-03-01T00:00:00.000+0000", "resolutiondate": None,
        "assignee": {"name": "jrivera"}, "parent": {"key": "PAY-42"}}}
    draft = only(run(jira.normalize, item))
    assert draft.kind == "ticket" and draft.url is None and draft.closed_at is None
    assert draft.excerpt == "Retry exports for@Jordan https://x.test/browse/PAY-9"
    assert jira.adf_text(ADF) == "Retry\nexports for@Jordan\n https://x.test/browse/PAY-9 \n"
    assert {("jira", "PAY-42"), ("jira", "PAY-9")} <= draft.refs


def test_csv_rows_with_repeated_labels_and_numeric_parent():
    epic = {"Summary": "Latency", "Issue key": "PAY-42", "Issue id": "10042", "Issue Type": "Epic",
            "Status": "Done", "Assignee": "Jordan Rivera", "Assignee Id": "5b10ac", "Reporter": "Priya",
            "Created": "10/Feb/25 9:00 AM", "Resolved": "30/May/25 5:30 PM", "Labels": ["a", "b", "a"],
            "Description": ""}
    story = {"summary": "Retries", "ISSUE KEY": "PAY-43", "Issue Type": "Story", "Status": "Open",
             "Assignee": "", "Reporter": "jrivera", "Created": "2025-03-01 10:00", "Resolved": "",
             "Parent": "10042"}
    classic = {**story, "ISSUE KEY": "PAY-44", "Parent": "", "Custom field (Epic Link)": "PAY-42"}
    result = run(jira.normalize, epic, story, classic, username="5b10ac")
    assert [d.native_key for d in result.drafts] == ["PAY-42"] and result.not_mine == 2
    result = run(jira.normalize, epic, story, classic)
    story_draft, classic_draft = result.drafts
    assert (story_draft.engineer_role, story_draft.created_at, story_draft.closed_at) == (
        "reporter", "2025-03-01T10:00:00Z", None)
    assert ("jira", "PAY-42") in story_draft.refs and ("jira", "PAY-42") in classic_draft.refs
    epic_draft = only(run(jira.normalize, epic, username="jordan rivera"))
    assert epic_draft.labels == ["a", "b"] and epic_draft.closed_at == "2025-05-30T17:30:00Z"


def test_bad_rows():
    result = run(jira.normalize, {"foo": 1}, {"Issue key": "", "Summary": "x"},
                 {"Issue key": "PAY-1", "Summary": "x", "Created": "later", "Assignee": "jrivera"},
                 {"Issue key": "PAY-2", "Summary": "x", "Created": "2025-01-01", "Resolved": "soon",
                  "Assignee": "jrivera"},
                 {"key": "PAY-3", "fields": {"created": "2025-01-01"}})
    assert result.bad == [
        '01-raw/x.jsonl:1#/items/0: neither a Jira REST issue ("key", "fields") nor a CSV row ("Issue key")',
        "01-raw/x.jsonl:1#/items/1: no issue key",
        "01-raw/x.jsonl:1#/items/2: created 'later' is not a timestamp",
        "01-raw/x.jsonl:1#/items/3: resolved 'soon' is not a timestamp",
        "01-raw/x.jsonl:1#/items/4: no summary",
    ]
