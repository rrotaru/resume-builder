"""The profile faithfulness check (rimport.check)."""
import json

import pytest
from rimport import check
from samples import TEXT, TMP, profile, sha, stage_text

LABEL = "03-profile.tmp/profile.json"


def problems(doc, text=TEXT):
    return check.check_text(doc, text, LABEL)


def test_fixture_profile_passes():
    assert problems(profile()) == []


def test_fixture_stage_passes(workspace):
    assert check.check_stage(workspace, "03-profile") == ([], True)


# Values ----------------------------------------------------------------------

@pytest.mark.parametrize("pointer, value, line", [
    ("/work/0/position", "Staff Engineer",
     "/work/0/position: 'Staff Engineer' is not in resume.txt lines 7-8"),
    ("/work/0/name", "Northwind", None),  # a shorter value copied from the text passes
    ("/education/0/studyType", "PhD",
     "/education/0/studyType: 'PhD' is not in resume.txt lines 22-22"),
    ("/skills/0/keywords/0", "Kubernetes",
     "/skills/0/keywords/0: 'Kubernetes' is not in resume.txt lines 26-26"),
    ("/basics/name", "J. Rivera", "/basics/name: 'J. Rivera' is not in resume.txt"),
    ("/basics/name", "JORDAN RIVERA", None),
    ("/basics/label", "Senior Backend Engineer",
     "/basics/label: 'Senior Backend Engineer' is not in resume.txt"),
])
def test_values_must_be_in_their_scope(pointer, value, line):
    doc = profile()
    parts = pointer.strip("/").split("/")
    node = doc
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    node[int(parts[-1]) if isinstance(node, list) else parts[-1]] = value
    assert problems(doc) == ([f"{LABEL}: {line}"] if line else [])


def test_a_value_from_another_entry_fails():
    doc = profile()
    doc["work"][0]["name"] = "Tailspin Toys"  # true of /work/1, not /work/0
    assert problems(doc) == [f"{LABEL}: /work/0/name: 'Tailspin Toys' is not in resume.txt lines 7-8"]


def test_a_highlight_must_be_copied_word_for_word():
    doc = profile()
    doc["work"][1]["highlights"] = ["Led the migration of the order service from PHP to Go"]
    assert problems(doc) == [
        f"{LABEL}: /work/1/highlights/0: 'Led the migration of the order service from PHP to Go' "
        "is not in resume.txt lines 10-12"]


def test_long_values_are_shortened_in_messages():
    doc = profile()
    doc["projects"][0]["description"] = "x" * 100
    [line] = problems(doc)
    assert line.endswith(f"'{'x' * 57}...' is not in resume.txt lines 16-18")


def test_urls_are_searched_in_the_whole_text():
    doc = profile()
    assert doc["projects"][0]["url"] == "https://github.com/jrivera/ledger-lint"  # only in the links block
    doc["projects"][0]["url"] = "https://github.com/jrivera/other"
    assert problems(doc) == [f"{LABEL}: /projects/0/url: 'https://github.com/jrivera/other' is not in resume.txt"]


def test_phone_and_email_in_basics():
    text = TEXT.replace("github.com/jrivera\n", "github.com/jrivera | (555) 123-4567 | jordan@example.com\n", 1)
    doc = profile()
    doc["basics"].update(phone="555-123-4567", email="jordan@example.com")
    assert problems(doc, text) == []
    doc["basics"]["phone"] = "+1 555 123 4567"
    assert problems(doc, text) == [f"{LABEL}: /basics/phone: '+1 555 123 4567' is not in resume.txt"]


# Dates -----------------------------------------------------------------------

@pytest.mark.parametrize("field, value, line", [
    ("startDate", "2019-06-01",
     "/work/1/startDate: '2019-06-01' is not a date resume.txt lines 10-12 give (they give 2019-06, 2022-12)"),
    ("startDate", "2019-05",
     "/work/1/startDate: '2019-05' is not a date resume.txt lines 10-12 give (they give 2019-06, 2022-12)"),
    ("startDate", "2019", None),  # shortened: still stated
    ("endDate", "2023-01",  # the date of /work/0, not of /work/1
     "/work/1/endDate: '2023-01' is not a date resume.txt lines 10-12 give (they give 2019-06, 2022-12)"),
    ("endDate", "2022-13",
     "/work/1/endDate: '2022-13' is not a real date written YYYY, YYYY-MM or YYYY-MM-DD"),
])
def test_dates_must_be_stated_in_the_entry(field, value, line):
    doc = profile()
    doc["work"][1][field] = value
    assert problems(doc) == ([f"{LABEL}: {line}"] if line else [])


