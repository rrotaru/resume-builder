# resume-core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared `resume-core` skill (workspace data formats, stage lifecycle and the three hard checks) plus the `resume-init` skill that creates a workspace. Every later resume-builder skill depends on these.

**Architecture:** A standard-library-only Python package, `rcore`, lives in `skills/resume-core/scripts/rcore/`. Thin command-line scripts next to it (`validate.py`, `stage.py`, `check_*.py`, `init_workspace.py`) are what skills call with `uv run`. JSON Schemas in `skills/resume-core/schemas/` define every workspace file, and a small built-in validator enforces them, because the spec forbids third-party packages in check scripts. A made-up engineer's workspace in `tests/fixtures/workspace/` drives the tests.

**Tech Stack:** Python ≥ 3.10 (standard library only), uv, pytest (test-only, via `uv run --with pytest`), JSON Schema (2020-12 subset), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-24-resume-builder-architecture-design.md`

## Global Constraints

- Python ≥ 3.10. Every script is run with `uv run`. Every command-line script starts with a PEP 723 block declaring `requires-python = ">=3.10"` and `dependencies = []`.
- Code in `skills/resume-core/` imports only the Python standard library. No `jsonschema`, `pyyaml` or anything else.
- A skill folder contains only `SKILL.md`, `scripts/`, `references/`, `templates/`, `schemas/`. Skills refer to other skills only through `../resume-core/`. Never use `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PROJECT_DIR` or `$ARGUMENTS`.
- Every command-line script accepts `--workspace` (default `resume-workspace`). Paths passed to scripts are relative to the workspace.
- Stage names are exactly: `01-raw`, `02-evidence`, `03-profile`, `04-projects`, `05-terms`, `06-bullets`, `07-sanitized`, `08-ats`, `out`.
- Evidence ID = `ev_` + first 8 hex chars of sha256(`"<source>:<native_key>"`), extended to 12 hex chars only for IDs that collide.
- Metric prompt count: `N = min(project_count, clamp(ceil(0.30 × project_count), 3, 8))`, with percent, minimum and maximum configurable.
- Checks print one line per problem (file, record, rule) and exit 1 on failure. Never weaken or skip a check to make a test pass.
- Regenerating a stage never writes to `decisions/`.
- Run tests from the repository root with `uv run --with pytest pytest`.

## File Structure

| Path | Responsibility |
|---|---|
| `pytest.ini`, `.gitignore` | Test configuration (puts `skills/resume-core/scripts` on the import path); ignore caches and local workspaces |
| `tests/conftest.py` | `workspace` fixture: a disposable copy of the fixture workspace |
| `skills/resume-core/scripts/rcore/schema.py` | Minimal JSON Schema validator and schema loader |
| `skills/resume-core/scripts/rcore/wsio.py` | JSON/JSONL read and write, JSON Pointer, string traversal, resume highlight traversal |
| `skills/resume-core/scripts/rcore/ids.py` | Evidence IDs, project IDs, text hashes |
| `skills/resume-core/scripts/rcore/config.py` | Default `config.json`, metric prompt count rule |
| `skills/resume-core/scripts/rcore/validation.py` | Map workspace paths to schemas; validate files, folders, workspaces |
| `skills/resume-core/scripts/rcore/stages.py` | `begin` / `commit` / `status` stage lifecycle with input hashes |
| `skills/resume-core/scripts/rcore/sources.py` | Source check |
| `skills/resume-core/scripts/rcore/terms.py` | Terms (confidentiality) check |
| `skills/resume-core/scripts/rcore/flags.py` | Job-version flags check |
| `skills/resume-core/scripts/rcore/workspace.py` | Create a workspace; exclude it from git |
| `skills/resume-core/scripts/*.py` | Command-line wrappers: `validate.py`, `stage.py`, `check_sources.py`, `check_terms.py`, `check_flags.py`, `init_workspace.py` |
| `skills/resume-core/schemas/*.schema.json` | One schema per workspace file type (12 files) |
| `skills/resume-core/SKILL.md`, `skills/resume-init/SKILL.md` | Agent instructions |
| `tests/fixtures/workspace/` | Made-up engineer "Jordan Rivera": complete, valid workspace |
| `tests/resume_core/test_*.py`, `tests/test_skill_lint.py` | Tests |
| `.github/workflows/test.yml` | CI on Python 3.10 and 3.13 |

---

### Task 1: Test harness and schema validator

**Files:**
- Create: `pytest.ini`, `.gitignore`, `tests/conftest.py`
- Create: `skills/resume-core/scripts/rcore/__init__.py`, `skills/resume-core/scripts/rcore/schema.py`
- Test: `tests/resume_core/test_schema.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `rcore.schema.validate(instance, schema: dict, root: dict | None = None, path: str = "$") -> list[str]`. Returns error strings such as `"$.tags[1]: shorter than 2 characters"`; an empty list means valid.
  - `rcore.schema.load_schema(name: str) -> dict`. Loads `skills/resume-core/schemas/<name>.schema.json`.
  - `rcore.schema.SCHEMA_DIR: Path`.
  - `tests/conftest.py`: constants `REPO`, `FIXTURE_WORKSPACE`, `CORE_SCRIPTS`, and the `workspace` fixture (a `Path` to a private copy of `tests/fixtures/workspace/`, which Task 4 creates).

- [ ] **Step 1: Create the test configuration**

`pytest.ini`:
```ini
[pytest]
testpaths = tests
pythonpath = skills/resume-core/scripts
addopts = -q
```

`.gitignore`:
```gitignore
__pycache__/
.pytest_cache/
.venv/
resume-workspace/
```

`tests/conftest.py`:
```python
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURE_WORKSPACE = REPO / "tests" / "fixtures" / "workspace"
CORE_SCRIPTS = REPO / "skills" / "resume-core" / "scripts"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A private copy of the fixture workspace that a test may modify."""
    target = tmp_path / "ws"
    shutil.copytree(FIXTURE_WORKSPACE, target)
    return target
```

- [ ] **Step 2: Write the failing test**

`tests/resume_core/test_schema.py`:
```python
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
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run --with pytest pytest tests/resume_core/test_schema.py`
Expected: collection error, `ModuleNotFoundError: No module named 'rcore'`

- [ ] **Step 4: Write the implementation**

`skills/resume-core/scripts/rcore/__init__.py`:
```python
"""Shared library for resume-builder skills. Standard library only."""
```

`skills/resume-core/scripts/rcore/schema.py`:
```python
"""Minimal JSON Schema validator (standard library only).

Supports the subset used by resume-core schemas: type, const, enum, anyOf,
required, properties, additionalProperties, items, minItems, pattern,
minLength, minimum, maximum and local references ("#/$defs/<name>").
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


def load_schema(name: str) -> dict:
    """Load schemas/<name>.schema.json."""
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def _is_type(value, type_name: str) -> bool:
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _PY_TYPES[type_name])


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
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} is not one of {schema['enum']}")
    if "anyOf" in schema and all(validate(instance, s, root, path) for s in schema["anyOf"]):
        errors.append(f"{path}: does not match any allowed form")

    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            errors.append(f"{path}: shorter than {schema['minLength']} characters")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run --with pytest pytest tests/resume_core/test_schema.py`
Expected: `7 passed`

- [ ] **Step 6: Commit**

```bash
git add pytest.ini .gitignore tests/conftest.py tests/resume_core/test_schema.py skills/resume-core/scripts/rcore/
git commit -m "feat(resume-core): add stdlib JSON Schema validator and test harness"
```

---

### Task 2: File I/O helpers and stable IDs

**Files:**
- Create: `skills/resume-core/scripts/rcore/wsio.py`, `skills/resume-core/scripts/rcore/ids.py`
- Test: `tests/resume_core/test_wsio.py`, `tests/resume_core/test_ids.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `wsio.read_json(path) -> Any`, `wsio.write_json(path, data) -> None` (2-space indent, UTF-8, trailing newline, creates parent folders)
  - `wsio.read_jsonl(path) -> list[dict]` (skips blank lines; raises `ValueError("<path>:<line>: invalid JSON: ...")`), `wsio.write_jsonl(path, records) -> None` (sorted keys, one record per line)
  - `wsio.resolve_pointer(doc, pointer: str) -> Any` (RFC 6901; raises `KeyError` if unresolved)
  - `wsio.iter_strings(value, pointer="") -> Iterator[tuple[str, str]]` (pointer, string value; keys are not yielded)
  - `wsio.resume_highlights(resume: dict) -> Iterator[tuple[str, dict]]` (pointer, `x-highlights` item across `work` and `projects`)
  - `ids.SHORT_LENGTH = 8`, `ids.LONG_LENGTH = 12`
  - `ids.evidence_id(source: str, native_key: str, length: int = 8) -> str`
  - `ids.assign_evidence_ids(keys: Iterable[tuple[str, str]]) -> dict[tuple[str, str], str]`
  - `ids.project_id(evidence_ids: Iterable[str]) -> str` (`pj_` + 8 hex chars of the sorted, de-duplicated IDs joined by `\n`)
  - `ids.text_sha256(text: str) -> str` (64 hex chars, no prefix)

- [ ] **Step 1: Write the failing tests**

`tests/resume_core/test_wsio.py`:
```python
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
```

`tests/resume_core/test_ids.py`:
```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --with pytest pytest tests/resume_core/test_wsio.py tests/resume_core/test_ids.py`
Expected: collection errors, `ImportError: cannot import name 'wsio' from 'rcore'` and the same for `ids`

- [ ] **Step 3: Write the implementation**

`skills/resume-core/scripts/rcore/wsio.py`:
```python
"""Workspace file I/O, JSON Pointer resolution and string traversal."""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    """Read one JSON value per non-blank line. Raises ValueError naming the bad line."""
    records = []
    for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno}: invalid JSON: {exc.msg}") from exc
    return records


def write_jsonl(path: Path, records) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in records]
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def _unescape(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def resolve_pointer(doc, pointer: str):
    """Resolve an RFC 6901 JSON Pointer. Raises KeyError if it does not resolve."""
    if pointer == "":
        return doc
    if not pointer.startswith("/"):
        raise KeyError(pointer)
    node = doc
    for token in (_unescape(t) for t in pointer[1:].split("/")):
        if isinstance(node, dict) and token in node:
            node = node[token]
        elif isinstance(node, list) and token.isdigit() and int(token) < len(node):
            node = node[int(token)]
        else:
            raise KeyError(pointer)
    return node


def iter_strings(value, pointer: str = "") -> Iterator[tuple[str, str]]:
    """Yield (json_pointer, string) for every string value (not keys) in value."""
    if isinstance(value, str):
        yield pointer, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from iter_strings(child, f"{pointer}/{_escape(key)}")
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from iter_strings(child, f"{pointer}/{i}")


def resume_highlights(resume: dict) -> Iterator[tuple[str, dict]]:
    """Yield (json_pointer, x-highlight) for every sourced bullet in a tailored resume."""
    for section in ("work", "projects"):
        for i, entry in enumerate(resume.get(section, [])):
            for j, highlight in enumerate(entry.get("x-highlights", [])):
                yield f"/{section}/{i}/x-highlights/{j}", highlight
```

`skills/resume-core/scripts/rcore/ids.py`:
```python
"""Stable identifiers and text hashes."""
from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable

SHORT_LENGTH = 8
LONG_LENGTH = 12


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def evidence_id(source: str, native_key: str, length: int = SHORT_LENGTH) -> str:
    """ev_ + first `length` hex chars of sha256("<source>:<native_key>")."""
    return "ev_" + _digest(f"{source}:{native_key}")[:length]


def assign_evidence_ids(keys: Iterable[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """Map each (source, native_key) to its ID, using 12 hex chars where 8 collide."""
    unique = sorted(set(keys))
    short = {key: evidence_id(*key) for key in unique}
    counts = Counter(short.values())
    return {
        key: evidence_id(*key, length=LONG_LENGTH) if counts[short[key]] > 1 else short[key]
        for key in unique
    }


def project_id(evidence_ids: Iterable[str]) -> str:
    """Deterministic ID for a new project: pj_ + 8 hex chars of its sorted evidence IDs."""
    return "pj_" + _digest("\n".join(sorted(set(evidence_ids))))[:SHORT_LENGTH]


def text_sha256(text: str) -> str:
    """Hex sha256 of a bullet's text, used by attestations and flags."""
    return _digest(text)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --with pytest pytest tests/resume_core/test_wsio.py tests/resume_core/test_ids.py`
Expected: `11 passed`

- [ ] **Step 5: Commit**

```bash
git add skills/resume-core/scripts/rcore/wsio.py skills/resume-core/scripts/rcore/ids.py tests/resume_core/test_wsio.py tests/resume_core/test_ids.py
git commit -m "feat(resume-core): add workspace file helpers and stable IDs"
```

---

### Task 3: Config defaults and the metric prompt rule

**Files:**
- Create: `skills/resume-core/scripts/rcore/config.py`, `skills/resume-core/schemas/config.schema.json`
- Test: `tests/resume_core/test_config.py`

**Interfaces:**
- Consumes: `rcore.schema.load_schema`, `rcore.schema.validate` (Task 1).
- Produces:
  - `config.DEFAULT_METRIC_PROMPTS = {"percent": 0.30, "min": 3, "max": 8}`
  - `config.default_config(target_role: str = "") -> dict` (a fresh dict on every call)
  - `config.metric_prompt_count(project_count: int, percent: float = 0.30, minimum: int = 3, maximum: int = 8) -> int`
  - Schema `config` (file `config.json`).

- [ ] **Step 1: Write the failing test**

`tests/resume_core/test_config.py`:
```python
import pytest

from rcore import config
from rcore.schema import load_schema, validate


@pytest.mark.parametrize("count, expected", [
    (0, 0), (1, 1), (2, 2), (3, 3), (5, 3), (10, 3), (11, 4), (20, 6), (26, 8), (40, 8), (100, 8),
])
def test_metric_prompt_count_defaults(count, expected):
    assert config.metric_prompt_count(count) == expected


def test_metric_prompt_count_custom_settings():
    assert config.metric_prompt_count(10, percent=0.5, minimum=1, maximum=20) == 5
    assert config.metric_prompt_count(10, percent=0.0, minimum=0, maximum=8) == 0


def test_default_config_matches_schema():
    cfg = config.default_config("Staff Engineer")
    assert cfg["target_role"] == "Staff Engineer"
    assert cfg["metric_prompts"] == {"percent": 0.30, "min": 3, "max": 8}
    assert validate(cfg, load_schema("config")) == []


def test_default_config_returns_independent_copies():
    a = config.default_config()
    a["metric_prompts"]["max"] = 99
    assert config.default_config()["metric_prompts"]["max"] == 8
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest pytest tests/resume_core/test_config.py`
Expected: collection error, `ImportError: cannot import name 'config' from 'rcore'`

- [ ] **Step 3: Write the schema and implementation**

`skills/resume-core/schemas/config.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Workspace config (config.json)",
  "type": "object",
  "required": ["schema_version", "target_role", "time_range", "sources", "local_repos",
               "reviews_dir", "resume_path", "metric_prompts", "data_notice_acknowledged_at"],
  "additionalProperties": false,
  "properties": {
    "schema_version": {"const": 1},
    "target_role": {"type": "string"},
    "time_range": {
      "type": "object",
      "required": ["start", "end"],
      "additionalProperties": false,
      "properties": {
        "start": {"$ref": "#/$defs/dateOrNull"},
        "end": {"$ref": "#/$defs/dateOrNull"}
      }
    },
    "sources": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["type", "mode"],
        "additionalProperties": false,
        "properties": {
          "type": {"enum": ["github", "gitlab", "jira"]},
          "mode": {"enum": ["connector", "export", "skip"]},
          "username": {"type": ["string", "null"]},
          "export_path": {"type": ["string", "null"]}
        }
      }
    },
    "local_repos": {"type": "array", "items": {"type": "string", "minLength": 1}},
    "reviews_dir": {"type": ["string", "null"]},
    "resume_path": {"type": ["string", "null"]},
    "metric_prompts": {
      "type": "object",
      "required": ["percent", "min", "max"],
      "additionalProperties": false,
      "properties": {
        "percent": {"type": "number", "minimum": 0, "maximum": 1},
        "min": {"type": "integer", "minimum": 0},
        "max": {"type": "integer", "minimum": 0}
      }
    },
    "data_notice_acknowledged_at": {"type": ["string", "null"]}
  },
  "$defs": {
    "dateOrNull": {"type": ["string", "null"], "pattern": "^\\d{4}-\\d{2}-\\d{2}$"}
  }
}
```

`skills/resume-core/scripts/rcore/config.py`. The `round(..., 9)` guards against floating-point results like `3.0000000000000004` pushing `ceil` up by one:
```python
"""Workspace configuration defaults and the top-N metric prompt rule."""
from __future__ import annotations

import math

DEFAULT_METRIC_PROMPTS = {"percent": 0.30, "min": 3, "max": 8}


def default_config(target_role: str = "") -> dict:
    return {
        "schema_version": 1,
        "target_role": target_role,
        "time_range": {"start": None, "end": None},
        "sources": [],
        "local_repos": [],
        "reviews_dir": None,
        "resume_path": None,
        "metric_prompts": dict(DEFAULT_METRIC_PROMPTS),
        "data_notice_acknowledged_at": None,
    }


def metric_prompt_count(project_count: int, percent: float = 0.30,
                        minimum: int = 3, maximum: int = 8) -> int:
    """N = min(project_count, clamp(ceil(percent * project_count), minimum, maximum))."""
    if project_count <= 0:
        return 0
    n = math.ceil(round(percent * project_count, 9))
    return min(project_count, max(minimum, min(maximum, n)))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --with pytest pytest tests/resume_core/test_config.py`
Expected: `14 passed`

- [ ] **Step 5: Commit**

```bash
git add skills/resume-core/scripts/rcore/config.py skills/resume-core/schemas/config.schema.json tests/resume_core/test_config.py
git commit -m "feat(resume-core): add config defaults and metric prompt count rule"
```

---

### Task 4: Data contract schemas, fixture workspace and validation

**Files:**
- Create: `skills/resume-core/schemas/{stage,evidence,resume,projects,bullets,terms,term-candidates,project-decisions,metrics,attestations,flags}.schema.json`
- Create: the 16 files under `tests/fixtures/workspace/` listed in Step 2
- Create: `skills/resume-core/scripts/rcore/validation.py`
- Test: `tests/resume_core/test_schema_files.py`, `tests/resume_core/test_validation.py`

**Interfaces:**
- Consumes: `schema.load_schema`, `schema.validate` (Task 1); `wsio.read_json`, `wsio.read_jsonl` (Task 2).
- Produces:
  - `validation.FILE_SCHEMAS: list[tuple[str, str, str]]` (pattern, schema name, `"json"` or `"jsonl"`; `*` matches one path segment)
  - `validation.logical_path(rel: str) -> str` (`"06-bullets.tmp/x.json"` becomes `"06-bullets/x.json"`)
  - `validation.schema_for(rel: str) -> tuple[str, str] | None`
  - `validation.validate_file(path: Path, rel: str) -> list[str]` (errors prefixed with `rel`; JSONL errors name `record <n>`; flags duplicate `id`s in arrays)
  - `validation.validate_paths(workspace: Path, rels: list[str]) -> list[str]` (files or folders; missing gives `"<rel>: not found"`)
  - `validation.validate_workspace(workspace: Path) -> list[str]` (skips top-level `*.tmp` and `*.old`)
  - Fixture facts used by later tasks: evidence IDs `ev_191cc8ce`, `ev_56410ed1`, `ev_99a74656`, `ev_cbf558fa`; project `pj_da2a2b53`; metric `m_1`; bullets `b_1`, `b_2`, `b_3`; job slug `fintech-sre`; denied terms `Project Falcon`, `Contoso Bank`; allowed term `Go`.

Notes on the formats (they refine the spec's data contracts):
- Tailored resumes put sourcing in `x-highlights: [{bullet_id, text, sources}]` on each `work`/`projects` entry, because JSON Resume `highlights` are plain strings. `highlights` must hold the same texts in the same order; Task 6 checks this.
- `resume:` and `wizard:` sources are JSON Pointers into `03-profile/profile.json` and `decisions/profile.json`.
- `06-bullets/bullets.json` deliberately still contains the denied terms (it comes before the cleanup step). Task 7 relies on that.

- [ ] **Step 1: Write the schemas**

`skills/resume-core/schemas/stage.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Stage metadata (<stage>/_stage.json)",
  "type": "object",
  "required": ["stage", "schema_version", "created_at", "inputs"],
  "additionalProperties": false,
  "properties": {
    "stage": {"enum": ["01-raw", "02-evidence", "03-profile", "04-projects", "05-terms",
                       "06-bullets", "07-sanitized", "08-ats", "out"]},
    "schema_version": {"const": 1},
    "created_at": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$"},
    "inputs": {
      "type": "object",
      "additionalProperties": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
    },
    "extra": {"type": "object"}
  }
}
```

`skills/resume-core/schemas/evidence.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Evidence item (one line of 02-evidence/evidence.jsonl)",
  "type": "object",
  "required": ["id", "source", "kind", "native_key", "title", "engineer_role", "created_at"],
  "additionalProperties": false,
  "properties": {
    "id": {"$ref": "#/$defs/evidenceId"},
    "source": {"enum": ["github", "gitlab", "git", "jira", "review"]},
    "kind": {"enum": ["pr", "mr", "commit", "review", "issue", "ticket", "epic", "perf_review"]},
    "native_key": {"type": "string", "minLength": 1},
    "url": {"type": ["string", "null"]},
    "title": {"type": "string"},
    "excerpt": {"type": "string"},
    "engineer_role": {"enum": ["author", "reviewer", "assignee", "reporter", "subject"]},
    "created_at": {"type": "string", "minLength": 10},
    "closed_at": {"type": ["string", "null"]},
    "state": {"type": ["string", "null"]},
    "stats": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "additions": {"type": "integer", "minimum": 0},
        "deletions": {"type": "integer", "minimum": 0},
        "files": {"type": "integer", "minimum": 0}
      }
    },
    "labels": {"type": "array", "items": {"type": "string"}},
    "links": {"type": "array", "items": {"$ref": "#/$defs/evidenceId"}},
    "raw_ref": {"type": ["string", "null"]}
  },
  "$defs": {
    "evidenceId": {"type": "string", "pattern": "^ev_[0-9a-f]{8}([0-9a-f]{4})?$"}
  }
}
```

`skills/resume-core/schemas/resume.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "JSON Resume document with resume-builder extensions (x-sources, x-highlights)",
  "type": "object",
  "properties": {
    "basics": {"type": "object"},
    "work": {"type": "array", "items": {"$ref": "#/$defs/entry"}},
    "projects": {"type": "array", "items": {"$ref": "#/$defs/entry"}},
    "education": {"type": "array", "items": {"$ref": "#/$defs/dated"}},
    "certificates": {"type": "array", "items": {"type": "object"}},
    "skills": {"type": "array", "items": {"type": "object"}},
    "x-sources": {"$ref": "#/$defs/sources"}
  },
  "$defs": {
    "date": {"type": "string", "pattern": "^\\d{4}(-\\d{2}(-\\d{2})?)?$"},
    "sourceRef": {
      "type": "string",
      "pattern": "^(ev_[0-9a-f]{8}([0-9a-f]{4})?|metric:m_[A-Za-z0-9_-]+|resume:/.*|wizard:/.*)$"
    },
    "sources": {"type": "array", "items": {"$ref": "#/$defs/sourceRef"}},
    "dated": {
      "type": "object",
      "properties": {
        "startDate": {"$ref": "#/$defs/date"},
        "endDate": {"$ref": "#/$defs/date"},
        "x-sources": {"$ref": "#/$defs/sources"}
      }
    },
    "entry": {
      "type": "object",
      "properties": {
        "startDate": {"$ref": "#/$defs/date"},
        "endDate": {"$ref": "#/$defs/date"},
        "highlights": {"type": "array", "items": {"type": "string"}},
        "x-sources": {"$ref": "#/$defs/sources"},
        "x-highlights": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["bullet_id", "text", "sources"],
            "additionalProperties": false,
            "properties": {
              "bullet_id": {"type": "string", "pattern": "^b_[A-Za-z0-9_-]+$"},
              "text": {"type": "string", "minLength": 1},
              "sources": {"$ref": "#/$defs/sources"}
            }
          }
        }
      }
    }
  }
}
```

`skills/resume-core/schemas/projects.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Projects (04-projects/projects.json)",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["id", "internal_name", "summary", "evidence_ids", "role", "scope",
                 "start", "end", "rank", "rank_reasons", "metric_prompt"],
    "additionalProperties": false,
    "properties": {
      "id": {"type": "string", "pattern": "^pj_[0-9a-f]{8}$"},
      "internal_name": {"type": "string", "minLength": 1},
      "summary": {"type": "string"},
      "evidence_ids": {
        "type": "array", "minItems": 1,
        "items": {"type": "string", "pattern": "^ev_[0-9a-f]{8}([0-9a-f]{4})?$"}
      },
      "role": {"enum": ["lead", "core", "supporting"]},
      "scope": {"enum": ["team", "cross-team", "org", "company"]},
      "start": {"type": "string", "pattern": "^\\d{4}-\\d{2}$"},
      "end": {"type": ["string", "null"], "pattern": "^\\d{4}-\\d{2}$"},
      "rank": {"type": "integer", "minimum": 1},
      "rank_reasons": {"type": "array", "items": {"type": "string"}},
      "metric_prompt": {"type": "boolean"}
    }
  }
}
```

`skills/resume-core/schemas/bullets.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Bullets (06-bullets/bullets.json, 07-sanitized/bullets.json)",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["id", "project_id", "work_ref", "text", "form", "sources"],
    "additionalProperties": false,
    "properties": {
      "id": {"type": "string", "pattern": "^b_[A-Za-z0-9_-]+$"},
      "project_id": {"type": ["string", "null"], "pattern": "^pj_[0-9a-f]{8}$"},
      "work_ref": {"type": ["integer", "null"], "minimum": 0},
      "text": {"type": "string", "minLength": 1},
      "form": {"enum": ["xyz_quantified", "xyz"]},
      "sources": {
        "type": "array",
        "items": {
          "type": "string",
          "pattern": "^(ev_[0-9a-f]{8}([0-9a-f]{4})?|metric:m_[A-Za-z0-9_-]+|resume:/.*|wizard:/.*)$"
        }
      }
    }
  }
}
```

`skills/resume-core/schemas/terms.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Confidentiality decisions (decisions/terms.json)",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["term", "replacement", "kind"],
    "additionalProperties": false,
    "properties": {
      "term": {"type": "string", "minLength": 2},
      "replacement": {"type": ["string", "null"]},
      "kind": {"enum": ["codename", "customer", "product", "url", "financial", "other"]}
    }
  }
}
```

`skills/resume-core/schemas/term-candidates.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Proposed sensitive terms (05-terms/candidates.json, 07-sanitized/new-terms.json)",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["term", "kind", "proposed_replacement", "found_in"],
    "additionalProperties": false,
    "properties": {
      "term": {"type": "string", "minLength": 2},
      "kind": {"enum": ["codename", "customer", "product", "url", "financial", "other"]},
      "proposed_replacement": {"type": "string"},
      "found_in": {"type": "array", "items": {"type": "string"}}
    }
  }
}
```

`skills/resume-core/schemas/project-decisions.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Project decisions (decisions/projects.json)",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["project_id", "action"],
    "additionalProperties": false,
    "properties": {
      "project_id": {"type": "string", "pattern": "^pj_[0-9a-f]{8}$"},
      "action": {"enum": ["exclude", "merge", "split", "rename", "set_role", "set_scope"]},
      "merge_with": {"type": "array", "items": {"type": "string", "pattern": "^pj_[0-9a-f]{8}$"}},
      "split_groups": {
        "type": "array",
        "items": {"type": "array", "items": {"type": "string", "pattern": "^ev_[0-9a-f]{8}([0-9a-f]{4})?$"}}
      },
      "name": {"type": "string"},
      "role": {"enum": ["lead", "core", "supporting"]},
      "scope": {"enum": ["team", "cross-team", "org", "company"]},
      "evidence_ids": {
        "type": "array",
        "items": {"type": "string", "pattern": "^ev_[0-9a-f]{8}([0-9a-f]{4})?$"}
      }
    }
  }
}
```

`skills/resume-core/schemas/metrics.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Confirmed metrics (decisions/metrics.json)",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["id", "project_id", "value", "unit", "statement"],
    "additionalProperties": false,
    "properties": {
      "id": {"type": "string", "pattern": "^m_[A-Za-z0-9_-]+$"},
      "project_id": {"type": "string", "pattern": "^pj_[0-9a-f]{8}$"},
      "value": {"type": "number"},
      "unit": {"type": "string"},
      "statement": {"type": "string", "minLength": 1}
    }
  }
}
```

`skills/resume-core/schemas/attestations.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Accepted job-specific rewrites (decisions/attestations.json)",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["job_slug", "bullet_id", "text_sha256", "action"],
    "additionalProperties": false,
    "properties": {
      "job_slug": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
      "bullet_id": {"type": "string", "pattern": "^b_[A-Za-z0-9_-]+$"},
      "text_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
      "action": {"enum": ["accept", "edit"]}
    }
  }
}
```

`skills/resume-core/schemas/flags.schema.json`:
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Unsupported claims in a job-specific resume (08-ats/jobs/<slug>/flags.json)",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["bullet_id", "text", "text_sha256", "reasons"],
    "additionalProperties": false,
    "properties": {
      "bullet_id": {"type": "string", "pattern": "^b_[A-Za-z0-9_-]+$"},
      "text": {"type": "string", "minLength": 1},
      "text_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
      "reasons": {"type": "array", "minItems": 1, "items": {"type": "string"}}
    }
  }
}
```

- [ ] **Step 2: Write the fixture workspace**

Every ID and hash below was computed with `rcore.ids`. Copy them exactly; tests assert on them.

`tests/fixtures/workspace/config.json`:
```json
{
  "schema_version": 1,
  "target_role": "Senior Backend Engineer",
  "time_range": {
    "start": "2023-01-01",
    "end": null
  },
  "sources": [
    {
      "type": "github",
      "mode": "connector",
      "username": "jrivera",
      "export_path": null
    },
    {
      "type": "jira",
      "mode": "export",
      "username": "jordan.rivera",
      "export_path": "exports/jira.csv"
    }
  ],
  "local_repos": [],
  "reviews_dir": "reviews",
  "resume_path": "old-resume.pdf",
  "metric_prompts": {
    "percent": 0.3,
    "min": 3,
    "max": 8
  },
  "data_notice_acknowledged_at": "2026-09-24T15:00:00Z"
}
```

`tests/fixtures/workspace/decisions/terms.json`:
```json
[
  {
    "term": "Project Falcon",
    "replacement": "real-time fraud-detection platform",
    "kind": "codename"
  },
  {
    "term": "Contoso Bank",
    "replacement": "a top-10 US bank",
    "kind": "customer"
  },
  {
    "term": "Go",
    "replacement": null,
    "kind": "other"
  }
]
```

`tests/fixtures/workspace/decisions/projects.json`:
```json
[
  {
    "project_id": "pj_da2a2b53",
    "action": "set_role",
    "role": "lead"
  }
]
```

`tests/fixtures/workspace/decisions/metrics.json`:
```json
[
  {
    "id": "m_1",
    "project_id": "pj_da2a2b53",
    "value": 40,
    "unit": "%",
    "statement": "p99 checkout latency reduced 40%"
  }
]
```

`tests/fixtures/workspace/decisions/profile.json`:
```json
{
  "basics": {
    "email": "jordan.rivera@example.com",
    "location": {
      "city": "Denver",
      "region": "CO"
    }
  }
}
```

`tests/fixtures/workspace/decisions/attestations.json`:
```json
[
  {
    "job_slug": "fintech-sre",
    "bullet_id": "b_1",
    "text_sha256": "f6c1490f4c91b1883112ce62228851f0eaefcc79db157cb042f2a3adbf50735f",
    "action": "accept"
  }
]
```

`tests/fixtures/workspace/02-evidence/evidence.jsonl` (four lines, one JSON object each):
```json
{"closed_at": "2025-03-11T09:30:00Z", "created_at": "2025-03-04T17:12:00Z", "engineer_role": "author", "excerpt": "Adds a Redis-backed idempotency cache in front of the Contoso Bank checkout path.", "id": "ev_191cc8ce", "kind": "pr", "labels": ["performance"], "links": ["ev_99a74656"], "native_key": "northwind/ledger#101", "raw_ref": "01-raw/github.jsonl:1", "source": "github", "state": "merged", "stats": {"additions": 812, "deletions": 140, "files": 23}, "title": "PAY-42: Add Redis idempotency cache for Project Falcon checkout", "url": "https://github.com/northwind/ledger/pull/101"}
{"closed_at": "2025-04-03T12:00:00Z", "created_at": "2025-04-02T10:00:00Z", "engineer_role": "reviewer", "excerpt": "Reviewed eviction metrics dashboard.", "id": "ev_56410ed1", "kind": "review", "labels": [], "links": ["ev_99a74656"], "native_key": "northwind/ledger#118", "raw_ref": "01-raw/github.jsonl:2", "source": "github", "state": "merged", "title": "PAY-57: Cache eviction metrics", "url": "https://github.com/northwind/ledger/pull/118"}
{"closed_at": "2025-05-30T00:00:00Z", "created_at": "2025-02-10T00:00:00Z", "engineer_role": "assignee", "excerpt": "Reduce p99 checkout latency for Contoso Bank.", "id": "ev_99a74656", "kind": "epic", "labels": [], "links": [], "native_key": "PAY-42", "raw_ref": "01-raw/jira.jsonl:1", "source": "jira", "state": "Done", "title": "Project Falcon: checkout latency", "url": null}
{"closed_at": null, "created_at": "2025-07-15T00:00:00Z", "engineer_role": "subject", "excerpt": "Jordan mentored two new engineers through on-call onboarding.", "id": "ev_cbf558fa", "kind": "perf_review", "labels": [], "links": [], "native_key": "2025-H1", "raw_ref": "01-raw/reviews.jsonl:1", "source": "review", "state": null, "title": "2025 H1 performance review", "url": null}
```

`tests/fixtures/workspace/03-profile/profile.json`:
```json
{
  "basics": {
    "name": "Jordan Rivera",
    "label": "Backend Engineer"
  },
  "work": [
    {
      "name": "Northwind Payments",
      "position": "Senior Software Engineer",
      "startDate": "2023-01",
      "highlights": [],
      "x-sources": [
        "resume:/work/0"
      ]
    },
    {
      "name": "Tailspin Toys",
      "position": "Software Engineer",
      "startDate": "2019-06",
      "endDate": "2022-12",
      "highlights": [
        "Migrated the order service from PHP to Go, serving 2M requests per day"
      ],
      "x-sources": [
        "resume:/work/1"
      ]
    }
  ],
  "education": [
    {
      "institution": "State University",
      "studyType": "BS",
      "area": "Computer Science",
      "endDate": "2019",
      "x-sources": [
        "resume:/education/0"
      ]
    }
  ],
  "skills": [
    {
      "name": "Backend",
      "keywords": [
        "Go",
        "Python",
        "Redis",
        "PostgreSQL"
      ]
    }
  ]
}
```

`tests/fixtures/workspace/04-projects/projects.json`:
```json
[
  {
    "id": "pj_da2a2b53",
    "internal_name": "Project Falcon checkout latency",
    "summary": "Idempotency cache that cut checkout latency for Contoso Bank.",
    "evidence_ids": [
      "ev_191cc8ce",
      "ev_56410ed1",
      "ev_99a74656"
    ],
    "role": "lead",
    "scope": "cross-team",
    "start": "2025-02",
    "end": "2025-05",
    "rank": 1,
    "rank_reasons": [
      "authored the core PR and owned the epic",
      "customer-facing latency impact"
    ],
    "metric_prompt": true
  }
]
```

`tests/fixtures/workspace/05-terms/candidates.json`:
```json
[
  {
    "term": "Project Falcon",
    "kind": "codename",
    "proposed_replacement": "real-time fraud-detection platform",
    "found_in": [
      "04-projects/projects.json"
    ]
  },
  {
    "term": "Contoso Bank",
    "kind": "customer",
    "proposed_replacement": "a top-10 US bank",
    "found_in": [
      "04-projects/projects.json"
    ]
  }
]
```

`tests/fixtures/workspace/06-bullets/bullets.json`:
```json
[
  {
    "id": "b_1",
    "project_id": "pj_da2a2b53",
    "work_ref": null,
    "text": "Cut p99 checkout latency 40% for Contoso Bank by building a Redis-backed idempotency cache for Project Falcon in Go",
    "form": "xyz_quantified",
    "sources": [
      "ev_191cc8ce",
      "ev_99a74656",
      "metric:m_1"
    ]
  },
  {
    "id": "b_2",
    "project_id": null,
    "work_ref": 0,
    "text": "Mentored two new engineers through on-call onboarding",
    "form": "xyz",
    "sources": [
      "ev_cbf558fa"
    ]
  },
  {
    "id": "b_3",
    "project_id": null,
    "work_ref": 1,
    "text": "Migrated the order service from PHP to Go, serving 2M requests per day",
    "form": "xyz",
    "sources": [
      "resume:/work/1/highlights/0"
    ]
  }
]
```

`tests/fixtures/workspace/07-sanitized/bullets.json`:
```json
[
  {
    "id": "b_1",
    "project_id": "pj_da2a2b53",
    "work_ref": null,
    "text": "Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency cache for a real-time fraud-detection platform in Go",
    "form": "xyz_quantified",
    "sources": [
      "ev_191cc8ce",
      "ev_99a74656",
      "metric:m_1"
    ]
  },
  {
    "id": "b_2",
    "project_id": null,
    "work_ref": 0,
    "text": "Mentored two new engineers through on-call onboarding",
    "form": "xyz",
    "sources": [
      "ev_cbf558fa"
    ]
  },
  {
    "id": "b_3",
    "project_id": null,
    "work_ref": 1,
    "text": "Migrated the order service from PHP to Go, serving 2M requests per day",
    "form": "xyz",
    "sources": [
      "resume:/work/1/highlights/0"
    ]
  }
]
```

`tests/fixtures/workspace/07-sanitized/profile.json` (identical to `03-profile/profile.json`):
```json
{
  "basics": {
    "name": "Jordan Rivera",
    "label": "Backend Engineer"
  },
  "work": [
    {
      "name": "Northwind Payments",
      "position": "Senior Software Engineer",
      "startDate": "2023-01",
      "highlights": [],
      "x-sources": [
        "resume:/work/0"
      ]
    },
    {
      "name": "Tailspin Toys",
      "position": "Software Engineer",
      "startDate": "2019-06",
      "endDate": "2022-12",
      "highlights": [
        "Migrated the order service from PHP to Go, serving 2M requests per day"
      ],
      "x-sources": [
        "resume:/work/1"
      ]
    }
  ],
  "education": [
    {
      "institution": "State University",
      "studyType": "BS",
      "area": "Computer Science",
      "endDate": "2019",
      "x-sources": [
        "resume:/education/0"
      ]
    }
  ],
  "skills": [
    {
      "name": "Backend",
      "keywords": [
        "Go",
        "Python",
        "Redis",
        "PostgreSQL"
      ]
    }
  ]
}
```

`tests/fixtures/workspace/08-ats/general/resume.json`:
```json
{
  "basics": {
    "name": "Jordan Rivera",
    "label": "Senior Backend Engineer",
    "email": "jordan.rivera@example.com",
    "location": {
      "city": "Denver",
      "region": "CO"
    },
    "x-sources": [
      "resume:/basics",
      "wizard:/basics/email"
    ]
  },
  "work": [
    {
      "name": "Northwind Payments",
      "position": "Senior Software Engineer",
      "startDate": "2023-01",
      "highlights": [
        "Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency cache in Go",
        "Mentored two new engineers through on-call onboarding"
      ],
      "x-highlights": [
        {
          "bullet_id": "b_1",
          "text": "Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency cache in Go",
          "sources": [
            "ev_191cc8ce",
            "ev_99a74656",
            "metric:m_1"
          ]
        },
        {
          "bullet_id": "b_2",
          "text": "Mentored two new engineers through on-call onboarding",
          "sources": [
            "ev_cbf558fa"
          ]
        }
      ]
    },
    {
      "name": "Tailspin Toys",
      "position": "Software Engineer",
      "startDate": "2019-06",
      "endDate": "2022-12",
      "highlights": [
        "Migrated the order service from PHP to Go, serving 2M requests per day"
      ],
      "x-highlights": [
        {
          "bullet_id": "b_3",
          "text": "Migrated the order service from PHP to Go, serving 2M requests per day",
          "sources": [
            "resume:/work/1/highlights/0"
          ]
        }
      ]
    }
  ],
  "education": [
    {
      "institution": "State University",
      "studyType": "BS",
      "area": "Computer Science",
      "endDate": "2019",
      "x-sources": [
        "resume:/education/0"
      ]
    }
  ],
  "skills": [
    {
      "name": "Backend",
      "keywords": [
        "Go",
        "Python",
        "Redis",
        "PostgreSQL"
      ]
    }
  ]
}
```

`tests/fixtures/workspace/08-ats/jobs/fintech-sre/resume.json`:
```json
{
  "basics": {
    "name": "Jordan Rivera",
    "label": "Senior Backend Engineer",
    "email": "jordan.rivera@example.com",
    "location": {
      "city": "Denver",
      "region": "CO"
    },
    "x-sources": [
      "resume:/basics",
      "wizard:/basics/email"
    ]
  },
  "work": [
    {
      "name": "Northwind Payments",
      "position": "Senior Software Engineer",
      "startDate": "2023-01",
      "highlights": [
        "Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency cache in Go, raising checkout SLO compliance",
        "Mentored two new engineers through on-call onboarding"
      ],
      "x-highlights": [
        {
          "bullet_id": "b_1",
          "text": "Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency cache in Go, raising checkout SLO compliance",
          "sources": [
            "ev_191cc8ce",
            "ev_99a74656",
            "metric:m_1"
          ]
        },
        {
          "bullet_id": "b_2",
          "text": "Mentored two new engineers through on-call onboarding",
          "sources": [
            "ev_cbf558fa"
          ]
        }
      ]
    },
    {
      "name": "Tailspin Toys",
      "position": "Software Engineer",
      "startDate": "2019-06",
      "endDate": "2022-12",
      "highlights": [
        "Migrated the order service from PHP to Go, serving 2M requests per day"
      ],
      "x-highlights": [
        {
          "bullet_id": "b_3",
          "text": "Migrated the order service from PHP to Go, serving 2M requests per day",
          "sources": [
            "resume:/work/1/highlights/0"
          ]
        }
      ]
    }
  ],
  "education": [
    {
      "institution": "State University",
      "studyType": "BS",
      "area": "Computer Science",
      "endDate": "2019",
      "x-sources": [
        "resume:/education/0"
      ]
    }
  ],
  "skills": [
    {
      "name": "Backend",
      "keywords": [
        "Go",
        "Python",
        "Redis",
        "PostgreSQL"
      ]
    }
  ]
}
```

`tests/fixtures/workspace/08-ats/jobs/fintech-sre/flags.json`:
```json
[
  {
    "bullet_id": "b_1",
    "text": "Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency cache in Go, raising checkout SLO compliance",
    "text_sha256": "f6c1490f4c91b1883112ce62228851f0eaefcc79db157cb042f2a3adbf50735f",
    "reasons": [
      "introduces 'SLO compliance', which no cited source mentions"
    ]
  }
]
```

- [ ] **Step 3: Write the failing tests**

`tests/resume_core/test_schema_files.py`:
```python
from rcore.schema import load_schema


def test_every_schema_file_loads():
    for name in ["config", "stage", "evidence", "resume", "projects", "bullets", "terms",
                 "term-candidates", "project-decisions", "metrics", "attestations", "flags"]:
        assert load_schema(name)["$schema"].startswith("https://json-schema.org/")
```

`tests/resume_core/test_validation.py`:
```python
import json

from rcore import validation, wsio


def test_fixture_workspace_is_valid(workspace):
    assert validation.validate_workspace(workspace) == []


def test_schema_for_maps_paths():
    assert validation.schema_for("02-evidence/evidence.jsonl") == ("evidence", "jsonl")
    assert validation.schema_for("08-ats/jobs/acme/flags.json") == ("flags", "json")
    assert validation.schema_for("06-bullets.tmp/bullets.json") == ("bullets", "json")
    assert validation.schema_for("04-projects/_stage.json") == ("stage", "json")
    assert validation.schema_for("08-ats/jobs/a/b/flags.json") is None
    assert validation.schema_for("01-raw/github.jsonl") is None


def test_logical_path():
    assert validation.logical_path("06-bullets.tmp/bullets.json") == "06-bullets/bullets.json"
    assert validation.logical_path("06-bullets.tmp") == "06-bullets"
    assert validation.logical_path("config.json") == "config.json"


def test_bad_evidence_record_is_reported_with_record_number(workspace):
    path = workspace / "02-evidence" / "evidence.jsonl"
    records = wsio.read_jsonl(path)
    records[1]["id"] = "ev_BAD"
    wsio.write_jsonl(path, records)
    errors = validation.validate_paths(workspace, ["02-evidence"])
    assert len(errors) == 1
    assert errors[0].startswith("02-evidence/evidence.jsonl: record 2: $.id:")


def test_invalid_json_is_reported(workspace):
    (workspace / "04-projects" / "projects.json").write_text("[{", encoding="utf-8")
    errors = validation.validate_paths(workspace, ["04-projects/projects.json"])
    assert len(errors) == 1 and errors[0].startswith("04-projects/projects.json: ")


def test_duplicate_ids_are_reported(workspace):
    path = workspace / "06-bullets" / "bullets.json"
    bullets = wsio.read_json(path)
    bullets.append(dict(bullets[0]))
    wsio.write_json(path, bullets)
    assert validation.validate_paths(workspace, ["06-bullets"]) == [
        "06-bullets/bullets.json: duplicate id 'b_1'"
    ]


def test_tmp_folder_is_validated_with_committed_schema(workspace):
    tmp = workspace / "06-bullets.tmp"
    tmp.mkdir()
    (tmp / "bullets.json").write_text(json.dumps([{"id": "b_1"}]), encoding="utf-8")
    errors = validation.validate_paths(workspace, ["06-bullets.tmp"])
    assert errors and all(e.startswith("06-bullets.tmp/bullets.json: $[0]: missing") for e in errors)


def test_workspace_validation_skips_tmp_and_old(workspace):
    for name in ("06-bullets.tmp", "06-bullets.old"):
        (workspace / name).mkdir()
        (workspace / name / "bullets.json").write_text("not json", encoding="utf-8")
    assert validation.validate_workspace(workspace) == []


def test_missing_path_is_an_error(workspace):
    assert validation.validate_paths(workspace, ["nope.json"]) == ["nope.json: not found"]
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv run --with pytest pytest tests/resume_core/test_schema_files.py tests/resume_core/test_validation.py`
Expected: `test_schema_files.py` passes (1 passed); `test_validation.py` fails to collect with `ImportError: cannot import name 'validation' from 'rcore'`

- [ ] **Step 5: Write the implementation**

`skills/resume-core/scripts/rcore/validation.py`:
```python
"""Schema validation for workspace files, mapped by path."""
from __future__ import annotations

import fnmatch
import json
from collections import Counter
from pathlib import Path

from . import schema, wsio

# (path pattern relative to the workspace, schema name, file format).
# "*" matches exactly one path segment.
FILE_SCHEMAS: list[tuple[str, str, str]] = [
    ("config.json", "config", "json"),
    ("decisions/terms.json", "terms", "json"),
    ("decisions/projects.json", "project-decisions", "json"),
    ("decisions/metrics.json", "metrics", "json"),
    ("decisions/profile.json", "resume", "json"),
    ("decisions/attestations.json", "attestations", "json"),
    ("*/_stage.json", "stage", "json"),
    ("02-evidence/evidence.jsonl", "evidence", "jsonl"),
    ("03-profile/profile.json", "resume", "json"),
    ("04-projects/projects.json", "projects", "json"),
    ("05-terms/candidates.json", "term-candidates", "json"),
    ("06-bullets/bullets.json", "bullets", "json"),
    ("07-sanitized/bullets.json", "bullets", "json"),
    ("07-sanitized/profile.json", "resume", "json"),
    ("07-sanitized/new-terms.json", "term-candidates", "json"),
    ("08-ats/general/resume.json", "resume", "json"),
    ("08-ats/jobs/*/resume.json", "resume", "json"),
    ("08-ats/jobs/*/flags.json", "flags", "json"),
]


