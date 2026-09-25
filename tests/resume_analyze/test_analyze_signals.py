"""Clusters of linked evidence, their signals, and the people read from raw records."""
from analyze_samples import eid, item, make_workspace
from conftest import FIXTURE_WORKSPACE
from ranalyze import clusters, raw
from ranalyze.common import evidence_hash, load_config, load_evidence
from rcore import schema, wsio


def day(n: int) -> str:
    return f"2025-01-{n:02d}T00:00:00Z"


def ids_of(found):
    return [[i["id"] for i in members] for members in found]


def compute(ws):
    return clusters.compute(ws, load_config(ws), load_evidence(ws), evidence_hash(ws))


# Clusters --------------------------------------------------------------------

def test_clusters_follow_links_both_ways():
    evidence = [item(1, "ticket", links=[2], created=day(1)), item(2, "epic", created=day(2)),
                item(3, "pr", links=[1], created=day(3)), item(4, "pr", created=day(4)),
                item(5, "review", links=[2], created=day(5))]
    assert ids_of(clusters.build(evidence)) == [[eid(1), eid(2), eid(3), eid(5)], [eid(4)]]


def test_clusters_are_ordered_by_their_first_item():
    evidence = [item(1, "pr", created=day(1)), item(2, "pr", links=[4], created=day(2)),
                item(3, "pr", links=[1], created=day(3)), item(4, "ticket", created=day(4))]
    assert ids_of(clusters.build(evidence)) == [[eid(1), eid(3)], [eid(2), eid(4)]]


def test_a_performance_review_mentions_clusters_without_joining_them(tmp_path):
    evidence = [item(1, "pr", created=day(1)), item(2, "pr", created=day(2)),
                item(3, "perf_review", links=[1, 2], created=day(3)), item(4, "perf_review", created=day(4))]
    assert ids_of(clusters.build(evidence)) == [[eid(1)], [eid(2)]]
    data, _ = compute(make_workspace(tmp_path, evidence))
    assert [c["review_mentions"] for c in data["clusters"]] == [[eid(3)], [eid(3)]]
    assert data["reviews"] == [
        {"id": eid(3), "title": "perf_review 3", "date": "2025-01-03", "raw_ref": None, "clusters": ["c1", "c2"]},
        {"id": eid(4), "title": "perf_review 4", "date": "2025-01-04", "raw_ref": None, "clusters": []},
    ]


def test_links_to_items_that_are_not_evidence_are_ignored():
    evidence = [item(1, "pr", links=[99], created=day(1)), item(2, "pr", created=day(2))]
    assert ids_of(clusters.build(evidence)) == [[eid(1)], [eid(2)]]


def test_label_prefers_an_epic_then_a_ticket_or_issue():
    assert clusters._label([item(1, "pr"), item(2, "ticket", title="T"), item(3, "epic", title="E")]) == "E"
    assert clusters._label([item(1, "pr"), item(2, "issue", title="I"), item(3, "ticket", title="T")]) == "I"
    assert clusters._label([item(1, "pr", title="P"), item(2, "review")]) == "P"


# Signals ---------------------------------------------------------------------

