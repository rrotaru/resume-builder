"""rats.lint: lint rules, experience and the length estimate."""
import copy

import pytest

from ats_samples import build, fix_month
from conftest import FIXTURE_WORKSPACE
from rats import lint
from rcore import wsio


def general():
    return wsio.read_json(FIXTURE_WORKSPACE / "08-ats" / "general" / "resume.json")


@pytest.fixture
def found(monkeypatch):
    fix_month(monkeypatch)
    return build(FIXTURE_WORKSPACE)


# Experience -------------------------------------------------------------------------

@pytest.mark.parametrize("work, months", [
    ([{"startDate": "2019-06", "endDate": "2022-12"}, {"startDate": "2023-01"}], 88),  # the fixture, to 2026-09
    ([{"startDate": "2020-01", "endDate": "2020-12"}, {"startDate": "2020-06", "endDate": "2021-03"}], 15),
    ([{"startDate": "2018", "endDate": "2019"}], 24),  # a year alone: January to December
    ([{"startDate": "2020-01", "endDate": "2020-12"}, {"startDate": "2020-03", "endDate": "2020-04"}], 12),
    ([{"startDate": "2024-01-15", "endDate": "2024-02-01"}], 2),
    ([{"endDate": "2022-12"}, {"name": "no dates"}, "not an entry"], 0),  # no startDate: not counted
    ([{"startDate": "2026-01", "endDate": "2027-12"}], 9),  # an end in the future stops at this month
    ([{"startDate": "2027-01"}], 0),
])
def test_experience_months(work, months):
    assert lint.experience_months({"work": work}, (2026, 9)) == months


def test_budget():
    assert lint.budget(95) == (1, 50)
    assert lint.budget(96) == (2, 100)


# The estimate ------------------------------------------------------------------------

def test_the_estimate_adds_up_the_parts():
    assert lint.estimate({"basics": {"name": "Jordan"}}) == 2  # 1.6
    assert lint.estimate({"basics": {"name": "J", "label": "Engineer", "email": "j@example.com"}}) == 5  # 4.2
    job = {"name": "Northwind", "position": "Engineer", "startDate": "2023-01",
           "x-highlights": [{"bullet_id": "b_1", "text": "x" * 95, "sources": []},
                            {"bullet_id": "b_2", "text": "y" * 96, "sources": []}]}
    # heading 2.4 + title 1 + dates 1 + bullets 0.15 + (0.15 + 1) + (0.15 + 2) + space 0.45 = 8.3, plus 1.6
    assert lint.estimate({"basics": {"name": "J"}, "work": [job]}) == 10
    skills = {"basics": {"name": "J"}, "skills": [{"name": "Backend", "keywords": ["Go"] * 40}]}
    assert lint.estimate(skills) == 7  # 1.6 + 2.4 + 0.15 + 2 lines of 100 characters
    summary = {"basics": {"name": "J", "summary": "s" * 101, "x-summary-sources": ["metric:m_1"]}}
    assert lint.estimate(summary) == 6  # 1.6 + 2.4 + 2
    unsourced = {"basics": {"name": "J", "summary": "s" * 101}}
    assert lint.estimate(unsourced) == 2  # render shows no summary without sources


def test_the_fixture_estimate():
    assert lint.estimate(general()) == 36


# Lint --------------------------------------------------------------------------------

def test_the_fixture_is_clean(found):
    assert lint.lint(general(), found) == ([], [], {"experience_months": 88, "pages": 1, "estimated_lines": 36,
                                                    "line_budget": 50})