def _matches(rel: str, pattern: str) -> bool:
    parts, pattern_parts = rel.split("/"), pattern.split("/")
    return len(parts) == len(pattern_parts) and all(
        fnmatch.fnmatchcase(p, q) for p, q in zip(parts, pattern_parts)
    )


def logical_path(rel: str) -> str:
    """Map a path inside '<stage>.tmp/' to the path it will have once committed."""
    first, sep, rest = rel.partition("/")
    if first.endswith(".tmp"):
        first = first[: -len(".tmp")]
    return first + sep + rest


def schema_for(rel: str) -> tuple[str, str] | None:
    """Return (schema name, format) for a workspace-relative path, or None."""
    logical = logical_path(rel)
    for pattern, name, fmt in FILE_SCHEMAS:
        if _matches(logical, pattern):
            return name, fmt
    return None


def _duplicate_ids(records: list) -> list[str]:
    ids = [r["id"] for r in records if isinstance(r, dict) and isinstance(r.get("id"), str)]
    return sorted(i for i, n in Counter(ids).items() if n > 1)


def validate_file(path: Path, rel: str) -> list[str]:
    """Validate one file against the schema its path maps to. Unmapped files pass."""
    mapping = schema_for(rel)
    if mapping is None:
        return []
    name, fmt = mapping
    spec = schema.load_schema(name)
    try:
        if fmt == "jsonl":
            records = wsio.read_jsonl(path)
            errors = []
            for lineno, record in enumerate(records, start=1):
                errors += [f"{rel}: record {lineno}: {e}" for e in schema.validate(record, spec)]
            data = records
        else:
            data = wsio.read_json(path)
            errors = [f"{rel}: {e}" for e in schema.validate(data, spec)]
    except (ValueError, json.JSONDecodeError) as exc:
        return [f"{rel}: {exc}"]
    if isinstance(data, list):
        errors += [f"{rel}: duplicate id {i!r}" for i in _duplicate_ids(data)]
    return errors


