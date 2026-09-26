"""rwrite.material: job months, overlaps, pointer places and the texts sources hold."""
import pytest

from rwrite import common, material
from write_samples import EVIDENCE, PA, PB, PROFILE, REVIEW_TEXT, eid, make_workspace, project


def build(ws):
    return material.build(ws, common.load_inputs(ws))


@pytest.mark.parametrize("value, end, expected", [
    ("2023", False, (2023, 1)), ("2023", True, (2023, 12)), ("2023-04", True, (2023, 4)),
    ("2023-04-30", False, (2023, 4)), ("2023-02-30", False, None), ("present", False, None), (None, False, None),
])
def test_month(value, end, expected):
    assert material.month(value, end) == expected


@pytest.mark.parametrize("job, overlapping", [
    ({"startDate": "2023-01"}, True),                          # ongoing
    ({"startDate": "2019-06", "endDate": "2022-12"}, False),  # ended before
    ({"startDate": "2025-05", "endDate": "2026"}, True),       # starts in the project's last month
    ({"startDate": "2019", "endDate": "2025-01-31"}, False),   # ends the month before
    ({"startDate": "2019", "endDate": "2025"}, True),          # a year alone ends in December
    ({"endDate": "2025-03"}, True),                            # open start
    ({}, True),                                                # no dates at all
    ({"startDate": "2025-06"}, False),                         # starts after
])
def test_overlaps(job, overlapping):
    assert material.overlaps(job, project(PA, [1], "X", 1, "2025-02", "2025-05", True)) is overlapping


def test_span():
    assert material.span({"startDate": "2019-06", "endDate": "2022-12"}) == "2019-06 to 2022-12"
    assert material.span({"startDate": "2023-01"}) == "2023-01 to present"
    assert material.span({"endDate": "2020"}) == "? to 2020"
    assert material.span({}) == ""


@pytest.mark.parametrize("ref, place", [
    ("resume:/work/1/highlights/0", ("work", 1)), ("wizard:/work/2/name", ("work", 2)),
    ("resume:/projects/0/description", ("projects", 0)), ("resume:/work/10", ("work", 10)),
    ("resume:/basics/summary", None), ("resume:/awards/0/title", None), ("resume:/work/01/name", None),
    ("ev_00000001", None), ("metric:m_1", None),
])
def test_pointer_place(ref, place):
    assert material.pointer_place(ref) == place


def test_x_field():
    assert material.x_field("resume:/work/0/x-lines/first") == "x-lines"
    assert material.x_field("wizard:/work/0/x-lines") == "x-lines"
    assert material.x_field("resume:/work/0/highlights/0") is None
    assert material.x_field("ev_00000001") is None


def test_source_texts(tmp_path):
    found = build(make_workspace(tmp_path, wizard={"work": [{"name": "Northwind Ltd"}], "basics": {"phone": 5550100}}))
    assert found.source_texts(eid(2)) == ["Add idempotency cache", "Cache in front of checkout in 3 regions."]
    assert found.source_texts(eid(5)) == ["2025 H1 review", "Jordan led the cache work.", REVIEW_TEXT]
    assert found.source_texts("metric:m_1") == ["40", "p99 checkout latency reduced 40%"]
    assert found.source_texts("resume:/work/1/highlights/0") == [PROFILE["work"][1]["highlights"][0]]
    assert found.source_texts("wizard:/work/0/name") == ["Northwind Ltd"]
    assert found.source_texts("wizard:/basics/phone") == ["5550100"]
    assert found.source_texts("resume:/work/0") == []  # not a single value
    assert found.source_texts("resume:/nowhere") == []
    assert found.source_texts("metric:m_9") == []
    assert found.raw_warnings == []


def test_a_float_metric_value_reads_back_without_an_exponent(tmp_path):
    metrics = [{"id": "m_1", "project_id": PA, "value": 12000000000000000.0, "unit": "requests",
                "statement": "served 12000000000000000 requests"}]
    found = build(make_workspace(tmp_path, metrics=metrics))
    assert found.source_texts("metric:m_1")[0] == "12000000000000000"


def test_an_unreadable_review_gives_a_warning_and_its_excerpt_stands_in(tmp_path):
    found = build(make_workspace(tmp_path, review_text=None))
    assert found.source_texts(eid(5)) == ["2025 H1 review", "Jordan led the cache work."]
    assert found.raw_warnings == [f"{eid(5)}: the raw record 01-raw/reviews.jsonl:1#/items/0 01-raw/reviews.jsonl "
                                  "not found; its excerpt stands in for the review's text"]


def test_a_review_without_a_raw_ref(tmp_path):
    evidence = [dict(e) for e in EVIDENCE]
    del evidence[4]["raw_ref"]  # optional in evidence.schema.json
    found = build(make_workspace(tmp_path, evidence=evidence))
    assert found.source_texts(eid(5)) == ["2025 H1 review", "Jordan led the cache work."]
    assert found.raw_warnings == [f"{eid(5)}: has no raw_ref; its excerpt stands in for the review's text"]


def test_story_texts_are_the_projects_evidence_the_reviews_and_its_metrics(tmp_path):
    found = build(make_workspace(tmp_path))
    texts = found.story_texts(found.by_id[PA])
    assert "Reduce p99 checkout latency." in texts and REVIEW_TEXT in texts and "40" in texts
    assert "Retries ledger exports." not in texts  # another project's evidence
    assert "40" not in found.story_texts(found.by_id[PB])


def test_required_pointers(tmp_path):
    profile = {"work": [{"name": "A", "highlights": ["one", " ", "two"]}, {"name": "B", "summary": "prose"}],
               "projects": [{"name": "p", "description": "d", "highlights": ["h"]}, {"name": "q", "description": "d"},
                            {"name": "r"}]}
    found = build(make_workspace(tmp_path, profile=profile))
    assert found.required_pointers() == ["resume:/work/0/highlights/0", "resume:/work/0/highlights/2",
                                         "resume:/projects/0/highlights/0", "resume:/projects/1/description"]


def test_jobs_come_from_the_effective_profile(tmp_path):
    wizard = {"work": [{}, {}, {"name": "Contoso", "position": "Staff Engineer", "startDate": "2025-01"}]}
    found = build(make_workspace(tmp_path, wizard=wizard))
    assert [job.get("name") for job in found.jobs] == ["Northwind", "Tailspin", "Contoso"]
    assert found.jobs_for(found.by_id[PA]) == [0, 2]
    assert found.job_label(1) == "/work/1 (2019-06 to 2022-12)"
    assert [p["id"] for p in found.homeless()] == []


def test_projects_in_rank_order_and_their_items_in_evidence_order(tmp_path):
    projects = [project(PB, [3], "B", 2, "2025-06", "2025-06", False),
                project(PA, [2, 1], "A", 1, "2025-02", "2025-05", True)]
    found = build(make_workspace(tmp_path, projects=projects))
    assert [p["id"] for p in found.projects] == [PA, PB]
    assert [i["id"] for i in found.items_of(found.by_id[PA])] == [eid(1), eid(2)]
    assert found.owner == {eid(1): PA, eid(2): PA, eid(3): PB}