def _big_cluster(tmp_path):
    evidence = [
        item(1, "epic", created=day(1), closed="2025-03-20T10:00:00Z", raw_ref="01-raw/jira.jsonl:1#/items/0"),
        item(2, "ticket", links=[1], created=day(2), raw_ref="01-raw/jira.jsonl:1#/items/1"),
        item(3, "pr", links=[2], created=day(3), closed=day(9), raw_ref="01-raw/github.jsonl:1#/items/0",
             stats={"additions": 100, "deletions": 20, "files": 4}),
        item(4, "review", links=[2], created=day(4), closed=day(5), key="Northwind/API#7",
             raw_ref="01-raw/github.jsonl:2#/items/0"),
        item(5, "commit", links=[2], created=day(6), raw_ref="01-raw/git.jsonl:1#/items/0",
             stats={"additions": 5, "deletions": 1, "files": 1}),
        item(6, "commit", links=[2], created=day(7), raw_ref="01-raw/git.jsonl:1#/items/1"),
        item(7, "mr", source="gitlab", links=[2], created=day(8), raw_ref="01-raw/gitlab.jsonl:1#/items/0"),
        item(8, "issue", role="author", links=[2], created=day(10), key="northwind/ledger#8",
             raw_ref="01-raw/github.jsonl:1#/items/1"),
        item(9, "ticket", role="reporter", source="jira", key="OPS-3", links=[1], created=day(11),
             raw_ref="01-raw/jira.jsonl:1#/items/2"),
        item(10, "perf_review", links=[3], created=day(20)),
    ]
    raw_files = {
        "jira.jsonl": [{"items": [
            {"Issue key": "PAY-1", "Issue Type": "Epic", "Assignee": "Jordan Rivera", "Assignee Id": "jordan.rivera",
             "Reporter": "JORDAN.RIVERA"},
            {"key": "PAY-2", "fields": {"assignee": {"displayName": "Jordan Rivera", "accountId": "jordan.rivera"},
                                        "reporter": {"displayName": "Priya Shah", "accountId": "5b10"}}},
            {"key": "OPS-3", "fields": {"reporter": {"name": "jordan.rivera"},
                                        "assignee": {"displayName": "priya shah"}}},
        ]}],
        "github.jsonl": [
            {"items": [{"number": 3, "user": {"login": "jrivera"}, "assignees": [{"login": "mchen"}]},
                       {"number": 8, "user": {"login": "JRivera"}}]},
            {"items": [{"number": 7, "user": {"login": "MChen"}, "assignees": {"nodes": [{"login": "sam"}]}}]},
        ],
        "git.jsonl": [{"items": [{"sha": "a", "remote": "github.com/northwind/api", "repo": "/src/api"},
                                 {"sha": "b", "remote": None, "repo": "/home/jordan/tools/"}]}],
        "gitlab.jsonl": [{"items": [{"iid": 7, "author": {"username": "jr"}, "assignees": [{"username": "alex"}]}]}],
    }
    return make_workspace(tmp_path, evidence, raw_files)


def test_every_signal(tmp_path):
    data, warnings = compute(_big_cluster(tmp_path))
    assert warnings == []
    assert schema.validate(data, schema.load_schema("signals")) == []
    [cluster] = data["clusters"]
    assert cluster == {
        "id": "c1",
        "label": "epic 1",
        "evidence_ids": [eid(n) for n in range(1, 10)],
        "start": "2025-01-01",
        "end": "2025-03-20",
        "days": 78,
        "kinds": {"pr": 1, "mr": 1, "commit": 2, "review": 1, "issue": 1, "ticket": 2, "epic": 1},
        "authored": 4,
        "reviewed": 1,
        "assigned": 2,
        "reported": 2,
        "stats": {"additions": 105, "deletions": 21, "files": 5},
        "repos": ["Northwind/API", "group/app", "northwind/api", "northwind/ledger", "tools"],
        "jira_projects": ["OPS", "PAY"],
        # Priya Shah (Jira REST and, differently spelled, a Jira user object), mchen (twice), sam, alex
        "contributors": 4,
        "epics": [eid(1)],
        "epics_created": [eid(1)],
        "first_authored_at": "2025-01-03",
        "authored_first": True,
        "open_items": 4,
        "review_mentions": [eid(10)],
    }


def test_authored_first_is_false_when_a_review_comes_first(tmp_path):
    evidence = [item(1, "review", created=day(1)), item(2, "pr", links=[1], created=day(2))]
    [cluster] = compute(make_workspace(tmp_path, evidence))[0]["clusters"]
    assert cluster["first_authored_at"] == "2025-01-02"
    assert cluster["authored_first"] is False


def test_no_authored_work(tmp_path):
    evidence = [item(1, "ticket", created=day(1), closed=day(4)), item(2, "review", links=[1], created=day(2))]
    [cluster] = compute(make_workspace(tmp_path, evidence))[0]["clusters"]
    assert (cluster["first_authored_at"], cluster["authored_first"]) == (None, False)
    assert cluster["stats"] == {"additions": 0, "deletions": 0, "files": 0}
    assert (cluster["open_items"], cluster["days"]) == (0, 3)