def validate_paths(workspace: Path, rels: list[str]) -> list[str]:
    """Validate files and directories given relative to the workspace."""
    workspace = Path(workspace)
    errors: list[str] = []
    for rel in rels:
        target = workspace / rel
        if target.is_dir():
            for path in sorted(p for p in target.rglob("*") if p.is_file()):
                errors += validate_file(path, path.relative_to(workspace).as_posix())
        elif target.is_file():
            errors += validate_file(target, rel)
        else:
            errors.append(f"{rel}: not found")
    return errors


def validate_workspace(workspace: Path) -> list[str]:
    """Validate every committed file in the workspace (skips *.tmp and *.old folders)."""
    workspace = Path(workspace)
    rels = sorted(
        p.name for p in workspace.iterdir()
        if not p.name.endswith((".tmp", ".old"))
    )
    return validate_paths(workspace, rels)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run --with pytest pytest tests/resume_core/test_schema_files.py tests/resume_core/test_validation.py`
Expected: `10 passed`

If `test_fixture_workspace_is_valid` fails, the error names the fixture file and field. Fix the fixture to match Step 2 exactly; do not loosen a schema.

- [ ] **Step 7: Commit**

```bash
git add skills/resume-core/schemas/ skills/resume-core/scripts/rcore/validation.py tests/fixtures/workspace/ tests/resume_core/test_schema_files.py tests/resume_core/test_validation.py
git commit -m "feat(resume-core): add data contract schemas, fixture workspace and validation"
```

---

### Task 5: Stage lifecycle

**Files:**
- Create: `skills/resume-core/scripts/rcore/stages.py`
- Test: `tests/resume_core/test_stages.py`

**Interfaces:**
- Consumes: `validation.validate_paths` (Task 4); `wsio.read_json`, `wsio.write_json` (Task 2).
- Produces:
  - `stages.STAGES: tuple[str, ...]`, `stages.META = "_stage.json"`, `stages.SCHEMA_VERSION = 1`
  - `stages.tmp_dir(workspace, stage) -> Path`
  - `stages.begin(workspace, stage) -> Path` (empty `<stage>.tmp/`; `ValueError` for unknown stage)
  - `stages.hash_path(path) -> str` (`"sha256:<hex>"`; folders hash relative paths plus file bytes, ignoring `_stage.json`)
  - `stages.commit(workspace, stage, inputs: list[str], extra: dict | None = None) -> list[str]` (empty list on success; on error the previous `<stage>/` is untouched and `<stage>.tmp/` is kept for fixing)
  - `stages.status(workspace) -> dict[str, str]` (each stage `"missing"`, `"fresh"` or `"stale"`; stale spreads to stages whose inputs live in a stale stage)

- [ ] **Step 1: Write the failing test**

`tests/resume_core/test_stages.py`:
```python
import pytest

