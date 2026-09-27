"""rcore.citations (what a source says), rcore.places (a bullet's place), facts.matches, numbers.spans,
and the schemas of 08-ats's keywords.json and report.json."""
import json
from decimal import Decimal

import pytest

from conftest import FIXTURE_WORKSPACE
from rcore import facts, numbers, places, schema, validation, wsio
from rcore.citations import Citations, is_review


def _fixture_citations(workspace=FIXTURE_WORKSPACE):
    return Citations(workspace, wsio.read_jsonl(workspace / "02-evidence" / "evidence.jsonl"),
                     wsio.read_json(workspace / "decisions" / "metrics.json"),
                     wsio.read_json(workspace / "03-profile" / "profile.json"),
                     wsio.read_json(workspace / "decisions" / "profile.json"))


def test_citations_of_the_fixture():
    found = _fixture_citations()
    assert found.texts("ev_191cc8ce") == [
        "PAY-42: Add Redis idempotency cache for Project Falcon checkout",
        "Adds a Redis-backed idempotency cache in front of the Contoso Bank checkout path."]
    assert found.texts("ev_cbf558fa")[-1] == ("2025 H1 performance review\n\nJordan mentored two new engineers "
                                              "through on-call onboarding.\n")  # the review's full text
    assert found.texts("metric:m_1") == ["40", "p99 checkout latency reduced 40%"]
    assert found.texts("resume:/work/1/highlights/0") == [
        "Migrated the order service from PHP to Go, serving 2M requests per day"]
    assert found.texts("wizard:/basics/email") == ["jordan.rivera@example.com"]
    for ref in ("ev_00000000", "metric:m_9", "resume:/work/0", "resume:/nowhere", "wizard:/basics", "x"):
        assert found.texts(ref) == []
    assert found.warnings == []


def test_citations_warn_when_a_review_has_no_text(workspace):
    (workspace / "01-raw" / "reviews.jsonl").unlink()
    found = _fixture_citations(workspace)
    assert found.texts("ev_cbf558fa") == ["2025 H1 performance review",
                                          "Jordan mentored two new engineers through on-call onboarding."]
    assert found.warnings == ["ev_cbf558fa: the raw record 01-raw/reviews.jsonl:1#/items/0 01-raw/reviews.jsonl "
                              "not found; its excerpt stands in for the review's text"]
    assert is_review({"kind": "perf_review"}) and not is_review({"kind": "pr"})


def test_resume_write_uses_the_shared_helpers():
    from rwrite import bullets, material
    assert material.pointer_place is places.pointer_place and material.is_review is is_review
    assert bullets.place({"work_ref": None, "sources": ["resume:/projects/2/description"]}) == "/projects/2"


@pytest.mark.parametrize("bullet, place", [
    ({"work_ref": 0, "sources": ["ev_191cc8ce"]}, ("work", 0)),
    ({"work_ref": 1, "sources": ["resume:/projects/0/description"]}, ("work", 1)),  # work_ref wins
    ({"work_ref": None, "sources": ["ev_cbf558fa", "wizard:/projects/3/name"]}, ("projects", 3)),
    ({"work_ref": None, "sources": ["resume:/work/1/highlights/0"]}, None),  # a job pointer needs work_ref
    ({"work_ref": None, "sources": ["resume:/projects/01/name", "resume:/projectsX/0"]}, None),
    ({"work_ref": None, "sources": []}, None),
])
def test_place(bullet, place):
    assert places.place(bullet) == place


def test_matches_is_the_fact_checks_rule_for_one_entry():
    job = {"name": "Tailspin Toys", "position": "Software Engineer", "startDate": "2019-06", "endDate": "2022-12",
           "highlights": ["x"], "x-lines": {"first": 1, "last": 2}}
    assert facts.matches({"name": "Tailspin Toys", "startDate": "2019", "endDate": "2022-12", "x-highlights": []},
                         job)
    assert not facts.matches({"name": "Tailspin Toys", "startDate": "2019-06"}, job)  # endDate dropped
    assert not facts.matches({"name": "Tailspin", "startDate": "2019-06", "endDate": "2022-12"}, job)
    assert not facts.matches({"name": "Tailspin Toys", "url": "https://x", "startDate": "2019-06",
                              "endDate": "2022-12"}, job)  # a field the profile entry lacks
    assert not facts.matches("Tailspin Toys", job) and not facts.matches({}, None)


def test_number_spans():
    text = "Cut p99 latency 40% for 1,200 users,"
    assert numbers.spans(text) == [(5, 7, "99", Decimal(99)), (16, 18, "40", Decimal(40)),
                                   (24, 29, "1,200", Decimal(1200))]
    assert [text[s:e] for s, e, _, _ in numbers.spans(text)] == ["99", "40", "1,200"]
    assert numbers.numbers(text) == [(w, v) for _, _, w, v in numbers.spans(text)]


def test_ats_schemas_are_mapped():
    for version in ("general", "jobs/fintech-sre"):
        assert validation.schema_for(f"08-ats/{version}/keywords.json") == ("ats-keywords", "json")
        assert validation.schema_for(f"08-ats.tmp/{version}/report.json") == ("ats-report", "json")
    assert validation.schema_for("08-ats/jobs/a/b/report.json") is None


def test_keywords_schema():
    spec = schema.load_schema("ats-keywords")
    assert schema.validate(["Go", "SLO compliance", "C++"], spec) == []
    assert schema.validate([], spec) == []
    assert len(schema.validate(["", " Go", "Go ", "a\nb"], spec)) == 4
    assert schema.validate({"keywords": []}, spec)


def test_report_schema():
    spec = schema.load_schema("ats-report")
    report = {"length": {"experience_months": 88, "pages": 1, "estimated_lines": 34, "line_budget": 50},
              "keywords": [{"keyword": "Go", "status": "covered", "where": ["/skills/0/keywords/0"]}],
              "left_out": [{"bullet_id": "b_5", "reason": "no place"}], "warnings": ["/basics: no email"]}
    assert schema.validate(report, spec) == []
    broken = json.loads(json.dumps(report))
    broken["length"]["pages"] = 3
    broken["keywords"][0]["status"] = "partly"
    broken["left_out"][0]["reason"] = "too long"
    broken["errors"] = []
    assert len(schema.validate(broken, spec)) == 4
