"""Loading a JSON Resume file (rimport.jsonresume)."""
import json

from rimport import jsonresume


def load(doc):
    return jsonresume.load(json.dumps(doc).encode("utf-8"))


def test_keeps_order_sections_and_unknown_fields():
    doc = {
        "basics": {"name": "Jordan Rivera", "label": "Backend Engineer"},
        "work": [{"name": "Tailspin Toys", "position": "Software Engineer", "startDate": "2019-06",
                  "endDate": "2022-12", "custom": "kept"},
                 {"name": "Northwind Payments", "position": "Senior Software Engineer", "startDate": "2023-01"}],
        "volunteer": [{"organization": "Code Club"}],
        "hobbies": ["kept too"],
    }
    assert load(doc) == (doc, [], [])


def test_drops_file_metadata_x_keys_and_empty_values():
    doc = {
        "$schema": "https://raw.githubusercontent.com/jsonresume/resume-schema/v1.0.0/schema.json",
        "meta": {"version": "v1.0.0"},
        "basics": {"name": "Jordan Rivera", "email": "", "phone": None, "x-note": "private"},
        "work": [{"name": "Tailspin Toys", "summary": "", "highlights": ["Did a thing", ""],
                  "x-lines": {"first": 1, "last": 2}}],
        "x-extra": [],
    }
    profile, notes, errors = load(doc)
    assert errors == []
    assert profile == {"basics": {"name": "Jordan Rivera"},
                       "work": [{"name": "Tailspin Toys", "highlights": ["Did a thing"]}]}
    assert notes == ["dropped /$schema", "dropped /meta", "dropped /basics/x-note", "dropped /work/0/x-lines",
                     "dropped /x-extra", "dropped 4 empty values"]


def test_a_nested_meta_is_not_file_metadata():
    profile, notes, _ = load({"projects": [{"name": "x", "meta": "kept"}]})
    assert profile == {"projects": [{"name": "x", "meta": "kept"}]} and notes == []


def test_timestamps_are_cut_to_their_date():
    profile, _, errors = load({"work": [{"startDate": "2019-06-01T00:00:00.000Z", "endDate": "2022-12"}]})
    assert errors == [] and profile["work"][0] == {"startDate": "2019-06-01", "endDate": "2022-12"}


def test_other_dates_are_errors_never_dropped():
    profile, _, errors = load({"work": [{"startDate": "June 2019", "endDate": "2022-02-30"}],
                               "awards": [{"date": 2020}]})
    assert profile is None
    assert errors == [
        "/work/0/startDate: date 'June 2019' is not YYYY, YYYY-MM or YYYY-MM-DD; fix it in the file",
        "/work/0/endDate: date '2022-02-30' is not YYYY, YYYY-MM or YYYY-MM-DD; fix it in the file",
        "/awards/0/date: date 2020 is not YYYY, YYYY-MM or YYYY-MM-DD; fix it in the file",
    ]


def test_the_result_must_match_the_resume_schema():
    profile, _, errors = load({"work": ["Staff Engineer at Google"]})
    assert profile is None and errors == ["$.work[0]: expected object, got str"]


def test_file_must_be_a_json_object():
    assert jsonresume.load(b"[]") == (None, [], ["a JSON Resume file must hold a JSON object"])
    assert jsonresume.load(b"\xff\xfe") == (None, [], ["not UTF-8 text; save it as UTF-8"])
    _, _, [error] = jsonresume.load(b"{")
    assert error.startswith("invalid JSON: ")


def test_a_bom_is_allowed():
    assert jsonresume.load(b"\xef\xbb\xbf" + b'{"basics": {"name": "Jordan"}}')[0] == {"basics": {"name": "Jordan"}}
