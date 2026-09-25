"""Minimal JSON Schema validator (standard library only).

Supports the subset used by resume-core schemas: type, const, enum, anyOf,
required, properties, additionalProperties, items, minItems, pattern,
minLength, minimum, maximum and local references ("#/$defs/<name>").
load_schema rejects any other keyword, so a schema can never silently rely
on a rule this validator does not enforce.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"

_PY_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "null": type(None),
}


SUPPORTED_KEYWORDS = frozenset({
    "$schema", "title", "description", "$defs", "$ref", "type", "const", "enum", "anyOf",
    "required", "properties", "additionalProperties", "items", "minItems", "pattern",
    "minLength", "minimum", "maximum",
})


def _has_inner_dollar(pattern: str) -> bool:
    """True if pattern has an unescaped $ anywhere but its last character.

    _search turns only a final $ into end-of-string; any other $ would keep
    re's "before a trailing newline" meaning, so it is not allowed.
    """
    escaped = False
    for i, char in enumerate(pattern):
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "$" and i != len(pattern) - 1:
            return True
    return False


def check_schema(node, name: str, path: str = "#") -> None:
    """Raise ValueError if a schema uses a keyword outside SUPPORTED_KEYWORDS.

    Walks only schema positions: the schema itself, each value under
    properties and $defs, items, a schema-valued additionalProperties and
    each anyOf branch. Property names and const/enum values are data.
    Also rejects a pattern with an unescaped $ anywhere but at the very end.
    """
    if not isinstance(node, dict):
        raise ValueError(f"{name}: expected a schema object at {path}")
    for key in node:
        if key not in SUPPORTED_KEYWORDS:
            raise ValueError(f"{name}: unsupported keyword '{key}' at {path}")
    if isinstance(node.get("pattern"), str) and _has_inner_dollar(node["pattern"]):
        raise ValueError(f"{name}: pattern may use an unescaped '$' only at the end, at {path}")
    for key in ("properties", "$defs"):
        for child, sub in node.get(key, {}).items():
            check_schema(sub, name, f"{path}/{key}/{child}")
    if "items" in node:
        check_schema(node["items"], name, f"{path}/items")
    if isinstance(node.get("additionalProperties"), dict):
        check_schema(node["additionalProperties"], name, f"{path}/additionalProperties")
    for i, sub in enumerate(node.get("anyOf", [])):
        check_schema(sub, name, f"{path}/anyOf/{i}")


def load_schema(name: str) -> dict:
    """Load schemas/<name>.schema.json, rejecting unsupported keywords."""
    spec = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
    check_schema(spec, name)
    return spec


def _is_type(value, type_name: str) -> bool:
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _PY_TYPES[type_name])


def _json_equal(a, b) -> bool:
    """JSON equality: booleans never equal numbers; 1 equals 1.0."""
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_json_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_json_equal(a[k], b[k]) for k in a)
    return type(a) is type(b) and a == b


def _search(pattern: str, text: str) -> bool:
    """re.search, except a trailing unescaped $ means end of string (no trailing newline)."""
    if pattern.endswith("$"):
        backslashes = len(pattern[:-1]) - len(pattern[:-1].rstrip("\\"))
        if backslashes % 2 == 0:
            pattern = pattern[:-1] + r"\Z"
    return re.search(pattern, text) is not None


def _resolve_ref(ref: str, root: dict) -> dict:
    prefix = "#/$defs/"
    if not ref.startswith(prefix):
        raise ValueError(f"unsupported $ref: {ref}")
    return root["$defs"][ref[len(prefix):]]


def validate(instance, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    """Return a list of error strings; an empty list means the instance is valid."""
    root = schema if root is None else root
    if "$ref" in schema:
        return validate(instance, _resolve_ref(schema["$ref"], root), root, path)

    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(instance, t) for t in types):
            return [f"{path}: expected {' or '.join(types)}, got {type(instance).__name__}"]

    errors: list[str] = []
    if "const" in schema and not _json_equal(instance, schema["const"]):
        errors.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and not any(_json_equal(instance, v) for v in schema["enum"]):
        errors.append(f"{path}: {instance!r} is not one of {schema['enum']}")
    if "anyOf" in schema and all(validate(instance, s, root, path) for s in schema["anyOf"]):
        errors.append(f"{path}: does not match any allowed form")

    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            errors.append(f"{path}: shorter than {schema['minLength']} characters")
        if "pattern" in schema and not _search(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} does not match {schema['pattern']}")

    if _is_type(instance, "number"):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} is less than {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: {instance} is greater than {schema['maximum']}")

    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            errors.append(f"{path}: needs at least {schema['minItems']} items")
        if "items" in schema:
            for i, item in enumerate(instance):
                errors += validate(item, schema["items"], root, f"{path}[{i}]")

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, value in instance.items():
            child = f"{path}.{key}"
            if key in props:
                errors += validate(value, props[key], root, child)
            elif extra is False:
                errors.append(f"{child}: unexpected property")
            elif isinstance(extra, dict):
                errors += validate(value, extra, root, child)
    return errors
