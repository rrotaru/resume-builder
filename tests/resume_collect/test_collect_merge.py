"""References found in text, duplicates, squash commits, IDs and links."""
from rcollect import merge, refs
from rcollect.common import Draft
from rcore import ids


def test_jira_keys_stand_alone():
    text = "PAY-42: fix (see PAY-7, xPAY-8, PAY-9x, pay-10, PAY-0, UTF-8) https://j.test/browse/OPS-3"
    assert refs.jira_keys(text) == {("jira", k) for k in ("PAY-42", "PAY-7", "UTF-8", "OPS-3")}
    assert refs.branch_keys("feature/pay-42-cache") == {("jira", "PAY-42")}
    assert refs.branch_keys(None) == set()


def test_github_references():
    text = ("Fixes #12, see acme/infra#3 and https://github.com/acme/web/pull/9/files and "
            "https://ghe.test/Team/Svc/issues/4 but not &#39; or page#5 or a/b/c#6-ish")
    found = refs.find(text, github_repo="acme/pay")
    assert {("github", "acme/pay#12"), ("github", "acme/infra#3"), ("github", "acme/web#9"),
            ("github", "Team/Svc#4")} <= found
    assert ("github", "acme/pay#39") not in found and ("github", "acme/pay#5") not in found
    assert not any(src == "github" and key.startswith("a/b/c") for src, key in found)
    assert ("github", "acme/pay#12") not in refs.find("Fixes #12")


def test_gitlab_references():
    text = "Closes #3 and !4, needs grp/sub/proj!5 and https://gl.test/grp/other/-/issues/6"
    found = refs.find(text, gitlab_project="grp/proj")
    assert {("gitlab", "grp/proj#3"), ("gitlab", "grp/proj!4"), ("gitlab", "grp/sub/proj!5"),
            ("gitlab", "grp/other#6")} <= found


def draft(source, native_key, role="author", kind="pr", created="2025-01-01T00:00:00Z", **extra):
    return Draft(source=source, kind=kind, native_key=native_key, title=native_key, engineer_role=role,
                 created_at=created, raw_ref=f"01-raw/{source}.jsonl:1#/items/0", **extra)


def test_links_resolve_only_to_evidence_ignoring_case():
    pr = draft("github", "Acme/Pay#7", refs={("github", "acme/pay#7"), ("jira", "pay-42"), ("jira", "OPS-1"),
                                            ("github", "acme/pay#8")})
    epic = draft("jira", "PAY-42", role="assignee", kind="epic", created="2024-12-01T00:00:00Z")
    issue = draft("github", "acme/pay#8", role="assignee", kind="issue", created="2025-02-01T00:00:00Z")
    records, duplicates = merge.build([pr, epic, issue])
    by_key = {r["native_key"]: r for r in records}
    assert duplicates == 0
    assert by_key["acme/pay#7"]["links"] == sorted([by_key["PAY-42"]["id"], by_key["acme/pay#8"]["id"]])
    assert [r["native_key"] for r in records] == ["PAY-42", "acme/pay#7", "acme/pay#8"]
    assert by_key["PAY-42"]["id"] == ids.evidence_id("jira", "PAY-42")


def test_ids_do_not_depend_on_how_a_source_spells_the_key():
    """The same item spelled differently by two sources, or by two runs, keeps one ID."""
    for spelling in ("Acme/Pay#7", "acme/pay#7", "ACME/PAY#7"):
        records, _ = merge.build([draft("github", spelling), draft("gitlab", spelling.replace("#", "!")),
                                  draft("jira", "pay-42", role="assignee", kind="epic")])
        assert {r["native_key"]: r["id"] for r in records} == {
            "acme/pay#7": ids.evidence_id("github", "acme/pay#7"),
            "acme/pay!7": ids.evidence_id("gitlab", "acme/pay!7"),
            "PAY-42": ids.evidence_id("jira", "PAY-42"),
        }
    review = draft("github", "Acme/Pay#7", role="reviewer", kind="review")
    authored = draft("github", "ACME/pay#7")
    for order in ([review, authored], [authored, review]):
        (record,), _ = merge.build(order)
        assert (record["native_key"], record["id"]) == ("acme/pay#7", ids.evidence_id("github", "acme/pay#7"))


def test_same_item_twice_keeps_the_stronger_role():
    review = draft("github", "acme/pay#7", role="reviewer", kind="review", labels=["b"], refs={("jira", "X-1")})
    authored = draft("github", "acme/pay#7", labels=["a", "b"], stats={"additions": 1, "deletions": 0, "files": 1})
    again = draft("github", "ACME/pay#7", labels=["c"])
    epic = draft("jira", "X-1", role="assignee", kind="epic")
    records, duplicates = merge.build([review, authored, again, epic])
    pr = next(r for r in records if r["source"] == "github")
    assert duplicates == 2 and len(records) == 2
    assert (pr["kind"], pr["engineer_role"], pr["labels"], pr["stats"]["files"]) == ("pr", "author",
                                                                                      ["a", "b", "c"], 1)
    assert pr["links"] == [ids.evidence_id("jira", "X-1")]


def test_squash_and_merge_commits_of_authored_pull_requests_are_dropped():
    pr = draft("github", "acme/pay#7", merge_shas={"a" * 40})
    by_sha = draft("git", "a" * 40, kind="commit", sha="a" * 40, refs={("jira", "PAY-1")})
    by_subject = draft("git", "b" * 40, kind="commit", sha="b" * 40, squash_of=("github", "ACME/pay#7"))
    other = draft("git", "c" * 40, kind="commit", sha="c" * 40, squash_of=("github", "acme/pay#8"),
                  refs={("github", "acme/pay#8")})
    reviewed = draft("github", "acme/pay#8", role="reviewer", kind="review")
    epic = draft("jira", "PAY-1", role="assignee", kind="epic")
    records, duplicates = merge.build([pr, by_sha, by_subject, other, reviewed, epic])
    keys = {r["native_key"]: r for r in records}
    assert duplicates == 2
    assert sorted(keys) == sorted(["acme/pay#7", "c" * 40, "acme/pay#8", "PAY-1"])
    assert keys["acme/pay#7"]["links"] == [keys["PAY-1"]["id"]]  # moved from the dropped commit
    assert keys["c" * 40]["links"] == [keys["acme/pay#8"]["id"]]


def test_colliding_ids_are_lengthened(monkeypatch):
    real = ids._digest
    monkeypatch.setattr(ids, "_digest", lambda text: "0" * 8 + real(text)[8:])  # every short ID collides
    a, b = draft("jira", "A-1", role="assignee", kind="ticket"), draft("jira", "B-1", role="assignee",
                                                                         kind="ticket")
    records, _ = merge.build([a, b])
    assert sorted(len(r["id"]) for r in records) == [15, 15]
    assert records[0]["id"] != records[1]["id"]
