"""Raw records at an evidence item's raw_ref: the people named on it, and a commit's repository."""
from __future__ import annotations

import json
import re
from pathlib import Path

RAW_REF = re.compile(r"^(01-raw/[^/\\:]+\.jsonl):([1-9][0-9]*)#/items/(0|[1-9][0-9]*)$")
_JIRA_USER_FIELDS = ("displayName", "name", "key", "emailAddress", "accountId")


class RawReader:
    """Reads each raw file once. A record that cannot be read gives None and one warning per file."""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self._lines: dict[str, list[str] | None] = {}
        self._warned: dict[str, str] = {}

    @property
    def warnings(self) -> list[str]:
        return [f"{message}; its items add no people to the signals" for message in self._warned.values()]

    def _warn(self, key: str, message: str) -> None:
        self._warned.setdefault(key, message)

    def _file(self, rel: str) -> list[str] | None:
        if rel not in self._lines:
            path = self.workspace / rel
            try:
                self._lines[rel] = path.read_text(encoding="utf-8").split("\n")
            except FileNotFoundError:
                self._lines[rel] = None
                self._warn(rel, f"{rel}: not found")
            except (OSError, UnicodeDecodeError) as exc:
                self._lines[rel] = None
                self._warn(rel, f"{rel}: cannot be read ({exc})")
        return self._lines[rel]

    def item(self, raw_ref) -> dict | None:
        match = RAW_REF.match(raw_ref) if isinstance(raw_ref, str) else None
        if match is None:
            if raw_ref is not None:
                self._warn(str(raw_ref), f"raw_ref {raw_ref!r} is not 01-raw/<file>:<line>#/items/<index>")
            return None
        rel, line, index = match.group(1), int(match.group(2)), int(match.group(3))
        lines = self._file(rel)
        if lines is None:
            return None
        try:
            page = json.loads(lines[line - 1]) if line <= len(lines) else None
        except json.JSONDecodeError:
            page = None
        items = page.get("items") if isinstance(page, dict) else None
        record = items[index] if isinstance(items, list) and index < len(items) else None
        if not isinstance(record, dict):
            self._warn(rel, f"{rel}: line {line} has no item {index}")
            return None
        return record


# People ----------------------------------------------------------------------

def _get(node, path: str):
    for key in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _as_list(value) -> list:
    """A list, or GraphQL {"nodes": [...]}, as a list; anything else as []."""
    if isinstance(value, dict) and isinstance(value.get("nodes"), list):
        return value["nodes"]
    return value if isinstance(value, list) else []


def _text(value) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _login_people(item: dict, key: str) -> list[list[str]]:
    """GitHub or GitLab: author, assignee and assignees, each as a one-name identity."""
    found = [_get(item, f"user.{key}"), _get(item, f"author.{key}"), _get(item, f"assignee.{key}")]
    found += [entry.get(key) if isinstance(entry, dict) else entry for entry in _as_list(item.get("assignees"))]
    return [[name] for name in map(_text, found) if name]


def _jira_user(value) -> list[str]:
    if isinstance(value, dict):
        return [v for v in (_text(value.get(k)) for k in _JIRA_USER_FIELDS) if v]
    name = _text(value)
    return [name] if name else []


def _csv(item: dict, header: str) -> list[str]:
    values = []
    for key, value in item.items():
        if isinstance(key, str) and key.strip().lower() == header:
            for v in value if isinstance(value, list) else [value]:
                if _text(v):
                    values.append(_text(v))
    return values


def _jira_role(item: dict, role: str) -> list[str]:
    """One Jira person (assignee or reporter): every identity string the record gives them."""
    if isinstance(item.get("fields"), dict):
        return _jira_user(item["fields"].get(role))
    return _csv(item, role) + _csv(item, f"{role} id")


def people(source: str, item: dict) -> list[list[str]]:
    """The people named as author, assignee or reporter on a raw record.

    Each person is a list of identity strings, the first one being their name.
    Git commits (always the engineer's) and review files have none.
    """
    if source == "github":
        return _login_people(item, "login")
    if source == "gitlab":
        return _login_people(item, "username")
    if source == "jira":
        return [p for p in (_jira_role(item, "assignee"), _jira_role(item, "reporter")) if p]
    return []


def jira_reporter(item: dict) -> list[str]:
    return _jira_role(item, "reporter")


def same(a: str, b) -> bool:
    return isinstance(b, str) and a.strip().casefold() == b.strip().casefold() != ""


def is_engineer(identities: list[str], username) -> bool:
    return any(same(identity, username) for identity in identities)


def commit_repo(item: dict) -> str | None:
    """A commit's repository: its remote without the host, else its folder's name."""
    remote = _text(item.get("remote"))
    if remote and "/" in remote:
        return remote.split("/", 1)[1]
    folder = _text(item.get("repo"))
    if folder:
        name = re.split(r"[\\/]", folder.rstrip("/\\"))[-1]
        return name or None
    return None