from rcore import stages, wsio

BULLET = {"id": "b_9", "project_id": None, "work_ref": 0, "text": "Did X",
          "form": "xyz", "sources": ["ev_cbf558fa"]}


def _write_bullets(workspace, bullets):
    tmp = stages.begin(workspace, "06-bullets")
    wsio.write_json(tmp / "bullets.json", bullets)
    return tmp


def test_begin_rejects_unknown_stage(workspace):
    with pytest.raises(ValueError, match="unknown stage"):
        stages.begin(workspace, "09-nope")


def test_begin_discards_leftover_tmp(workspace):
    tmp = stages.begin(workspace, "06-bullets")
    (tmp / "junk.txt").write_text("x")
    assert list(stages.begin(workspace, "06-bullets").iterdir()) == []


def test_commit_swaps_in_new_output_and_records_inputs(workspace):
    _write_bullets(workspace, [BULLET])
    errors = stages.commit(workspace, "06-bullets", ["04-projects", "decisions/metrics.json"])
    assert errors == []
    assert not (workspace / "06-bullets.tmp").exists()
    assert not (workspace / "06-bullets.old").exists()
    assert wsio.read_json(workspace / "06-bullets" / "bullets.json") == [BULLET]
    meta = wsio.read_json(workspace / "06-bullets" / "_stage.json")
    assert meta["stage"] == "06-bullets"
    assert set(meta["inputs"]) == {"04-projects", "decisions/metrics.json"}
    assert all(v.startswith("sha256:") for v in meta["inputs"].values())


