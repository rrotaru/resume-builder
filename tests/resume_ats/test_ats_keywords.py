"""rats.coverage and the checks of keywords.json."""
import pytest

from ats_samples import GENERAL_KEYWORDS, JOB_KEYWORDS, build, fix_month, write_keywords
from conftest import FIXTURE_WORKSPACE
from rats import check, coverage
from rats.common import Version
from rcore import stages, wsio


def resume(version="general"):
    folder = "general" if version == "general" else f"jobs/{version}"
    return wsio.read_json(FIXTURE_WORKSPACE / "08-ats" / folder / "resume.json")


@pytest.fixture
def found(monkeypatch):
    fix_month(monkeypatch)
    return build(FIXTURE_WORKSPACE)


def test_the_fixture_reports(found):
    for version, keywords, folder in (("general", GENERAL_KEYWORDS, "general"),
                                      ("fintech-sre", JOB_KEYWORDS, "jobs/fintech-sre")):
        saved = wsio.read_json(FIXTURE_WORKSPACE / "08-ats" / folder / "report.json")
        assert coverage.cover(resume(version), keywords, found) == saved["keywords"]


def test_statuses_and_where(found):
    report = coverage.cover(resume(), ["Go", "Senior Software Engineer", "State University", "metrics",
                                       "on-call", "PAY-42", "ledger files", "old-resume", "Kubernetes"], found)
    assert [(k["keyword"], k["status"], k["where"]) for k in report] == [
        ("Go", "covered", ["/work/0/x-highlights/0/text", "/work/1/x-highlights/0/text", "/skills/0/keywords/0"]),
        ("Senior Software Engineer", "covered", ["/work/0/position"]),
        ("State University", "covered", ["/education/0/institution"]),
        ("metrics", "missing_with_evidence", ["ev_56410ed1"]),
        ("on-call", "covered", ["/work/0/x-highlights/1/text"]),
        ("PAY-42", "missing_with_evidence", ["ev_191cc8ce", "ev_56410ed1"]),
        ("ledger files", "covered", ["/projects/0/x-highlights/0/text"]),
        ("old-resume", "missing_without_evidence", []),
        ("Kubernetes", "missing_without_evidence", [])]
    assert coverage.counts(report) == {"covered": 5, "missing_with_evidence": 2, "missing_without_evidence": 2}


def test_evidence_includes_left_out_bullets_reviews_metrics_and_the_profile(found):
    shown = resume()
    shown["work"][0]["x-highlights"] = []  # b_1 and b_2 left out
    shown["skills"][0]["keywords"] = ["Go"]
    report = coverage.cover(shown, ["onboarding", "checkout latency", "PostgreSQL", "example.com"], found)
    assert [(k["status"], k["where"]) for k in report] == [
        ("missing_with_evidence", ["b_2", "ev_cbf558fa"]),
        ("missing_with_evidence", ["b_1", "ev_99a74656", "metric:m_1"]),
        ("missing_with_evidence", ["resume:/skills/0/keywords/3"]),
        ("missing_with_evidence", ["wizard:/basics/email"])]


def test_evidence_of_no_project_is_not_evidence(workspace, monkeypatch):
    fix_month(monkeypatch)
    edit_projects = wsio.read_json(workspace / "04-projects" / "projects.json")
    edit_projects[0]["evidence_ids"] = ["ev_191cc8ce", "ev_99a74656"]  # ev_56410ed1 left the project
    wsio.write_json(workspace / "04-projects" / "projects.json", edit_projects)
    report = coverage.cover(resume(), ["metrics"], build(workspace))
    assert report == [{"keyword": "metrics", "status": "missing_without_evidence", "where": []}]


def _draft(workspace, version):
    stages.begin(workspace, "08-ats", from_current=True)
    return Version(version)


def test_keywords_json_checks(workspace):
    job = _draft(workspace, "fintech-sre")
    write_keywords(workspace, "fintech-sre", JOB_KEYWORDS)
    assert check.keywords(workspace, job, "Senior Backend Engineer") == (JOB_KEYWORDS, [])
    write_keywords(workspace, "fintech-sre", ["Go", "golang", "Rust", "slo-compliance", "SLO  compliance"])
    rel = "08-ats.tmp/jobs/fintech-sre/keywords.json"
    assert check.keywords(workspace, job, "")[1] == [
        f"{rel}: 'SLO  compliance' is listed twice (as 'slo-compliance')",
        f"{rel}: 'golang' is not in the posting (08-ats.tmp/jobs/fintech-sre/jd.txt); list only the posting's keywords, "
        "as it spells them",
        f"{rel}: 'Rust' is not in the posting (08-ats.tmp/jobs/fintech-sre/jd.txt); list only the posting's "
        "keywords, as it spells them"]
    write_keywords(workspace, "fintech-sre", [])
    assert check.keywords(workspace, job, "")[1] == [
        f"{rel}: no keywords; list the posting's keywords as it spells them"]
    write_keywords(workspace, "fintech-sre", {"keywords": []})
    assert check.keywords(workspace, job, "")[1] == [f"{rel}: $: expected array, got dict"]


def test_general_keywords_may_be_empty_only_without_a_target_role(workspace):
    general = _draft(workspace, "general")
    write_keywords(workspace, "general", [])
    assert check.keywords(workspace, general, "") == ([], [])
    assert check.keywords(workspace, general, "Senior Backend Engineer")[1] == [
        "08-ats.tmp/general/keywords.json: no keywords; list the keywords an ATS would match for the target role "
        "'Senior Backend Engineer'"]
    write_keywords(workspace, "general", ["Haskell"])  # the general resume has no posting to be found in
    assert check.keywords(workspace, general, "Senior Backend Engineer") == (["Haskell"], [])