@pytest.mark.parametrize("text, error", [
    ("Cut latency\nby half", "/work/0/x-highlights/0: holds a line break or tab; a bullet is one line"),
    ("Cut latency\tby half", "/work/0/x-highlights/0: holds a line break or tab; a bullet is one line"),
    (" Cut latency", "/work/0/x-highlights/0: begins or ends with a space"),
    ("• Cut latency", "/work/0/x-highlights/0: begins with '•'; render adds the bullet"),
    ("- Cut latency", "/work/0/x-highlights/0: begins with '-'; render adds the bullet"),
    ("Cut latency \U0001f680", "/work/0/x-highlights/0: holds '\U0001f680' (U+1F680), which ATS parsers garble"),
    ("Cut latency ★ twice", "/work/0/x-highlights/0: holds '★' (U+2605), which ATS parsers garble"),
    ("Cut latency ", "/work/0/x-highlights/0: holds '\\ue000' (U+E000), which ATS parsers garble"),
    ("Cut latency \x07", "/work/0/x-highlights/0: holds '\\x07' (U+0007), which ATS parsers garble"),
])
def test_bullet_text_errors(found, text, error):
    resume = general()
    resume["work"][0]["x-highlights"][0]["text"] = text
    assert error in lint.lint(resume, found)[0]


def test_text_that_is_fine(found):
    resume = general()
    resume["work"][0]["x-highlights"][0]["text"] = "Cut latency 40% (p99) — at 30°C, naïvely, for C++ users"
    assert lint.lint(resume, found)[0] == []


def test_the_summary_is_linted_too(found):
    resume = general()
    resume["basics"].update(summary="Backend engineer \U0001f680", **{"x-summary-sources": ["metric:m_1"]})
    assert lint.lint(resume, found)[0] == [
        "/basics/summary: holds '\U0001f680' (U+1F680), which ATS parsers garble"]


def test_name_duplicates_and_length(found):
    resume = general()
    resume["basics"]["name"] = " "
    resume["work"][1]["x-highlights"].append(copy.deepcopy(resume["work"][0]["x-highlights"][0]))
    resume["education"].append(copy.deepcopy(resume["education"][0]))
    resume["work"][0]["x-highlights"] += [{"bullet_id": f"b_{n}", "text": "z" * 190, "sources": []}
                                          for n in range(10, 17)]
    errors, _, length = lint.lint(resume, found)
    assert errors == [
        "/basics/name: a resume needs a name; add it with /resume-builder:wizard",
        "/work/1/x-highlights/1: b_1 is already at /work/0/x-highlights/0; use a bullet once",
        "/education/1: copies the profile's /education/0, as /education/0 does; list each entry once",
        f"estimated {length['estimated_lines']} lines, over the 1-page budget of 50 lines (88 months of "
        "experience); leave out the weakest bullets or entries"]
    assert length["estimated_lines"] > 50


def test_warnings(found):
    resume = general()
    del resume["basics"]["email"]
    resume["work"].reverse()
    del resume["work"][0]["startDate"]  # no longer copies the profile's job: also left out
    resume["work"][1]["x-highlights"][1]["text"] = "w" * 201
    resume["projects"][0]["x-highlights"] = []
    resume["skills"][0].pop("keywords")
    errors, warnings, _ = lint.lint(resume, found)
    assert errors == []
    assert warnings == [
        "/basics: no email and no phone; add one with /resume-builder:wizard so recruiters can reach the engineer",
        "/work/1: Senior Software Engineer, Northwind Payments is more recent than /work/0; list jobs most recent "
        "first",
        "the profile's /work/1 (Software Engineer, Tailspin Toys) is left out; a gap in the dates can read as a gap "
        "in employment",
        "/work/0: Software Engineer, Tailspin Toys has no start date; ATS parsers compute experience from dates; add "
        "it with /resume-builder:wizard",
        "/work/1/x-highlights/1: 201 characters; a bullet over two lines is hard to scan",
        "/projects/0: ledger-lint has no bullets",
        "no skill keywords: an ATS matches skills by keyword; add them with /resume-builder:wizard"]


def test_an_ongoing_job_is_the_most_recent(found):
    resume = general()
    resume["work"][0]["endDate"] = "2024-01"  # no longer the profile's job, but the order rule still reads it
    resume["work"].insert(0, {"name": "Other", "position": "Engineer", "startDate": "2020-01",
                              "x-highlights": []})
    warnings = lint.lint(resume, found)[1]
    assert not any("more recent" in w for w in warnings)
    resume["work"].append(resume["work"].pop(0))
    assert "/work/2: Engineer, Other is more recent than /work/1; list jobs most recent first" in \
        lint.lint(resume, found)[1]
