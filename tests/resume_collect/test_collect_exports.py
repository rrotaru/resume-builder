"""Export files turned into raw pages."""
import json

import pytest

from rcollect import exports
from rcollect.common import CollectError


def write(tmp_path, name, text, encoding="utf-8"):
    path = tmp_path / name
    path.write_bytes(text.encode(encoding) if isinstance(text, str) else text)
    return path


def test_csv_rows_with_repeated_headers_and_multiline_cells(tmp_path):
    path = write(tmp_path, "jira.csv", "﻿Summary,Issue key,Labels,Labels,Description\n"
                                       "One,PAY-1,a,,\"two\nlines\"\n"
                                       "\n"
                                       "Two,PAY-2,,b,plain\n")
    pages = exports.load(path, "jira")
    assert pages == [
        {"export": str(path), "row": 2, "items": [
            {"Summary": "One", "Issue key": "PAY-1", "Labels": ["a"], "Description": "two\nlines"}]},
        {"export": str(path), "row": 5, "items": [
            {"Summary": "Two", "Issue key": "PAY-2", "Labels": ["b"], "Description": "plain"}]},
    ]


def test_csv_is_for_jira_only_and_must_be_utf8(tmp_path):
    with pytest.raises(CollectError, match="CSV exports are read for Jira only"):
        exports.load(write(tmp_path, "gh.csv", "a\n1\n"), "github")
    with pytest.raises(CollectError, match="not UTF-8 text"):
        exports.load(write(tmp_path, "j.csv", b"Summary\n\xff\n"), "jira")
    with pytest.raises(CollectError, match="empty CSV file"):
        exports.load(write(tmp_path, "e.csv", "\n\n"), "jira")
    with pytest.raises(CollectError, match="unsupported export format '.xml'"):
        exports.load(write(tmp_path, "x.xml", "<a/>"), "jira")


def test_json_arrays_pages_and_arrays_of_pages(tmp_path):
    items = [{"number": 1}, {"number": 2}]
    assert exports.load(write(tmp_path, "a.json", json.dumps(items)), "github") == [
        {"export": str(tmp_path / "a.json"), "row": 1, "items": [{"number": 1}]},
        {"export": str(tmp_path / "a.json"), "row": 2, "items": [{"number": 2}]},
    ]
    page = {"total_count": 2, "items": items}
    assert [p["row"] for p in exports.load(write(tmp_path, "p.json", json.dumps(page)), "github")] == [1, 2]
    pages = [{"query": "author:jrivera", "items": items[:1]}, {"query": "reviewed-by:jrivera", "items": items[1:]}]
    loaded = exports.load(write(tmp_path, "pp.json", json.dumps(pages)), "github")
    assert [(p["query"], p["row"]) for p in loaded] == [("author:jrivera", 1), ("reviewed-by:jrivera", 2)]
    jira = {"startAt": 0, "issues": [{"key": "PAY-1"}]}
    assert exports.load(write(tmp_path, "j.json", json.dumps(jira)), "jira")[0]["items"] == [{"key": "PAY-1"}]
    with pytest.raises(CollectError, match="expected an array of items"):
        exports.load(write(tmp_path, "o.json", '{"number": 1}'), "github")
    with pytest.raises(CollectError, match="not valid JSON"):
        exports.load(write(tmp_path, "b.json", "[1,"), "github")


def test_jsonl_lines_items_and_pages_with_bad_lines_kept_as_errors(tmp_path):
    text = '{"iid": 1}\n\n{oops\n{"query": "q", "items": [{"iid": 2}, {"iid": 3}]}\n[{"iid": 4}]\n'
    path = write(tmp_path, "gl.ndjson", text)
    pages = exports.load(path, "gitlab")
    assert [(p["row"], p.get("query"), p["items"], "error" in p) for p in pages] == [
        (1, None, [{"iid": 1}], False),
        (3, None, [], True),
        (4, "q", [{"iid": 2}], False),
        (4, "q", [{"iid": 3}], False),
        (5, None, [{"iid": 4}], False),
    ]
    assert pages[1]["error"].startswith("invalid JSON: ")