def test_commit_with_invalid_output_keeps_previous_stage(workspace):
    before = wsio.read_json(workspace / "06-bullets" / "bullets.json")
    _write_bullets(workspace, [{"id": "b_1", "text": ""}])
    errors = stages.commit(workspace, "06-bullets", ["04-projects"])
    assert errors and errors[0].startswith("06-bullets.tmp/bullets.json:")
    assert wsio.read_json(workspace / "06-bullets" / "bullets.json") == before
    assert (workspace / "06-bullets.tmp").is_dir()


def test_commit_requires_begin_and_existing_inputs(workspace):
    assert stages.commit(workspace, "06-bullets", []) == ["06-bullets.tmp: not found; run begin first"]
    _write_bullets(workspace, [BULLET])
    assert stages.commit(workspace, "06-bullets", ["04-projects/nope.json"]) == [
        "input not found: 04-projects/nope.json"
    ]


def test_hash_path_directory_ignores_stage_meta(workspace):
    before = stages.hash_path(workspace / "04-projects")
    wsio.write_json(workspace / "04-projects" / "_stage.json", {"anything": 1})
    assert stages.hash_path(workspace / "04-projects") == before
    (workspace / "04-projects" / "extra.json").write_text("{}")
    assert stages.hash_path(workspace / "04-projects") != before


def _commit_chain(workspace):
    for stage, inputs in [("04-projects", ["02-evidence"]), ("06-bullets", ["04-projects"])]:
        tmp = stages.begin(workspace, stage)
        for f in (workspace / stage).iterdir():
            if f.name != "_stage.json":
                (tmp / f.name).write_bytes(f.read_bytes())
        assert stages.commit(workspace, stage, inputs) == []


def test_status_fresh_missing_and_stale(workspace):
    _commit_chain(workspace)
    status = stages.status(workspace)
    assert status["04-projects"] == "fresh"
    assert status["06-bullets"] == "fresh"
    assert status["02-evidence"] == "missing"  # fixture has no _stage.json there

    wsio.write_json(workspace / "04-projects" / "projects.json", [])
    status = stages.status(workspace)
    assert status["04-projects"] == "fresh"
    assert status["06-bullets"] == "stale"


def test_status_propagates_staleness_downstream(workspace):
    _commit_chain(workspace)
    evidence = workspace / "02-evidence" / "evidence.jsonl"
    evidence.write_text(evidence.read_text() + "\n")
    status = stages.status(workspace)
    assert status["04-projects"] == "stale"
    assert status["06-bullets"] == "stale"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest pytest tests/resume_core/test_stages.py`
Expected: collection error, `ImportError: cannot import name 'stages' from 'rcore'`

- [ ] **Step 3: Write the implementation**

`skills/resume-core/scripts/rcore/stages.py`. Note that `status` only spreads staleness from a *stale* upstream stage. An upstream stage with no `_stage.json` (for example, a hand-supplied evidence file) is judged by its input hashes alone:
```python
"""Stage lifecycle: begin into <stage>.tmp/, commit atomically, report freshness."""
from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import validation, wsio

STAGES = ("01-raw", "02-evidence", "03-profile", "04-projects", "05-terms",
          "06-bullets", "07-sanitized", "08-ats", "out")
META = "_stage.json"
SCHEMA_VERSION = 1


def _check(stage: str) -> None:
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}; expected one of {', '.join(STAGES)}")


def tmp_dir(workspace: Path, stage: str) -> Path:
    return Path(workspace) / f"{stage}.tmp"


def begin(workspace: Path, stage: str) -> Path:
    """Create an empty <stage>.tmp/ (discarding any leftover) and return its path."""
    _check(stage)
    tmp = tmp_dir(workspace, stage)
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    return tmp


def hash_path(path: Path) -> str:
    """sha256 of a file's bytes, or of a directory's relative paths and file bytes.

    Directory hashes ignore _stage.json so re-committing identical content
    does not mark downstream stages stale.
    """
    path = Path(path)
    if path.is_file():
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    digest = hashlib.sha256()
    for file in sorted(p for p in path.rglob("*") if p.is_file() and p.name != META):
        digest.update(file.relative_to(path).as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(file.read_bytes()).digest())
    return "sha256:" + digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def commit(workspace: Path, stage: str, inputs: list[str], extra: dict | None = None) -> list[str]:
    """Record input hashes, validate <stage>.tmp/, and swap it into place.

    Returns a list of errors. On any error the previous <stage>/ is untouched.
    """
    _check(stage)
    workspace = Path(workspace)
    tmp = tmp_dir(workspace, stage)
    if not tmp.is_dir():
        return [f"{tmp.name}: not found; run begin first"]
    missing = [rel for rel in inputs if not (workspace / rel).exists()]
    if missing:
        return [f"input not found: {rel}" for rel in missing]

    meta = {
        "stage": stage,
        "schema_version": SCHEMA_VERSION,
        "created_at": _now(),
        "inputs": {rel: hash_path(workspace / rel) for rel in sorted(inputs)},
    }
    if extra:
        meta["extra"] = extra
    wsio.write_json(tmp / META, meta)

    errors = validation.validate_paths(workspace, [tmp.name])
    if errors:
        return errors

    final, old = workspace / stage, workspace / f"{stage}.old"
    if old.exists():
        shutil.rmtree(old)
    if final.exists():
        final.rename(old)
    tmp.rename(final)
    if old.exists():
        shutil.rmtree(old)
    return []


def status(workspace: Path) -> dict[str, str]:
    """Map each stage to 'missing', 'fresh' or 'stale'.

    A stage is stale if an input's hash changed, an input is gone, or an
    input lives in a stage that is itself stale.
    """
    workspace = Path(workspace)
    result: dict[str, str] = {}
    for stage in STAGES:
        meta_path = workspace / stage / META
        if not meta_path.is_file():
            result[stage] = "missing"
            continue
        state = "fresh"
        for rel, digest in wsio.read_json(meta_path)["inputs"].items():
            upstream = rel.split("/", 1)[0]
            path = workspace / rel
            if result.get(upstream) == "stale" or not path.exists() or hash_path(path) != digest:
                state = "stale"
                break
        result[stage] = state
    return result
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --with pytest pytest tests/resume_core/test_stages.py`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add skills/resume-core/scripts/rcore/stages.py tests/resume_core/test_stages.py
git commit -m "feat(resume-core): add atomic stage commit and freshness status"
```

---

### Task 6: Source check

**Files:**
- Create: `skills/resume-core/scripts/rcore/sources.py`
- Test: `tests/resume_core/test_sources.py`

**Interfaces:**
- Consumes: `wsio.read_json`, `wsio.read_jsonl`, `wsio.resolve_pointer`, `wsio.resume_highlights` (Task 2); fixture workspace (Task 4).
- Produces:
  - `sources.KnownSources` dataclass: `evidence_ids: set[str]`, `metric_ids: set[str]`, `profile: dict`, `wizard: dict`
  - `sources.load_known(workspace) -> KnownSources` (missing files contribute nothing)
  - `sources.source_error(ref: str, known) -> str | None`
  - `sources.check_bullets(bullets: list[dict], known, label: str) -> list[str]`
  - `sources.check_resume(resume: dict, known, label: str) -> list[str]`
  - `sources.check_file(workspace, rel: str, known: KnownSources | None = None) -> list[str]` (JSON array = bullets file, object = tailored resume)

- [ ] **Step 1: Write the failing test**

`tests/resume_core/test_sources.py`:
```python
from rcore import sources, wsio

TAILORED = ["08-ats/general/resume.json", "08-ats/jobs/fintech-sre/resume.json"]


def test_fixture_bullets_and_resumes_pass(workspace):
    known = sources.load_known(workspace)
    for rel in ["06-bullets/bullets.json", "07-sanitized/bullets.json", *TAILORED]:
        assert sources.check_file(workspace, rel, known) == []


def test_load_known(workspace):
    known = sources.load_known(workspace)
    assert known.evidence_ids == {"ev_191cc8ce", "ev_56410ed1", "ev_99a74656", "ev_cbf558fa"}
    assert known.metric_ids == {"m_1"}
    assert known.profile["basics"]["name"] == "Jordan Rivera"
    assert known.wizard["basics"]["email"] == "jordan.rivera@example.com"


def test_load_known_tolerates_missing_files(tmp_path):
    known = sources.load_known(tmp_path)
    assert known.evidence_ids == set() and known.profile == {}


def test_source_error_cases(workspace):
    known = sources.load_known(workspace)
    assert sources.source_error("ev_191cc8ce", known) is None
    assert sources.source_error("ev_deadbeef", known) == "unknown evidence id"
    assert sources.source_error("metric:m_1", known) is None
    assert sources.source_error("metric:m_9", known) == "unknown metric id"
    assert sources.source_error("resume:/work/1/highlights/0", known) is None
    assert sources.source_error("resume:/work/7", known) == "does not resolve in 03-profile/profile.json"
    assert sources.source_error("wizard:/basics/email", known) is None
    assert sources.source_error("wizard:/basics/phone", known) == "does not resolve in decisions/profile.json"
    assert sources.source_error("gut-feeling", known) == "unrecognized source reference"


def test_bullet_without_sources_fails(workspace):
    path = workspace / "06-bullets" / "bullets.json"
    bullets = wsio.read_json(path)
    bullets[1]["sources"] = []
    bullets[2]["sources"] = ["ev_deadbeef"]
    wsio.write_json(path, bullets)
    assert sources.check_file(workspace, "06-bullets/bullets.json") == [
        "06-bullets/bullets.json: bullet b_2: has no sources",
        "06-bullets/bullets.json: bullet b_3: ev_deadbeef: unknown evidence id",
    ]


def test_resume_highlights_must_match_x_highlights(workspace):
    path = workspace / TAILORED[0]
    resume = wsio.read_json(path)
    resume["work"][0]["highlights"][0] = "Edited without updating x-highlights"
    wsio.write_json(path, resume)
    assert sources.check_file(workspace, TAILORED[0]) == [
        "08-ats/general/resume.json: /work/0: highlights do not match x-highlights"
    ]


def test_imported_highlights_without_x_highlights_fail(workspace):
    assert sources.check_file(workspace, "03-profile/profile.json") == [
        "03-profile/profile.json: /work/1: highlights do not match x-highlights"
    ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest pytest tests/resume_core/test_sources.py`
