"""rcore.raw: the text of the raw record at a raw_ref."""
import json

from rcore.raw import RawReader


def test_reads_a_records_text_and_says_why_it_cannot(tmp_path):
    raw = tmp_path / "01-raw"
    raw.mkdir()
    (raw / "reviews.jsonl").write_text(json.dumps({"items": [{"text": "Full review text."}, {"file": "x"}]}) + "\n",
                                       encoding="utf-8")
    reader = RawReader(tmp_path)
    assert reader.text("01-raw/reviews.jsonl:1#/items/0") == ("Full review text.", None)
    assert reader.text("01-raw/reviews.jsonl:1#/items/1") == (None, "has no text")
    assert reader.text("01-raw/reviews.jsonl:1#/items/5") == (None, "does not resolve")
    assert reader.text("01-raw/reviews.jsonl:2#/items/0") == (None, "01-raw/reviews.jsonl has no line 2")
    assert reader.text("01-raw/gone.jsonl:1#/items/0") == (None, "01-raw/gone.jsonl not found")
    assert reader.text(None) == (None, "is not a raw reference")


def test_resume_sanitize_uses_it():
    from rsanitize import texts
    assert texts.RawReader is RawReader
