"""Wizard answers a re-import moves to a different entry (rimport.shifts)."""
from rimport.shifts import warnings

NORTHWIND = {"name": "Northwind Payments", "position": "Senior Software Engineer"}
TAILSPIN = {"name": "Tailspin Toys", "position": "Software Engineer"}
CONTOSO = {"name": "Contoso", "position": "Engineer"}
REVIEW = "Review it with /resume-builder:wizard."


def test_no_warning_when_the_answered_entry_stays():
    old = {"work": [NORTHWIND, TAILSPIN]}
    new = {"work": [dict(NORTHWIND, startDate="2023-01"), TAILSPIN]}
    assert warnings(old, new, {"work": [{}, {"endDate": "2022-12"}]}) == []


def test_a_moved_entry_is_named():
    old = {"work": [NORTHWIND, TAILSPIN]}
    new = {"work": [NORTHWIND, CONTOSO, TAILSPIN]}
    assert warnings(old, new, {"work": [{}, {"endDate": "2022-12"}]}) == [
        "decisions/profile.json /work/1 was answered for 'Software Engineer, Tailspin Toys'; after this import "
        f"/work/1 is 'Engineer, Contoso'. {REVIEW}"]


def test_empty_answers_are_ignored():
    old = {"work": [NORTHWIND, TAILSPIN]}
    new = {"work": [TAILSPIN, NORTHWIND]}
    assert warnings(old, new, {"work": [{}, {}]}) == []


def test_an_added_entry_that_now_merges():
    new = {"certificates": [{"name": "AWS Certified Developer", "x-lines": {"first": 3, "last": 3}}]}
    wizard = {"certificates": [{"name": "AWS Certified Solutions Architect - Associate"}]}
    assert warnings({}, new, wizard) == [
        "decisions/profile.json /certificates/0 added a certificates entry; after this import it merges into "
        f"'AWS Certified Developer'. {REVIEW}"]


def test_an_answered_entry_that_is_gone():
    old = {"education": [{"institution": "State University", "studyType": "BS", "area": "Computer Science"}]}
    assert warnings(old, {}, {"education": [{"endDate": "2019"}]}) == [
        "decisions/profile.json /education/0 was answered for 'BS, Computer Science, State University'; after this "
        f"import there is no /education/0, so the answer adds a new entry. {REVIEW}"]


def test_basics_profiles_merge_by_index_too():
    old = {"basics": {"profiles": [{"network": "GitHub", "username": "jrivera"}]}}
    new = {"basics": {"profiles": [{"network": "LinkedIn", "username": "jordanrivera"}]}}
    assert warnings(old, new, {"basics": {"profiles": [{"url": "https://github.com/jrivera"}]}}) == [
        "decisions/profile.json /basics/profiles/0 was answered for 'GitHub, jrivera'; after this import "
        f"/basics/profiles/0 is 'LinkedIn, jordanrivera'. {REVIEW}"]


def test_arrays_that_do_not_merge_by_index_are_skipped():
    old = {"skills": [{"name": "Backend"}]}
    new = {"skills": [{"name": "Data"}]}
    assert warnings(old, new, {"skills": ["Go"]}) == []
    assert warnings(old, new, {}) == []


def test_fixture_decisions_have_no_shifts(workspace):
    import json
    profile = json.loads((workspace / "03-profile" / "profile.json").read_text())
    wizard = json.loads((workspace / "decisions" / "profile.json").read_text())
    assert warnings(profile, profile, wizard) == []
