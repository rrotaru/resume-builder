from rcore.schema import validate

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
