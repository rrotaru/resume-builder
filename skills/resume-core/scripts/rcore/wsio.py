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


class JsonlError(ValueError):
    """A JSONL line that is not valid JSON."""

    def __init__(self, label: str, lineno: int, msg: str):
        super().__init__(f"{label}:{lineno}: invalid JSON: {msg}")
        self.lineno = lineno
        self.msg = msg


def _parse_jsonl(text: str, label: str) -> list:
    records = []
    # Split on "\n" only: str.splitlines() also breaks on U+2028, \x1c and others inside strings.
    for lineno, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise JsonlError(label, lineno, exc.msg) from exc
    return records


def read_jsonl(path: Path) -> list[dict]:
    """Read one JSON value per non-blank line. Raises ValueError naming the bad line."""
    return _parse_jsonl(Path(path).read_text(encoding="utf-8"), str(path))


def load(workspace: Path, rel: str, fmt: str = "json"):
    """Read a workspace file for a check without raising.

    fmt is "json", "jsonl" or "text". Returns (data, None) on success, or
    (None, "<rel>: <problem>") when the file is missing, unreadable, not
    UTF-8 text or not valid JSON.
    """
    path = Path(workspace) / rel
    if not path.is_file():
        return None, f"{rel}: not found"
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None, f"{rel}: not UTF-8 text"
    except OSError as exc:
        return None, f"{rel}: cannot be read ({exc.strerror})"
    try:
        if fmt == "json":
            return json.loads(text), None
        if fmt == "jsonl":
            return _parse_jsonl(text, rel), None
    except JsonlError as exc:
        return None, f"{rel}: invalid JSON on line {exc.lineno}: {exc.msg}"
    except json.JSONDecodeError as exc:
        return None, f"{rel}: invalid JSON: {exc}"
    return text, None


def _jsonl_line(record) -> str:
    # json.dumps escapes control characters below U+0020 but not U+0085, U+2028 or U+2029,
    # which str.splitlines() also breaks on; escape them so every reader keeps the line whole.
    text = json.dumps(record, ensure_ascii=False, sort_keys=True)
    return text.replace("\x85", "\\u0085").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def write_jsonl(path: Path, records) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(_jsonl_line(r) + "\n" for r in records), encoding="utf-8")


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