Expected: collection error, `ImportError: cannot import name 'sources' from 'rcore'`

- [ ] **Step 3: Write the implementation**

`skills/resume-core/scripts/rcore/sources.py`:
```python
"""Source check: every bullet cites at least one source, and every source resolves."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import wsio


@dataclass
class KnownSources:
    evidence_ids: set[str] = field(default_factory=set)
    metric_ids: set[str] = field(default_factory=set)
    profile: dict = field(default_factory=dict)
    wizard: dict = field(default_factory=dict)


def load_known(workspace: Path) -> KnownSources:
    """Collect everything a bullet may cite. Missing files contribute nothing."""
    workspace = Path(workspace)
    known = KnownSources()
    evidence = workspace / "02-evidence" / "evidence.jsonl"
    if evidence.is_file():
        known.evidence_ids = {r["id"] for r in wsio.read_jsonl(evidence)}
    metrics = workspace / "decisions" / "metrics.json"
    if metrics.is_file():
        known.metric_ids = {m["id"] for m in wsio.read_json(metrics)}
    profile = workspace / "03-profile" / "profile.json"
    if profile.is_file():
        known.profile = wsio.read_json(profile)
    wizard = workspace / "decisions" / "profile.json"
    if wizard.is_file():
        known.wizard = wsio.read_json(wizard)
    return known


def _pointer_error(doc: dict, pointer: str, filename: str) -> str | None:
    try:
        wsio.resolve_pointer(doc, pointer)
    except KeyError:
        return f"does not resolve in {filename}"
    return None


def source_error(ref: str, known: KnownSources) -> str | None:
    """Return why a source reference is invalid, or None if it resolves."""
    if ref.startswith("ev_"):
        return None if ref in known.evidence_ids else "unknown evidence id"
    if ref.startswith("metric:"):
        return None if ref[len("metric:"):] in known.metric_ids else "unknown metric id"
    if ref.startswith("resume:"):
        return _pointer_error(known.profile, ref[len("resume:"):], "03-profile/profile.json")
    if ref.startswith("wizard:"):
        return _pointer_error(known.wizard, ref[len("wizard:"):], "decisions/profile.json")
    return "unrecognized source reference"


def check_bullets(bullets: list[dict], known: KnownSources, label: str) -> list[str]:
    errors = []
    for bullet in bullets:
        where = f"{label}: bullet {bullet.get('id')}"
        refs = bullet.get("sources") or []
        if not refs:
            errors.append(f"{where}: has no sources")
        for ref in refs:
            reason = source_error(ref, known)
            if reason:
                errors.append(f"{where}: {ref}: {reason}")
    return errors


def check_resume(resume: dict, known: KnownSources, label: str) -> list[str]:
    """Check a tailored resume: highlights mirror x-highlights, and each is sourced."""
    errors = []
    for section in ("work", "projects"):
        for i, entry in enumerate(resume.get(section, [])):
            texts = [h.get("text") for h in entry.get("x-highlights", [])]
            if entry.get("highlights", []) != texts:
                errors.append(f"{label}: /{section}/{i}: highlights do not match x-highlights")
    bullets = [
        {"id": h.get("bullet_id"), "sources": h.get("sources")}
        for _, h in wsio.resume_highlights(resume)
    ]
    return errors + check_bullets(bullets, known, label)


def check_file(workspace: Path, rel: str, known: KnownSources | None = None) -> list[str]:
    """Check a bullets file (JSON array) or a tailored resume (JSON object)."""
    known = load_known(workspace) if known is None else known
    data = wsio.read_json(Path(workspace) / rel)
    if isinstance(data, list):
        return check_bullets(data, known, rel)
    return check_resume(data, known, rel)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --with pytest pytest tests/resume_core/test_sources.py`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add skills/resume-core/scripts/rcore/sources.py tests/resume_core/test_sources.py
git commit -m "feat(resume-core): add source check for bullets and tailored resumes"
```

---

### Task 7: Terms (confidentiality) check

**Files:**
- Create: `skills/resume-core/scripts/rcore/terms.py`
- Test: `tests/resume_core/test_terms.py`

**Interfaces:**
- Consumes: `wsio.read_json`, `wsio.read_jsonl`, `wsio.iter_strings` (Task 2); fixture workspace (Task 4).
- Produces:
  - `terms.load_denylist(workspace) -> list[str]` (terms whose `replacement` is not null, in file order)
  - `terms.compile_terms(terms: list[str]) -> list[tuple[str, re.Pattern]]` (case-insensitive, whole-word)
  - `terms.scan_json(doc, patterns, label) -> list[str]` (`"<label>:<pointer>: contains denylisted term '<term>'"`)
  - `terms.scan_text(text, patterns, label) -> list[str]` (`"<label>:<line>: ..."`)
  - `terms.check_file(workspace, rel, patterns=None) -> list[str]` (`.json`, `.jsonl`, anything else read as text)

- [ ] **Step 1: Write the failing test**

`tests/resume_core/test_terms.py`:
```python
from rcore import terms


def test_load_denylist_excludes_allowed_terms(workspace):
    assert terms.load_denylist(workspace) == ["Project Falcon", "Contoso Bank"]


def test_unsanitized_bullets_fail_and_outputs_pass(workspace):
    assert terms.check_file(workspace, "06-bullets/bullets.json") == [
        "06-bullets/bullets.json:/0/text: contains denylisted term 'Project Falcon'",
        "06-bullets/bullets.json:/0/text: contains denylisted term 'Contoso Bank'",
    ]
    for rel in ["07-sanitized/bullets.json", "08-ats/general/resume.json",
                "08-ats/jobs/fintech-sre/resume.json"]:
        assert terms.check_file(workspace, rel) == []


def test_matching_is_case_insensitive_whole_word():
    patterns = terms.compile_terms(["Falcon", "C++"])
    assert terms.scan_json({"a": "the FALCON service"}, patterns, "x") == [
        "x:/a: contains denylisted term 'Falcon'"
    ]
    assert terms.scan_json({"a": "Falconry and Falcons"}, patterns, "x") == []
    assert terms.scan_json({"a": "wrote C++ tooling"}, patterns, "x") == [
        "x:/a: contains denylisted term 'C++'"
    ]


def test_keys_are_not_scanned():
    patterns = terms.compile_terms(["secret"])
    assert terms.scan_json({"secret": "fine"}, patterns, "x") == []


def test_text_files_report_line_numbers(workspace):
    (workspace / "06-bullets" / "stories.md").write_text(
        "# Stories\n\nSituation: Contoso Bank checkout was slow.\n", encoding="utf-8"
    )
    assert terms.check_file(workspace, "06-bullets/stories.md") == [
        "06-bullets/stories.md:3: contains denylisted term 'Contoso Bank'"
    ]


def test_jsonl_files_are_scanned(workspace):
    errors = terms.check_file(workspace, "02-evidence/evidence.jsonl")
    assert "02-evidence/evidence.jsonl:/0/title: contains denylisted term 'Project Falcon'" in errors


def test_no_terms_file_means_nothing_denied(tmp_path):
    assert terms.load_denylist(tmp_path) == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest pytest tests/resume_core/test_terms.py`
Expected: collection error, `ImportError: cannot import name 'terms' from 'rcore'`

- [ ] **Step 3: Write the implementation**

`skills/resume-core/scripts/rcore/terms.py`. Whole-word matching uses lookarounds rather than `\b`, so terms that start or end with punctuation (`C++`) still match:
```python
"""Terms check: no denylisted term from decisions/terms.json appears in output text."""
from __future__ import annotations

import re
from pathlib import Path

from . import wsio


def load_denylist(workspace: Path) -> list[str]:
    """Terms with a replacement are denied; terms with replacement null are allowed."""
    path = Path(workspace) / "decisions" / "terms.json"
    if not path.is_file():
        return []
    return [t["term"] for t in wsio.read_json(path) if t["replacement"] is not None]


def compile_terms(terms: list[str]) -> list[tuple[str, re.Pattern]]:
    """Case-insensitive, whole-word patterns (no letter/digit/underscore on either side)."""
    return [
        (term, re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE))
        for term in terms
    ]


def scan_json(doc, patterns, label: str) -> list[str]:
    errors = []
    for pointer, text in wsio.iter_strings(doc):
        for term, pattern in patterns:
            if pattern.search(text):
                errors.append(f"{label}:{pointer or '/'}: contains denylisted term {term!r}")
    return errors


def scan_text(text: str, patterns, label: str) -> list[str]:
    errors = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for term, pattern in patterns:
            if pattern.search(line):
                errors.append(f"{label}:{lineno}: contains denylisted term {term!r}")
    return errors


def check_file(workspace: Path, rel: str, patterns=None) -> list[str]:
    """Scan a .json, .jsonl or text file for denylisted terms."""
    workspace = Path(workspace)
    patterns = compile_terms(load_denylist(workspace)) if patterns is None else patterns
    path = workspace / rel
    if path.suffix == ".json":
        return scan_json(wsio.read_json(path), patterns, rel)
    if path.suffix == ".jsonl":
        return scan_json(wsio.read_jsonl(path), patterns, rel)
    return scan_text(path.read_text(encoding="utf-8"), patterns, rel)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --with pytest pytest tests/resume_core/test_terms.py`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add skills/resume-core/scripts/rcore/terms.py tests/resume_core/test_terms.py
git commit -m "feat(resume-core): add confidentiality terms check"
```

---

### Task 8: Job-version flags check

**Files:**
- Create: `skills/resume-core/scripts/rcore/flags.py`
- Test: `tests/resume_core/test_flags.py`

**Interfaces:**
- Consumes: `ids.text_sha256` (Task 2); `wsio.read_json`, `wsio.resume_highlights` (Task 2); fixture workspace (Task 4).
- Produces: `flags.check_job(workspace, job: str) -> list[str]`. A flag passes only when `decisions/attestations.json` has `(job_slug, bullet_id, text_sha256)` matching the bullet's **current** text in `08-ats/jobs/<job>/resume.json`. Reverted bullets drop out of `flags.json` when the ATS skill re-runs its claim diff, so this check never has to recognize a revert.

- [ ] **Step 1: Write the failing test**

`tests/resume_core/test_flags.py`:
```python
from rcore import flags, ids, wsio

JOB = "fintech-sre"
RESUME = f"08-ats/jobs/{JOB}/resume.json"


def test_attested_flag_passes(workspace):
    assert flags.check_job(workspace, JOB) == []


def test_unattested_flag_fails(workspace):
    wsio.write_json(workspace / "decisions" / "attestations.json", [])
    assert flags.check_job(workspace, JOB) == [
        "08-ats/jobs/fintech-sre: b_1 is flagged (introduces 'SLO compliance', which no "
        "cited source mentions); accept, revert or edit it"
    ]


def test_edit_after_attestation_invalidates_it(workspace):
    resume = wsio.read_json(workspace / RESUME)
    new_text = resume["work"][0]["x-highlights"][0]["text"] + " across 12 regions"
    resume["work"][0]["x-highlights"][0]["text"] = new_text
    resume["work"][0]["highlights"][0] = new_text
    wsio.write_json(workspace / RESUME, resume)
    assert flags.check_job(workspace, JOB) == [
        "08-ats/jobs/fintech-sre: b_1 changed since it was flagged; re-run the claim diff"
    ]


def test_edited_text_with_matching_attestation_passes(workspace):
    resume = wsio.read_json(workspace / RESUME)
    new_text = "Cut p99 checkout latency 40% for a top-10 US bank with a Redis idempotency cache"
    resume["work"][0]["x-highlights"][0]["text"] = new_text
    resume["work"][0]["highlights"][0] = new_text
    wsio.write_json(workspace / RESUME, resume)
    wsio.write_json(workspace / "decisions" / "attestations.json", [
        {"job_slug": JOB, "bullet_id": "b_1", "text_sha256": ids.text_sha256(new_text), "action": "edit"}
    ])
    assert flags.check_job(workspace, JOB) == []


def test_flag_for_missing_bullet_is_stale(workspace):
    path = workspace / f"08-ats/jobs/{JOB}/flags.json"
    flag_list = wsio.read_json(path)
    flag_list[0]["bullet_id"] = "b_99"
    wsio.write_json(path, flag_list)
    assert flags.check_job(workspace, JOB) == [
        "08-ats/jobs/fintech-sre: flag for b_99, which is not in resume.json; re-run the claim diff"
    ]


def test_attestation_for_another_job_does_not_count(workspace):
    atts = wsio.read_json(workspace / "decisions" / "attestations.json")
    atts[0]["job_slug"] = "other-job"
    wsio.write_json(workspace / "decisions" / "attestations.json", atts)
    assert len(flags.check_job(workspace, JOB)) == 1


def test_missing_files(workspace):
    assert flags.check_job(workspace, "nope") == ["08-ats/jobs/nope/resume.json: not found"]
    (workspace / f"08-ats/jobs/{JOB}/flags.json").unlink()
    assert flags.check_job(workspace, JOB) == [
        "08-ats/jobs/fintech-sre/flags.json: not found; run the claim diff for this job"
    ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest pytest tests/resume_core/test_flags.py`
