"""Timestamps, excerpts, the time range and raw pages."""
import pytest

from rcollect.common import (CollectError, excerpt, in_range, load_config, names, parse_timestamp,
                             read_pages)
from collect_samples import set_config, write_lines


@pytest.mark.parametrize("value, expected", [
    ("2025-03-04T17:12:00Z", "2025-03-04T17:12:00Z"),
    ("2025-03-04T17:12:00.123456Z", "2025-03-04T17:12:00Z"),
    ("2025-03-04T17:12:00+02:00", "2025-03-04T15:12:00Z"),
    ("2025-03-04T01:12:00-0500", "2025-03-04T06:12:00Z"),
    ("2025-02-10T00:00:00.000+0000", "2025-02-10T00:00:00Z"),
    ("2025-03-04T17:12Z", "2025-03-04T17:12:00Z"),
    ("2025-03-04 17:12", "2025-03-04T17:12:00Z"),
    ("2025-03-04 17:12:09", "2025-03-04T17:12:09Z"),
    ("2025-03-04", "2025-03-04T00:00:00Z"),
    ("2025-12-31T23:30:00-01:00", "2026-01-01T00:30:00Z"),
    ("10/Feb/25 12:00 AM", "2025-02-10T00:00:00Z"),
    ("10/Feb/25 12:00 PM", "2025-02-10T12:00:00Z"),
    ("2/jun/2025 9:15 pm", "2025-06-02T21:15:00Z"),
    ("02/Jun/25 21:15", "2025-06-02T21:15:00Z"),
    (" 2025-03-04T17:12:00Z ", "2025-03-04T17:12:00Z"),
])
def test_timestamps(value, expected):
    assert parse_timestamp(value) == expected


@pytest.mark.parametrize("value", [
    None, 20250304, "", "yesterday", "2025-02-30", "2025-13-01T00:00:00Z", "2025-03-04T24:00:00Z",
    "2025-03-04T17:12:00+25:00", "2025-03-04Tgarbage", "03/04/2025", "10/Foo/25 12:00 AM",
    "10/Feb/25 13:00 PM", "10/Feb/25 0:00 AM", "Feb 10, 2025",
])
def test_rejected_timestamps(value):
    assert parse_timestamp(value) is None


def test_excerpt_drops_comments_collapses_whitespace_and_cuts():
    body = "<!-- template: describe the change -->\r\nAdds a cache.\n\n\tFast   now.<!-- trailing"
    assert excerpt(body) == "Adds a cache. Fast now."
    assert excerpt("x" * 600) == "x" * 500
    assert excerpt(None) == "" and excerpt(42) == ""
    assert excerpt("a b") == "a b"


def test_names_reads_strings_objects_and_graphql_nodes():
    assert names([{"name": "perf"}, "perf", {"name": " a  b "}, 3, None], "name") == ["perf", "a b"]
    assert names({"nodes": [{"login": "x"}]}, "login") == ["x"]
    assert names(None) == []


@pytest.mark.parametrize("created, closed, span, kept", [
    ("2025-03-01T00:00:00Z", None, {"start": None, "end": None}, True),
    ("2022-06-01T00:00:00Z", "2022-12-31T23:00:00Z", {"start": "2023-01-01", "end": None}, False),
    ("2022-06-01T00:00:00Z", "2023-01-01T08:00:00Z", {"start": "2023-01-01", "end": None}, True),
    ("2022-06-01T00:00:00Z", None, {"start": "2023-01-01", "end": None}, True),  # still open
    ("2025-01-01T00:00:00Z", None, {"start": None, "end": "2024-12-31"}, False),
    ("2024-12-31T23:59:59Z", None, {"start": None, "end": "2024-12-31"}, True),
])
def test_time_range(created, closed, span, kept):
    assert in_range(created, closed, span) is kept


def test_read_pages(tmp_path):
    path = write_lines(tmp_path / "raw.jsonl", [
        {"query": "q1", "items": [{"a": 1}], "cursor": "2"},
        "",
        "{oops",
        [1, 2],
        {"items": "not a list"},
        {"export": "/x.jsonl", "row": 7, "error": "invalid JSON: Expecting value", "items": []},
        '{"items": [{"t": "a b"}]}',
    ])
    pages = read_pages(path)
    assert [(p.line, p.query, p.error) for p in pages] == [
        (1, "q1", None),
        (3, None, "invalid JSON: Expecting property name enclosed in double quotes"),
        (4, None, 'not a page: expected an object with an "items" array'),
        (5, None, 'not a page: expected an object with an "items" array'),
        (6, None, "export row 7: invalid JSON: Expecting value"),
        (7, None, None),
    ]
    assert pages[0].items == [{"a": 1}] and pages[-1].items == [{"t": "a b"}]


def test_read_pages_rejects_non_utf8(tmp_path):
    path = tmp_path / "raw.jsonl"
    path.write_bytes(b'{"items": ["\xff"]}\n')
    with pytest.raises(CollectError, match="not UTF-8 text"):
        read_pages(path)


def test_load_config_guards_the_notice(workspace, tmp_path):
    assert load_config(workspace)["sources"][0]["type"] == "github"
    set_config(workspace, data_notice_acknowledged_at=None)
    with pytest.raises(CollectError, match="the data notice has not been accepted"):
        load_config(workspace)
    assert load_config(workspace, need_notice=False)["data_notice_acknowledged_at"] is None
    set_config(workspace, time_range={"start": "2023-1-1", "end": None})
    with pytest.raises(CollectError, match="config.json is not valid"):
        load_config(workspace, need_notice=False)
    with pytest.raises(CollectError, match="not found; run /resume-builder:init first"):
        load_config(tmp_path / "nowhere")