def test_start_after_end_fails():
    text = TEXT.replace("June 2019 – December 2022", "December 2022 – June 2019")
    assert problems(profile(), text) == []  # the dates are stated either way round
    doc = profile()
    doc["work"][1].update(startDate="2022-12", endDate="2019-06")
    assert problems(doc, text) == [f"{LABEL}: /work/1: startDate '2022-12' is after endDate '2019-06'"]


def test_an_open_entry_must_be_ongoing_in_the_text():
    doc = profile()
    del doc["work"][1]["endDate"]  # Tailspin Toys would render as "Present"
    assert problems(doc) == [
        f"{LABEL}: /work/1: no endDate, but resume.txt lines 10-12 do not say it is ongoing (present, current, now, ...)"]


@pytest.mark.parametrize("word", ["Present", "current", "Now", "today", "ongoing", "to date", "Since"])
def test_ongoing_words(word):
    text = TEXT.replace("Jan 2023 – Present", f"Jan 2023 – {word}")
    assert problems(profile(), text) == []


def test_ongoing_needs_a_whole_word():
    text = TEXT.replace("Jan 2023 – Present", "Jan 2023 – presently unknown")
    assert problems(profile(), text) == [
        f"{LABEL}: /work/0: no endDate, but resume.txt lines 7-8 do not say it is ongoing (present, current, now, ...)"]


def test_an_entry_with_only_an_end_date_is_not_open():
    doc = profile()
    doc["education"][0]["endDate"] = "2019"
    assert "startDate" not in doc["education"][0]
    assert problems(doc) == []


# Structure -------------------------------------------------------------------

def test_x_lines_is_required():
    doc = profile()
    del doc["skills"][0]["x-lines"]
    assert problems(doc) == [
        f"{LABEL}: /skills/0: x-lines is missing; give the lines of resume.txt this entry was read from"]


def test_x_lines_must_be_inside_the_text():
    doc = profile()
    doc["skills"][0]["x-lines"] = {"first": 26, "last": 99}
    assert problems(doc) == [f"{LABEL}: /skills/0: x-lines 26-99 is outside resume.txt (lines 1-30)"]
    doc["skills"][0]["x-lines"] = {"first": 26, "last": 25}
    assert problems(doc) == [f"{LABEL}: /skills/0: x-lines 26-25 ends before it starts"]


def test_entries_keep_the_order_of_the_text():
    doc = profile()
    doc["work"].reverse()
    assert problems(doc) == [
        f"{LABEL}: /work/1: x-lines 7-8 come before /work/0 (lines 10-12); keep entries in the order of resume.txt"]


def test_entries_may_share_a_first_line():
    text = TEXT.replace("Backend: Go, Python, Redis, PostgreSQL", "Backend: Go, Python | Data: Redis, PostgreSQL")
    doc = profile()
    doc["skills"] = [
        {"name": "Backend", "keywords": ["Go", "Python"], "x-lines": {"first": 26, "last": 26}},
        {"name": "Data", "keywords": ["Redis", "PostgreSQL"], "x-lines": {"first": 26, "last": 26}},
    ]
    assert problems(doc, text) == []


def test_unknown_section_and_fields():
    doc = profile()
    doc["meta"] = {"version": "v1"}
    doc["work"][0]["company"] = "Northwind Payments"
    doc["basics"]["headline"] = "Backend Engineer"
    doc["basics"]["location"] = {"city": "Denver", "country": "USA"}
    lines = problems(doc)
    assert f"{LABEL}: /meta: not a JSON Resume section (allowed: basics, {', '.join(check.SECTIONS)})" in lines
    assert (f"{LABEL}: /work/0/company: not a work field (allowed: name, position, url, location, description, "
            "startDate, endDate, summary, highlights, x-lines)") in lines
    assert any(line.startswith(f"{LABEL}: /basics/headline: not a basics field") for line in lines)
    assert any(line.startswith(f"{LABEL}: /basics/location/country: not a basics.location field") for line in lines)
    assert f"{LABEL}: /basics/location/city: 'Denver' is not in resume.txt" in lines
    assert len(lines) == 5


def test_other_x_fields_are_not_allowed():
    doc = profile()
    doc["work"][0]["x-sources"] = ["resume:/work/0"]
    assert problems(doc) == [
        f"{LABEL}: /work/0/x-sources: not a work field (allowed: name, position, url, location, description, "
        "startDate, endDate, summary, highlights, x-lines)"]