def test_reviews_add_no_size(tmp_path):
    evidence = [item(1, "review", created=day(1), stats={"additions": 999, "deletions": 1, "files": 9})]
    [cluster] = compute(make_workspace(tmp_path, evidence))[0]["clusters"]
    assert cluster["stats"] == {"additions": 0, "deletions": 0, "files": 0}


def test_missing_raw_records_warn_once_per_file_and_add_no_people(tmp_path):
    evidence = [item(1, "epic", role="reporter", created=day(1), raw_ref="01-raw/jira.jsonl:1#/items/0"),
                item(2, "ticket", links=[1], created=day(2), raw_ref="01-raw/jira.jsonl:2#/items/0"),
                item(3, "pr", links=[1], created=day(3), raw_ref="01-raw/github.jsonl:5#/items/0"),
                item(4, "pr", links=[1], created=day(4), raw_ref="01-raw/github.jsonl:1#/items/3"),
                item(5, "pr", links=[1], created=day(5), raw_ref="elsewhere/x.jsonl:1#/items/0")]
    ws = make_workspace(tmp_path, evidence, {"github.jsonl": [{"items": [{"user": {"login": "mchen"}}]}]})
    data, warnings = compute(ws)
    assert warnings == [
        "01-raw/jira.jsonl: not found; its items add no people to the signals",
        "01-raw/github.jsonl: line 5 has no item 0; its items add no people to the signals",
        "raw_ref 'elsewhere/x.jsonl:1#/items/0' is not 01-raw/<file>:<line>#/items/<index>; its items add no "
        "people to the signals",
    ]
    [cluster] = data["clusters"]
    assert cluster["contributors"] == 0
    assert cluster["epics_created"] == [eid(1)]


def test_an_epic_someone_else_reported_was_not_created_by_the_engineer(tmp_path):
    evidence = [item(1, "epic", created=day(1), raw_ref="01-raw/jira.jsonl:1#/items/0")]
    ws = make_workspace(tmp_path, evidence, {"jira.jsonl": [{"items": [{"key": "PAY-1", "fields": {
        "assignee": {"name": "jordan.rivera"}, "reporter": {"name": "priya", "emailAddress": "p@x.test"}}}]}]})
    [cluster] = compute(ws)[0]["clusters"]
    assert (cluster["epics_created"], cluster["contributors"]) == ([], 1)


# People ------------------------------------------------------------------------

def test_people_per_source():
    assert raw.people("github", {"user": {"login": "a"}, "assignee": {"login": "b"},
                                 "assignees": [{"login": "c"}, "d"]}) == [["a"], ["b"], ["c"], ["d"]]
    assert raw.people("github", {"author": {"login": "a"}, "assignees": {"nodes": [{"login": "b"}]}}) == [["a"], ["b"]]
    assert raw.people("gitlab", {"author": {"username": "a"}, "assignees": [{"username": "b"}]}) == [["a"], ["b"]]
    assert raw.people("jira", {"fields": {"assignee": {"displayName": "A B", "name": "ab", "accountId": "1"},
                                          "reporter": None}}) == [["A B", "ab", "1"]]
    assert raw.people("jira", {"Assignee": "A B", "assignee id": "ab", "REPORTER": ["", "C"]}) == [["A B", "ab"],
                                                                                                    ["C"]]
    assert raw.people("git", {"author_email": "x@y"}) == []
    assert raw.people("review", {"text": "x"}) == []


def test_the_engineer_matches_any_identity_ignoring_case():
    assert raw.is_engineer(["Jordan Rivera", "JORDAN.RIVERA"], "jordan.rivera")
    assert not raw.is_engineer(["Jordan Rivera"], "jordan.rivera")
    assert not raw.is_engineer(["x"], None)


def test_commit_repositories():
    assert raw.commit_repo({"remote": "github.com/northwind/ledger"}) == "northwind/ledger"
    assert raw.commit_repo({"remote": None, "repo": "C:\\src\\ledger"}) == "ledger"
    assert raw.commit_repo({}) is None


# The fixture -----------------------------------------------------------------

def test_the_fixture_signals(workspace):
    data, warnings = clusters.compute(workspace, load_config(workspace), load_evidence(workspace),
                                      evidence_hash(workspace))
    assert warnings == []
    assert data == wsio.read_json(FIXTURE_WORKSPACE / "04-projects" / "signals.json")