Expected: collection error, `ImportError: cannot import name 'flags' from 'rcore'`

- [ ] **Step 3: Write the implementation**

`skills/resume-core/scripts/rcore/flags.py`:
```python
"""Flags check: every flagged rewrite in a job version was accepted or edited."""
from __future__ import annotations

from pathlib import Path

from . import ids, wsio


def check_job(workspace: Path, job: str) -> list[str]:
    workspace = Path(workspace)
    job_dir = workspace / "08-ats" / "jobs" / job
    label = f"08-ats/jobs/{job}"
    if not (job_dir / "resume.json").is_file():
        return [f"{label}/resume.json: not found"]
    if not (job_dir / "flags.json").is_file():
        return [f"{label}/flags.json: not found; run the claim diff for this job"]

    texts = {h["bullet_id"]: h["text"]
             for _, h in wsio.resume_highlights(wsio.read_json(job_dir / "resume.json"))}
    attestations_path = workspace / "decisions" / "attestations.json"
    attested = {
        (a["job_slug"], a["bullet_id"], a["text_sha256"])
        for a in (wsio.read_json(attestations_path) if attestations_path.is_file() else [])
    }

    errors = []
    for flag in wsio.read_json(job_dir / "flags.json"):
        bullet = flag["bullet_id"]
        if bullet not in texts:
            errors.append(f"{label}: flag for {bullet}, which is not in resume.json; re-run the claim diff")
            continue
        current = ids.text_sha256(texts[bullet])
        if (job, bullet, current) in attested:
            continue
        if current != flag["text_sha256"]:
            errors.append(f"{label}: {bullet} changed since it was flagged; re-run the claim diff")
        else:
            reasons = "; ".join(flag["reasons"])
            errors.append(f"{label}: {bullet} is flagged ({reasons}); accept, revert or edit it")
    return errors
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --with pytest pytest tests/resume_core/test_flags.py`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add skills/resume-core/scripts/rcore/flags.py tests/resume_core/test_flags.py
git commit -m "feat(resume-core): add job-version flags check"
```

---

### Task 9: Workspace creation

**Files:**
- Create: `skills/resume-core/scripts/rcore/workspace.py`
- Test: `tests/resume_core/test_workspace.py`

**Interfaces:**
- Consumes: `config.default_config` (Task 3); `wsio.write_json` (Task 2); `validation.validate_workspace` (Task 4, in tests).
- Produces:
  - `workspace.EMPTY_DECISIONS: dict[str, list | dict]`
  - `workspace.exclude_from_git(workspace: Path) -> str | None` (adds `/<path>/` to the repo's `info/exclude` once; `None` outside a repo or at the repo root)
  - `workspace.init_workspace(workspace: Path, target_role: str = "") -> list[str]` (messages; never overwrites)

Requires `git` ≥ 2.31 on the machine (for `rev-parse --path-format=absolute`). If git is missing or older, the exclude step is silently skipped.

- [ ] **Step 1: Write the failing test**

`tests/resume_core/test_workspace.py`:
```python
import subprocess

from rcore import validation, workspace, wsio


def test_init_creates_valid_workspace(tmp_path):
    ws = tmp_path / "resume-workspace"
    messages = workspace.init_workspace(ws, "Staff Engineer")
    assert "created config.json" in messages
    assert "created decisions/terms.json" in messages
    assert wsio.read_json(ws / "config.json")["target_role"] == "Staff Engineer"
    assert wsio.read_json(ws / "decisions" / "profile.json") == {}
    assert validation.validate_workspace(ws) == []


def test_init_never_overwrites(tmp_path):
    ws = tmp_path / "ws"
    workspace.init_workspace(ws, "A")
    wsio.write_json(ws / "decisions" / "terms.json", [{"term": "Falcon", "replacement": "x", "kind": "codename"}])
    messages = workspace.init_workspace(ws, "B")
    assert messages == ["config.json exists; left unchanged"]
    assert wsio.read_json(ws / "config.json")["target_role"] == "A"
    assert wsio.read_json(ws / "decisions" / "terms.json")[0]["term"] == "Falcon"


