import pytest

from rcore import schema as schema_module
from rcore.schema import check_schema, validate

OBJ = {
    "type": "object",
    "required": ["id"],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": "^ev_[0-9a-f]{8}$"},
        "count": {"type": "integer", "minimum": 0},
        "kind": {"enum": ["pr", "mr"]},
        "tags": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/tag"}},
        "note": {"type": ["string", "null"]},
    },
    "$defs": {"tag": {"type": "string", "minLength": 2}},
}


def test_valid_instance_has_no_errors():
    assert validate({"id": "ev_0123abcd", "count": 2, "kind": "pr", "tags": ["ab"], "note": None}, OBJ) == []


def test_missing_required_and_unexpected_property():
    errors = validate({"extra": 1}, OBJ)
    assert "$: missing required property 'id'" in errors
    assert "$.extra: unexpected property" in errors


def test_pattern_enum_minimum():
    errors = validate({"id": "ev_XYZ", "count": -1, "kind": "commit"}, OBJ)
    assert any(e.startswith("$.id:") and "does not match" in e for e in errors)
    assert "$.count: -1 is less than 0" in errors
    assert any(e.startswith("$.kind:") and "is not one of" in e for e in errors)


def test_bool_is_not_integer():
    assert validate({"id": "ev_0123abcd", "count": True}, OBJ) == ["$.count: expected integer, got bool"]


def test_items_ref_and_min_items_report_paths():
    errors = validate({"id": "ev_0123abcd", "tags": ["ok", "x"]}, OBJ)
    assert errors == ["$.tags[1]: shorter than 2 characters"]
    assert validate({"id": "ev_0123abcd", "tags": []}, OBJ) == ["$.tags: needs at least 1 items"]


def test_any_of():
    schema = {"anyOf": [{"type": "string"}, {"type": "integer"}]}
    assert validate("a", schema) == []
    assert validate(1.5, schema) == ["$: does not match any allowed form"]


def test_additional_properties_schema():
    schema = {"type": "object", "additionalProperties": {"type": "string"}}
    assert validate({"a": "x", "b": 1}, schema) == ["$.b: expected string, got int"]


def test_pattern_trailing_dollar_rejects_trailing_newline():
    schema = {"type": "string", "pattern": "^b_[0-9]+$"}
    assert validate("b_1", schema) == []
    assert validate("b_1\n", schema) != []
    assert validate("a$", {"pattern": "a\\$"}) == []


def test_const_and_enum_compare_types_strictly():
    assert validate(True, {"const": 1}) != []
    assert validate(True, {"enum": [1]}) != []
    assert validate(1, {"const": True}) != []
    assert validate(0, {"enum": [False]}) != []
    assert validate(1, {"const": 1}) == []
    assert validate(1.0, {"const": 1}) == []
    assert validate(True, {"enum": [True]}) == []
    assert validate([1], {"const": [True]}) != []
    assert validate({"a": 1}, {"const": {"a": 1}}) == []


def test_unsupported_keyword_is_rejected():
    with pytest.raises(ValueError, match=r"x: unsupported keyword 'maxLength' at #"):
        check_schema({"maxLength": 3}, "x")
    with pytest.raises(ValueError, match=r"unsupported keyword 'format' at #/properties/a/items"):
        check_schema({"properties": {"a": {"items": {"format": "date"}}}}, "x")
    with pytest.raises(ValueError, match=r"unsupported keyword 'oneOf' at #/\$defs/d/anyOf/0"):
        check_schema({"$defs": {"d": {"anyOf": [{"oneOf": []}]}}}, "x")


def test_property_names_are_not_keywords():
    check_schema({"properties": {"maxLength": {"type": "string"}, "format": {}},
                  "$defs": {"oneOf": {"type": "string"}},
                  "additionalProperties": {"enum": [{"format": 1}]}}, "x")


def test_load_schema_rejects_unsupported_keywords(tmp_path, monkeypatch):
    (tmp_path / "bad.schema.json").write_text('{"maxLength": 3}', encoding="utf-8")
    monkeypatch.setattr(schema_module, "SCHEMA_DIR", tmp_path)
    with pytest.raises(ValueError, match="bad: unsupported keyword 'maxLength' at #"):
        schema_module.load_schema("bad")


def test_pattern_with_unescaped_dollar_before_the_end_is_rejected():
    with pytest.raises(ValueError, match=r"x: pattern may use an unescaped '\$' only at the end, at #/properties/a"):
        check_schema({"properties": {"a": {"type": "string", "pattern": "^a$|^b$"}}}, "x")
    with pytest.raises(ValueError, match=r"unescaped '\$'"):
        check_schema({"pattern": "^a\\\\$b$"}, "x")  # escaped backslash, then a bare $
    check_schema({"pattern": "^a\\$b$"}, "x")
    check_schema({"pattern": "^a$"}, "x")
    check_schema({"pattern": "^a\\\\$"}, "x")
