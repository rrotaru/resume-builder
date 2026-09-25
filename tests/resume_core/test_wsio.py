import pytest

from rcore import wsio


def test_jsonl_round_trip(tmp_path):
    path = tmp_path / "x" / "items.jsonl"
    wsio.write_jsonl(path, [{"b": 1, "a": "é"}, {"c": None}])
    assert path.read_text(encoding="utf-8") == '{"a": "é", "b": 1}\n{"c": null}\n'
    assert wsio.read_jsonl(path) == [{"a": "é", "b": 1}, {"c": None}]


def test_read_jsonl_names_bad_line(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"a": 1}\n\n{oops}\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"bad.jsonl:3: invalid JSON"):
        wsio.read_jsonl(path)


def test_json_round_trip(tmp_path):
    path = tmp_path / "d" / "x.json"
    wsio.write_json(path, {"k": [1, 2]})
    assert path.read_text(encoding="utf-8").endswith("\n")
    assert wsio.read_json(path) == {"k": [1, 2]}


def test_resolve_pointer():
    doc = {"work": [{"highlights": ["a", "b"]}], "a/b": {"m~n": 1}}
    assert wsio.resolve_pointer(doc, "") is doc
    assert wsio.resolve_pointer(doc, "/work/0/highlights/1") == "b"
    assert wsio.resolve_pointer(doc, "/a~1b/m~0n") == 1
    for bad in ["/work/1", "/work/x", "/missing", "work/0"]:
        with pytest.raises(KeyError):
            wsio.resolve_pointer(doc, bad)


def test_iter_strings_yields_values_not_keys():
    doc = {"basics": {"name": "J"}, "tags": ["x", 3], "a/b": "y"}
    assert list(wsio.iter_strings(doc)) == [("/basics/name", "J"), ("/tags/0", "x"), ("/a~1b", "y")]


def test_resume_highlights():
    resume = {"work": [{"x-highlights": [{"bullet_id": "b_1"}]}],
              "projects": [{}, {"x-highlights": [{"bullet_id": "b_2"}]}]}
    assert [(p, h["bullet_id"]) for p, h in wsio.resume_highlights(resume)] == [
        ("/work/0/x-highlights/0", "b_1"),
        ("/projects/1/x-highlights/0", "b_2"),
    ]


def test_load_reports_problems_as_lines(tmp_path):
    (tmp_path / "ok.json").write_text('{"a": 1}', encoding="utf-8")
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    (tmp_path / "bad.jsonl").write_text('{"a": 1}\n{oops}\n', encoding="utf-8")
    (tmp_path / "bin.txt").write_bytes(b"\xff\xfe")
    assert wsio.load(tmp_path, "ok.json") == ({"a": 1}, None)
    assert wsio.load(tmp_path, "nope.json") == (None, "nope.json: not found")
    assert wsio.load(tmp_path, "bad.json")[1].startswith("bad.json: invalid JSON: ")
    assert wsio.load(tmp_path, "bad.jsonl", "jsonl")[1].startswith("bad.jsonl: invalid JSON on line 2: ")
    assert wsio.load(tmp_path, "bin.txt", "text") == (None, "bin.txt: not UTF-8 text")