@pytest.mark.parametrize("value, message", [
    (None, "is null; leave the field out instead"),
    ("", "is empty; leave the field out instead"),
    ("  ", "is empty; leave the field out instead"),
    (3, "must be a string, not int"),
    (["Senior Software Engineer"], "must be a string, not list"),
])
def test_values_must_be_non_empty_strings(value, message):
    doc = profile()
    doc["work"][0]["position"] = value
    assert problems(doc) == [f"{LABEL}: /work/0/position: {message}"]


def test_array_fields_hold_strings():
    doc = profile()
    doc["skills"][0]["keywords"] = "Go"
    assert problems(doc) == [f"{LABEL}: /skills/0/keywords: must be an array of strings"]
    doc["skills"][0]["keywords"] = ["Go", None]
    assert problems(doc) == [f"{LABEL}: /skills/0/keywords/1: is null; leave the field out instead"]


def test_other_json_resume_sections_are_checked():
    text = TEXT + "\nLANGUAGES\nSpanish (fluent)\n"
    doc = profile()
    doc["languages"] = [{"language": "Spanish", "fluency": "fluent", "x-lines": {"first": 32, "last": 33}}]
    assert problems(doc, text) == []
    doc["languages"][0]["fluency"] = "Native speaker"
    assert problems(doc, text) == [f"{LABEL}: /languages/0/fluency: 'Native speaker' is not in resume.txt lines 32-33"]


# Stage -----------------------------------------------------------------------

def test_stage_reports_an_edited_resume_txt(workspace):
    target = stage_text(workspace, TEXT, profile())
    assert check.check_stage(workspace, TMP) == ([], True)
    (target / "resume.txt").write_text(TEXT.replace("Senior Software Engineer", "Staff Engineer"), encoding="utf-8")
    assert check.check_stage(workspace, TMP) == (
        [f"{TMP}/resume.txt: changed after extraction; run extract_text.py again"], False)


def test_stage_validates_before_checking(workspace):
    doc = profile()
    doc["work"][0]["x-lines"] = {"first": 0, "last": 8}
    stage_text(workspace, TEXT, doc)
    lines, fix = check.check_stage(workspace, TMP)
    assert not fix and lines == [f"{TMP}/profile.json: $.work[0].x-lines.first: 0 is less than 1"]


def test_stage_needs_its_files(workspace):
    assert check.check_stage(workspace, TMP) == ([f"{TMP}: not found; run extract_text.py first"], False)
    target = stage_text(workspace, TEXT, profile())
    (target / "profile.json").unlink()
    assert check.check_stage(workspace, TMP) == ([f"{TMP}/profile.json: not found"], False)
    stage_text(workspace, TEXT, profile())
    (target / "resume.txt").unlink()
    assert check.check_stage(workspace, TMP) == (
        [f"{TMP}/resume.txt: not found; run extract_text.py again"], False)


def test_json_stage_must_equal_the_mapping(workspace, tmp_path):
    resume = tmp_path / "resume.json"
    resume.write_text(json.dumps({"basics": {"name": "Jordan Rivera"}, "work": []}), encoding="utf-8")
    target = workspace / TMP
    target.mkdir()
    source = {"path": str(resume), "format": "json", "sha256": sha(resume.read_bytes()), "text_sha256": None}
    (target / "source.json").write_text(json.dumps(source), encoding="utf-8")
    (target / "profile.json").write_text(json.dumps({"basics": {"name": "Jordan Rivera"}, "work": []}),
                                         encoding="utf-8")
    assert check.check_stage(workspace, TMP) == ([], False)

    (target / "profile.json").write_text(json.dumps({"basics": {"name": "Dr. Jordan Rivera"}, "work": []}),
                                         encoding="utf-8")
    assert check.check_stage(workspace, TMP) == (
        [f"{TMP}/profile.json: differs from the JSON Resume mapping; do not edit it, run extract_text.py again"],
        False)

    resume.write_text(json.dumps({"basics": {"name": "Dr. Jordan Rivera"}, "work": []}), encoding="utf-8")
    assert check.check_stage(workspace, TMP) == (
        [f"{resume}: changed since extract_text.py ran; run it again"], False)
    resume.unlink()
    [line], _ = check.check_stage(workspace, TMP)
    assert line.startswith(f"{resume}: cannot be read")


def test_describe_sections():
    assert check.describe_sections(profile()) == "basics, work 2, projects 1, education 1, skills 1"
    assert check.describe_sections({}) == "nothing"
