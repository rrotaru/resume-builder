"""The texts each half reads (rsanitize.texts), their places, and where a term occurs."""
from rsanitize.texts import RawReader, Text, line_of, output_texts, places, scan_texts

from sanitize_samples import eid, item, make_workspace, project

REVIEW_TEXT = "2025 H1 review\n\nLed the Falcon rollout for Fabrikam, which the excerpt cuts off."


def workspace_with_review(tmp_path, raw_ref="01-raw/reviews.jsonl:1#/items/0", raw=True):
    evidence = [item(1, "Add Falcon cache", "For Contoso."), item(2, "Unrelated fix", "Nightjar"),
                item(3, "2025 H1 review", "Led the Falcon rollout", kind="perf_review", raw_ref=raw_ref)]
    pages = {"reviews.jsonl": [{"items": [{"file": "h1.txt", "text": REVIEW_TEXT}]}]} if raw else {}
    return make_workspace(tmp_path, projects=[project("pj_0000000a", [1], name="Falcon cache",
                                                      summary="Cache for Contoso.", reasons=["named in review"])],
                          evidence=evidence, raw=pages)


def test_scan_reads_projects_their_evidence_reviews_and_the_profile(tmp_path):
    ws = workspace_with_review(tmp_path)
    from rcore import wsio
    projects = wsio.read_json(ws / "04-projects" / "projects.json")
    evidence = wsio.read_jsonl(ws / "02-evidence" / "evidence.jsonl")
    profile = {"basics": {"name": "Jordan Rivera", "summary": "Backend engineer."},
               "work": [{"name": "Northwind", "highlights": ["Shipped Falcon"]}]}
    scanned = scan_texts(ws, projects, evidence, profile)
    assert [(t.place, t.text, t.names) for t in scanned.texts] == [
        ("pj_0000000a", "Falcon cache", True), ("pj_0000000a", "Cache for Contoso.", True),
        ("pj_0000000a", "named in review", True),
        (eid(1), "Add Falcon cache", True), (eid(1), "For Contoso.", True),
        (eid(3), "2025 H1 review", True), (eid(3), "Led the Falcon rollout", True), (eid(3), REVIEW_TEXT, True),
        ("resume:/basics/name", "Jordan Rivera", False), ("resume:/basics/summary", "Backend engineer.", True),
        ("resume:/work/0/name", "Northwind", False), ("resume:/work/0/highlights/0", "Shipped Falcon", True)]
    assert (scanned.projects, scanned.project_items, scanned.reviews, scanned.profile) == (1, 1, 1, True)
    assert scanned.warnings == []
    assert scan_texts(ws, projects, evidence, None).profile is False


def test_an_item_without_an_excerpt_is_read_by_its_title(tmp_path):
    # excerpt is optional in evidence.schema.json.
    bare = item(1, "Add Falcon cache")
    del bare["excerpt"]
    ws = make_workspace(tmp_path, projects=[project("pj_0000000a", [1])], evidence=[bare])
    scanned = scan_texts(ws, [project("pj_0000000a", [1])], [bare], None)
    assert [(t.place, t.text) for t in scanned.texts if t.place == eid(1)] == [(eid(1), "Add Falcon cache")]


def test_an_unreadable_review_falls_back_to_its_excerpt(tmp_path):
    ws = workspace_with_review(tmp_path, raw=False)
    from rcore import wsio
    scanned = scan_texts(ws, wsio.read_json(ws / "04-projects" / "projects.json"),
                         wsio.read_jsonl(ws / "02-evidence" / "evidence.jsonl"), None)
    assert scanned.warnings == [f"{eid(3)}: the raw record 01-raw/reviews.jsonl:1#/items/0 01-raw/reviews.jsonl "
                                "not found; its excerpt stands in for the review's text"]
    assert REVIEW_TEXT not in [t.text for t in scanned.texts]


def test_raw_reader_reasons(tmp_path):
    ws = workspace_with_review(tmp_path)
    reader = RawReader(ws)
    assert reader.text("01-raw/reviews.jsonl:1#/items/0") == (REVIEW_TEXT, None)
    assert reader.text("reviews.jsonl") == (None, "is not a raw reference")
    assert reader.text("01-raw/reviews.jsonl:2#/items/0") == (None, "01-raw/reviews.jsonl has no line 2")
    assert reader.text("01-raw/reviews.jsonl:1#/items/5") == (None, "does not resolve")
    assert reader.text("01-raw/reviews.jsonl:1#/items") == (None, "has no text")


def test_output_texts_and_places():
    bullets = [{"id": "b_1", "text": "Led Falcon"}, {"id": "b_2", "text": "Other"}]
    stories = "# Stories\n\n## Falcon\n- For Falcon\n"
    texts = output_texts(bullets, stories, {"projects": [{"name": "Falcon", "description": "Falcon linter"}]})
    assert [(t.place, t.names) for t in texts] == [
        ("b_1", True), ("b_2", True), ("stories.md", True), ("resume:/projects/0/name", False),
        ("resume:/projects/0/description", True)]
    assert places("Falcon", texts, []) == ["b_1", "stories.md:3", "stories.md:4", "resume:/projects/0/name",
                                           "resume:/projects/0/description"]
    assert places("Falcon", [Text("b_1", "a Falcon checkpoint")], ["Falcon checkpoint"]) == []


def test_line_of_counts_like_splitlines():
    text = "a\r\nb c\x0cd"
    assert [line_of(text, text.index(c)) for c in "abcd"] == [1, 2, 3, 4]