def test_init_inside_git_repo_adds_exclude_once(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    ws = tmp_path / "sub" / "resume-workspace"
    workspace.init_workspace(ws)
    workspace.init_workspace(ws)
    exclude = (tmp_path / ".git" / "info" / "exclude").read_text().splitlines()
    assert exclude.count("/sub/resume-workspace/") == 1


def test_init_outside_git_repo(tmp_path):
    messages = workspace.init_workspace(tmp_path / "ws")
    assert not any("git" in m for m in messages)


def test_workspace_at_repo_root_is_not_excluded(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert workspace.exclude_from_git(tmp_path) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest pytest tests/resume_core/test_workspace.py`
Expected: collection error, `ImportError: cannot import name 'workspace' from 'rcore'`

- [ ] **Step 3: Write the implementation**

`skills/resume-core/scripts/rcore/workspace.py`:
```python
"""Create a workspace with default config and empty decision files."""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import config, wsio

EMPTY_DECISIONS = {
    "terms.json": [],
    "projects.json": [],
    "metrics.json": [],
    "profile.json": {},
    "attestations.json": [],
}


def _git(cwd: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(cwd), *args],
                             capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip()


def exclude_from_git(workspace: Path) -> str | None:
    """If the workspace is inside a git repo, add it to .git/info/exclude.

    Returns the excluded pattern, or None when not in a repo or when the
    workspace is the repository root.
    """
    top = _git(workspace, "rev-parse", "--show-toplevel")
    git_path = _git(workspace, "rev-parse", "--path-format=absolute", "--git-path", "info/exclude")
    if top is None or git_path is None:
        return None
    relative = workspace.resolve().relative_to(Path(top).resolve()).as_posix()
    if relative == ".":
        return None
    exclude = Path(git_path)
    pattern = "/" + relative + "/"
    existing = exclude.read_text(encoding="utf-8").splitlines() if exclude.is_file() else []
    if pattern not in existing:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as fh:
            fh.write(pattern + "\n")
    return pattern


def init_workspace(workspace: Path, target_role: str = "") -> list[str]:
    """Create missing workspace files. Never overwrites existing ones.

    Returns human-readable messages describing what was done.
    """
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    messages = []
    cfg = workspace / "config.json"
    if cfg.exists():
        messages.append("config.json exists; left unchanged")
    else:
        wsio.write_json(cfg, config.default_config(target_role))
        messages.append("created config.json")
    for name, empty in EMPTY_DECISIONS.items():
        path = workspace / "decisions" / name
        if not path.exists():
            wsio.write_json(path, empty)
            messages.append(f"created decisions/{name}")
    pattern = exclude_from_git(workspace)
    if pattern:
        messages.append(f"workspace is inside a git repo; added {pattern} to .git/info/exclude")
    return messages
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --with pytest pytest tests/resume_core/test_workspace.py`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add skills/resume-core/scripts/rcore/workspace.py tests/resume_core/test_workspace.py
git commit -m "feat(resume-core): add workspace creation with git exclude"
```

---

### Task 10: Command-line scripts

**Files:**
- Create: `skills/resume-core/scripts/{validate,stage,check_sources,check_terms,check_flags,init_workspace}.py`
- Test: `tests/resume_core/test_cli.py`

**Interfaces:**
- Consumes: `validation.validate_paths`, `validation.validate_workspace`, `stages.begin/commit/status/STAGES`, `sources.load_known/check_file`, `terms.compile_terms/load_denylist/check_file`, `flags.check_job`, `workspace.init_workspace`.
- Produces (what skills run; all take `--workspace WS`, and all exit 0 on success and 1 on failure):
  - `uv run validate.py --workspace WS [PATH ...]`
  - `uv run stage.py --workspace WS begin STAGE` (prints the tmp path)
  - `uv run stage.py --workspace WS commit STAGE --inputs REL [REL ...]`
  - `uv run stage.py --workspace WS status` (prints JSON)
  - `uv run check_sources.py --workspace WS FILE [FILE ...]`
  - `uv run check_terms.py --workspace WS FILE [FILE ...]`
  - `uv run check_flags.py --workspace WS JOB [JOB ...]`
  - `uv run init_workspace.py --workspace WS [--target-role ROLE]`

Each script imports `rcore` from its own folder, which Python puts first on `sys.path` when running a script, so no path setup is needed.

- [ ] **Step 1: Write the failing test**

`tests/resume_core/test_cli.py`:
```python
"""Each CLI runs as a standalone script (the way skills call it) and sets its exit code."""
import json
import subprocess
import sys

from conftest import CORE_SCRIPTS


def run(script, *args):
    return subprocess.run([sys.executable, str(CORE_SCRIPTS / script), *map(str, args)],
                          capture_output=True, text=True)


def test_validate_cli(workspace):
    ok = run("validate.py", "--workspace", workspace)
    assert ok.returncode == 0 and "validation passed" in ok.stdout
    (workspace / "config.json").write_text("{}")
    bad = run("validate.py", "--workspace", workspace, "config.json")
    assert bad.returncode == 1 and "missing required property" in bad.stdout


def test_check_sources_cli(workspace):
    ok = run("check_sources.py", "--workspace", workspace, "08-ats/general/resume.json")
    assert ok.returncode == 0
    bad = run("check_sources.py", "--workspace", workspace, "03-profile/profile.json")
    assert bad.returncode == 1


def test_check_terms_cli(workspace):
    assert run("check_terms.py", "--workspace", workspace, "08-ats/general/resume.json").returncode == 0
    bad = run("check_terms.py", "--workspace", workspace, "06-bullets/bullets.json")
    assert bad.returncode == 1 and "Project Falcon" in bad.stdout


def test_check_flags_cli(workspace):
    assert run("check_flags.py", "--workspace", workspace, "fintech-sre").returncode == 0
    assert run("check_flags.py", "--workspace", workspace, "missing-job").returncode == 1


def test_stage_cli_round_trip(workspace):
    tmp = run("stage.py", "--workspace", workspace, "begin", "05-terms").stdout.strip()
    (workspace / "05-terms.tmp" / "candidates.json").write_text("[]")
    assert tmp.endswith("05-terms.tmp")
    committed = run("stage.py", "--workspace", workspace, "commit", "05-terms", "--inputs", "04-projects")
    assert committed.returncode == 0, committed.stdout
    status = json.loads(run("stage.py", "--workspace", workspace, "status").stdout)
    assert status["05-terms"] == "fresh"


def test_init_workspace_cli(tmp_path):
    result = run("init_workspace.py", "--workspace", tmp_path / "ws", "--target-role", "SRE")
    assert result.returncode == 0 and "workspace ready" in result.stdout
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --with pytest pytest tests/resume_core/test_cli.py`
Expected: `6 failed` (each script exits 2 with `can't open file`)

- [ ] **Step 3: Write the scripts**

`skills/resume-core/scripts/validate.py`:
```python
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Validate workspace files against resume-core schemas.

Usage:
  uv run validate.py --workspace WS             # every committed file
  uv run validate.py --workspace WS PATH [...]  # files or folders, relative to WS
"""
import argparse
import sys
from pathlib import Path

from rcore import validation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    if args.paths:
        errors = validation.validate_paths(args.workspace, args.paths)
    else:
        errors = validation.validate_workspace(args.workspace)
    for error in errors:
        print(error)
    if errors:
        print(f"validation failed: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`skills/resume-core/scripts/stage.py`:
```python
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Stage lifecycle for resume-builder skills.

Usage:
  uv run stage.py --workspace WS begin STAGE
  uv run stage.py --workspace WS commit STAGE --inputs REL [REL ...]
  uv run stage.py --workspace WS status
"""
import argparse
import json
import sys
from pathlib import Path

from rcore import stages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    begin = sub.add_parser("begin", help="create an empty <stage>.tmp/ and print its path")
    begin.add_argument("stage", choices=stages.STAGES)
    commit = sub.add_parser("commit", help="validate <stage>.tmp/ and swap it into place")
    commit.add_argument("stage", choices=stages.STAGES)
    commit.add_argument("--inputs", nargs="*", default=[],
                        help="workspace-relative files or folders this stage read")
    sub.add_parser("status", help="print each stage as missing, fresh or stale")
    args = parser.parse_args()

    if args.command == "begin":
        print(stages.begin(args.workspace, args.stage))
        return 0
    if args.command == "commit":
        errors = stages.commit(args.workspace, args.stage, args.inputs)
        for error in errors:
            print(error)
        if errors:
            print(f"commit of {args.stage} failed; previous output left in place", file=sys.stderr)
            return 1
        print(f"committed {args.stage}")
        return 0
    print(json.dumps(stages.status(args.workspace), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`skills/resume-core/scripts/check_sources.py`:
```python
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Fail if any bullet has no sources or cites a source that does not exist.

Usage: uv run check_sources.py --workspace WS FILE [FILE ...]
FILE is a bullets file (JSON array) or a tailored resume.json, relative to WS.
"""
import argparse
import sys
from pathlib import Path

from rcore import sources


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    known = sources.load_known(args.workspace)
    errors = [e for rel in args.files for e in sources.check_file(args.workspace, rel, known)]
    for error in errors:
        print(error)
    if errors:
        print(f"source check failed: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("source check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`skills/resume-core/scripts/check_terms.py`:
```python
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Fail if any denylisted term from decisions/terms.json appears in the given files.

Usage: uv run check_terms.py --workspace WS FILE [FILE ...]
FILE is .json, .jsonl or text (for example .md), relative to WS.
"""
import argparse
import sys
from pathlib import Path

from rcore import terms


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    patterns = terms.compile_terms(terms.load_denylist(args.workspace))
    errors = [e for rel in args.files for e in terms.check_file(args.workspace, rel, patterns)]
    for error in errors:
        print(error)
    if errors:
        print(f"terms check failed: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("terms check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`skills/resume-core/scripts/check_flags.py`:
```python
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Fail if a job version has flagged rewrites the engineer has not accepted or edited.

Usage: uv run check_flags.py --workspace WS JOB_SLUG [JOB_SLUG ...]
"""
import argparse
import sys
from pathlib import Path

from rcore import flags


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("jobs", nargs="+")
    args = parser.parse_args()
    errors = [e for job in args.jobs for e in flags.check_job(args.workspace, job)]
    for error in errors:
        print(error)
    if errors:
        print(f"flags check failed: {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("flags check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`skills/resume-core/scripts/init_workspace.py`:
```python
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Create a resume-builder workspace (never overwrites existing files).

Usage: uv run init_workspace.py --workspace WS [--target-role "Senior Backend Engineer"]
"""
import argparse
import sys
from pathlib import Path

from rcore import workspace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("--target-role", default="")
    args = parser.parse_args()
    for message in workspace.init_workspace(args.workspace, args.target_role):
        print(message)
    print(f"workspace ready: {args.workspace.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --with pytest pytest tests/resume_core/test_cli.py`
Expected: `6 passed`

- [ ] **Step 5: Check the scripts under uv itself**

Run: `uv run skills/resume-core/scripts/check_flags.py --workspace tests/fixtures/workspace fintech-sre`
Expected: `flags check passed`

Run: `uv run skills/resume-core/scripts/check_terms.py --workspace tests/fixtures/workspace 06-bullets/bullets.json; echo "exit=$?"`
Expected: two lines naming `Project Falcon` and `Contoso Bank`, then `exit=1`

- [ ] **Step 6: Commit**

```bash
git add skills/resume-core/scripts/*.py tests/resume_core/test_cli.py
git commit -m "feat(resume-core): add command-line scripts for skills"
```

---

### Task 11: Skill instructions, portability lint, CI and README

**Files:**
- Create: `skills/resume-core/SKILL.md`, `skills/resume-init/SKILL.md`
- Create: `tests/test_skill_lint.py`, `.github/workflows/test.yml`
- Modify: `README.md` (replace the whole file)

**Interfaces:**
- Consumes: every script from Task 10.
- Produces: the `resume-core` and `resume-init` skills; a lint that every future skill must pass (front matter `name` equals the folder name, allowed entries only, no harness-specific tokens, `../` references only to `resume-core`, PEP 723 header on runnable scripts).

- [ ] **Step 1: Write the failing lint test**

`tests/test_skill_lint.py`:
```python
"""Portability rules from the architecture spec, enforced for every skill."""
import re
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parent.parent / "skills"
ALLOWED_ENTRIES = {"SKILL.md", "scripts", "references", "templates", "schemas"}
FORBIDDEN = ["CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR", "$ARGUMENTS"]
SKILL_DIRS = sorted(p for p in SKILLS.iterdir() if p.is_dir())


def front_matter(text: str) -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "SKILL.md must start with a --- front matter block"
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def test_there_are_skills():
    assert SKILL_DIRS


@pytest.mark.parametrize("skill", SKILL_DIRS, ids=lambda p: p.name)
def test_front_matter(skill):
    fields = front_matter((skill / "SKILL.md").read_text(encoding="utf-8"))
    assert fields.get("name") == skill.name
    assert re.fullmatch(r"[a-z0-9-]{1,64}", fields["name"])
    assert 0 < len(fields.get("description", "")) <= 1024


@pytest.mark.parametrize("skill", SKILL_DIRS, ids=lambda p: p.name)
def test_only_portable_entries(skill):
    extra = {p.name for p in skill.iterdir()} - ALLOWED_ENTRIES
    assert not extra, f"unexpected entries in {skill.name}: {sorted(extra)}"


@pytest.mark.parametrize("skill", SKILL_DIRS, ids=lambda p: p.name)
def test_no_harness_specific_constructs(skill):
    for path in [skill / "SKILL.md", *skill.rglob("*.py")]:
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            assert token not in text, f"{path.relative_to(SKILLS)} uses {token}"


@pytest.mark.parametrize("skill", SKILL_DIRS, ids=lambda p: p.name)
def test_cross_skill_references_only_to_resume_core(skill):
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    for name in re.findall(r"\.\./([A-Za-z0-9_-]+)/", text):
        assert name == "resume-core", f"{skill.name} references ../{name}/"


@pytest.mark.parametrize("skill", SKILL_DIRS, ids=lambda p: p.name)
def test_entry_scripts_declare_inline_metadata(skill):
    for path in skill.glob("scripts/*.py"):
        text = path.read_text(encoding="utf-8")
        if '__name__ == "__main__"' in text:
            assert text.startswith("# /// script\n"), f"{path.name} needs a PEP 723 header"
            assert 'requires-python = ">=3.10"' in text
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --with pytest pytest tests/test_skill_lint.py`
Expected: FAIL. `test_front_matter[resume-core]` raises `FileNotFoundError` for `skills/resume-core/SKILL.md`

- [ ] **Step 3: Write the skill instructions**

`skills/resume-core/SKILL.md`:
````markdown
---
name: resume-core
description: Workspace rules, data formats and hard checks shared by every resume-builder skill. Use when another resume-builder skill says to follow resume-core, or when validating a resume workspace, checking bullet sources, checking for confidential terms, checking job-version flags, or reporting which stages are stale.
---

# resume-core

Shared conventions for resume-builder skills. Other skills refer to this folder as `../resume-core/`.
Run every script with `uv run`. Each one takes `--workspace` (default `resume-workspace`).

## Workspace

```
resume-workspace/
  config.json      decisions/ (terms, projects, metrics, profile, attestations)
  01-raw/  02-evidence/  03-profile/  04-projects/  05-terms/
  06-bullets/  07-sanitized/  08-ats/  out/
```

- Each numbered folder is a **stage**, written by exactly one skill.
- `decisions/` holds the engineer's choices. Only the wizard and checkpoints write to it; regenerating a stage never touches it.
- Never edit another skill's stage folder.

## Writing a stage

1. `uv run ../resume-core/scripts/stage.py --workspace WS begin <stage>` creates an empty `<stage>.tmp/` and prints its path.
2. Write every output file into that folder.
3. `uv run ../resume-core/scripts/stage.py --workspace WS commit <stage> --inputs <each file or folder you read>`
   records input hashes, validates the folder, and swaps it into place.
4. If commit prints errors, fix the named records and commit again. The previous output stays in place until a commit succeeds. Never skip or weaken a check.

`stage.py --workspace WS status` prints each stage as `missing`, `fresh` or `stale`. Before reading a stale stage, tell the engineer and offer to rebuild it.

## Source references

Every bullet's `sources` list holds one or more of:

| Reference | Resolves against |
|---|---|
| `ev_<8 or 12 hex>` | `02-evidence/evidence.jsonl` |
| `metric:<id>` | `decisions/metrics.json` |
| `resume:<JSON Pointer>` | `03-profile/profile.json`, e.g. `resume:/work/1/highlights/0` |
| `wizard:<JSON Pointer>` | `decisions/profile.json`, e.g. `wizard:/basics/email` |

## Checks

| Script | Fails when |
|---|---|
| `validate.py [PATH ...]` | a file does not match its schema in `schemas/`, or an array has duplicate `id`s |
| `check_sources.py FILE ...` | a bullet has no sources or cites one that does not resolve; a resume's `highlights` differ from its `x-highlights` texts |
| `check_terms.py FILE ...` | text contains a term from `decisions/terms.json` whose `replacement` is not null |
| `check_flags.py JOB ...` | a flagged rewrite in `08-ats/jobs/<JOB>/flags.json` has no matching attestation for its current text |

Each prints one line per problem (file, record and rule) and exits 1 on failure.

## Python helpers for other skills' scripts

Scripts in other skills may import the shared library:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import ids, stages, wsio  # noqa: E402
```

`ids.evidence_id(source, native_key)`, `ids.assign_evidence_ids(keys)`, `ids.project_id(evidence_ids)`,
`ids.text_sha256(text)`, `config.metric_prompt_count(n, percent, minimum, maximum)`,
`wsio.read_json / write_json / read_jsonl / write_jsonl / resolve_pointer`.
````

`skills/resume-init/SKILL.md`:
```markdown
---
name: resume-init
description: Set up a resume-builder workspace. Checks that uv is installed and creates the workspace folder, default config.json and empty decision files. Use before any other resume-builder step, or when the engineer asks to start a new resume workspace.
---

# resume-init

Follow `../resume-core/SKILL.md` for workspace conventions.

1. Run `uv --version`. If it fails, show the engineer the install command for their OS and wait for them to confirm it is installed:
   - macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - Homebrew: `brew install uv`
2. Ask where the workspace should live (default `./resume-workspace`) and the target role (for example "Senior Backend Engineer").
3. Run `uv run ../resume-core/scripts/init_workspace.py --workspace <path> --target-role "<role>"`.
   The script never overwrites existing files. If the workspace is inside a git repository it adds the folder to `.git/info/exclude` so work data is not committed by accident.
4. Report the script's output to the engineer. Chromium for PDF rendering is installed later, the first time a resume is rendered.
```

- [ ] **Step 4: Run the lint to verify it passes**

Run: `uv run --with pytest pytest tests/test_skill_lint.py`
Expected: `11 passed`

- [ ] **Step 5: Add CI and update the README**

`.github/workflows/test.yml`:
```yaml
name: test

on:
  push:
  pull_request:

jobs:
  pytest:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: ["3.10", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv run --python ${{ matrix.python }} --with pytest pytest
```

`README.md`:
````markdown
# resume-builder
Discover your most impactful work and prove the value you have delivered.

A Claude Code plugin of portable agent skills that builds an evidence-backed engineering resume.
Design: [architecture spec](docs/superpowers/specs/2026-09-24-resume-builder-architecture-design.md).

## Development

Requires [uv](https://docs.astral.sh/uv/). Scripts support Python 3.10 and later.

```bash
uv run --with pytest pytest
```

Shared workspace conventions, schemas and checks live in `skills/resume-core/` (start with its `SKILL.md`).
````

- [ ] **Step 6: Run the full suite on both Python bounds**

Run: `uv run --with pytest pytest`
Expected: `93 passed`

Run: `uv run --python 3.10 --with pytest pytest`
Expected: `93 passed` (uv downloads Python 3.10 if it is not installed)

- [ ] **Step 7: Commit**

```bash
git add skills/resume-core/SKILL.md skills/resume-init/SKILL.md tests/test_skill_lint.py .github/workflows/test.yml README.md
git commit -m "feat(resume-core): add skill instructions, portability lint and CI"
```

---

## Done when

- `uv run --with pytest pytest` reports 93 passed on Python 3.10 and on the latest Python.
- `git grep -nE "^(import|from) " skills/resume-core` shows only standard-library modules and `rcore`.
- The CI workflow is green on the pushed branch.
