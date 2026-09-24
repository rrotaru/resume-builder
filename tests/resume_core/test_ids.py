import re

from rcore import ids


def test_evidence_id_format_and_stability():
    first = ids.evidence_id("github", "northwind/ledger#101")
    assert first == "ev_191cc8ce"
    assert ids.evidence_id("github", "northwind/ledger#101") == first
    assert re.fullmatch(r"ev_[0-9a-f]{8}", first)


def test_source_is_part_of_the_key():
    assert ids.evidence_id("github", "PAY-42") != ids.evidence_id("jira", "PAY-42")


def test_assign_extends_only_colliding_ids(monkeypatch):
    real = ids.evidence_id

    def fake(source, native_key, length=ids.SHORT_LENGTH):
        if length == ids.SHORT_LENGTH and native_key in {"a", "b"}:
            return "ev_00000000"
        return real(source, native_key, length)

    monkeypatch.setattr(ids, "evidence_id", fake)
    result = ids.assign_evidence_ids([("git", "a"), ("git", "b"), ("git", "c"), ("git", "a")])
    assert len(result) == 3
    assert result[("git", "a")] == real("git", "a", 12)
    assert result[("git", "b")] == real("git", "b", 12)
    assert result[("git", "c")] == real("git", "c")


def test_project_id_ignores_order_and_duplicates():
    a = ids.project_id(["ev_191cc8ce", "ev_56410ed1", "ev_99a74656"])
    assert a == "pj_da2a2b53"
    assert ids.project_id(["ev_99a74656", "ev_191cc8ce", "ev_56410ed1", "ev_191cc8ce"]) == a


def test_text_sha256_is_hex_digest():
    assert ids.text_sha256("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
