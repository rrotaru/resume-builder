"""Jira tickets and epics: REST issues (API 2 or 3) or rows of a CSV export."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import refs
from .common import Draft, Result, clean, excerpt, first, iterate, names, parse_timestamp, raw_ref, same

SOURCE = "jira"
_USER_FIELDS = ("name", "key", "accountId", "emailAddress", "displayName")
_ADF_BLOCKS = {"paragraph", "heading", "listItem", "codeBlock", "blockquote", "tableRow", "rule", "panel"}
_ADF_LINKS = {"inlineCard", "blockCard", "embedCard"}


@dataclass
class _Issue:
    key: object = None
    issue_id: str | None = None
    title: object = None
    kind: str = "ticket"
    state: str | None = None
    created: object = None
    resolved: object = None
    description: str = ""
    labels: list = field(default_factory=list)
    parents: list = field(default_factory=list)
    assignee: list = field(default_factory=list)   # identity strings
    reporter: list = field(default_factory=list)
    assignee_name: str | None = None               # for the report of other people's items
    url: str | None = None


def adf_text(node) -> str:
    """Plain text of an Atlassian Document Format node, with a line break after each block."""
    parts: list[str] = []

    def walk(n) -> None:
        if isinstance(n, list):
            for child in n:
                walk(child)
            return
        if not isinstance(n, dict):
            return
        kind = n.get("type")
        attrs = n.get("attrs") if isinstance(n.get("attrs"), dict) else {}
        if kind == "text" and isinstance(n.get("text"), str):
            parts.append(n["text"])
        elif kind == "hardBreak":
            parts.append("\n")
        elif kind in _ADF_LINKS and isinstance(attrs.get("url"), str):
            parts.append(f" {attrs['url']} ")
        elif kind == "mention" and isinstance(attrs.get("text"), str):
            parts.append(attrs["text"])
        walk(n.get("content"))
        if kind in _ADF_BLOCKS:
            parts.append("\n")

    walk(node)
    return "".join(parts)


def _user(value) -> list[str]:
    if isinstance(value, dict):
        return [value[k] for k in _USER_FIELDS if isinstance(value.get(k), str) and value[k]]
    return [value] if isinstance(value, str) and value else []


def _from_rest(item: dict) -> _Issue:
    fields = item["fields"]
    description = fields.get("description")
    if isinstance(description, dict):
        description = adf_text(description)
    self_url = item.get("self")
    site = self_url.split("/rest/", 1)[0] if isinstance(self_url, str) and "/rest/" in self_url else None
    key = item.get("key")
    issue_type = first(fields, "issuetype.name")
    return _Issue(
        key=key, issue_id=str(item["id"]) if isinstance(item.get("id"), (str, int)) else None,
        title=fields.get("summary"),
        kind="epic" if isinstance(issue_type, str) and issue_type.strip().lower() == "epic" else "ticket",
        state=first(fields, "status.name"), created=fields.get("created"), resolved=fields.get("resolutiondate"),
        description=description if isinstance(description, str) else "",
        labels=names(fields.get("labels"), "name"),
        parents=[p for p in (first(fields, "parent.key"), first(fields, "epic.key")) if isinstance(p, str)],
        assignee=_user(fields.get("assignee")), reporter=_user(fields.get("reporter")),
        assignee_name=first(fields, "assignee.displayName", "assignee.name", "assignee.emailAddress"),
        url=f"{site}/browse/{key}" if site and isinstance(key, str) else None,
    )


def _csv_values(row: dict, name: str) -> list[str]:
    values = []
    for header, value in row.items():
        if isinstance(header, str) and header.strip().lower() == name:
            for v in value if isinstance(value, list) else [value]:
                if isinstance(v, str) and v.strip():
                    values.append(v.strip())
    return values


def _csv_one(row: dict, *names_: str):
    for name in names_:
        values = _csv_values(row, name)
        if values:
            return values[0]
    return None


def _from_csv(row: dict) -> _Issue:
    issue_type = _csv_one(row, "issue type")
    return _Issue(
        key=_csv_one(row, "issue key"), issue_id=_csv_one(row, "issue id"), title=_csv_one(row, "summary") or "",
        kind="epic" if issue_type and issue_type.lower() == "epic" else "ticket",
        state=_csv_one(row, "status"), created=_csv_one(row, "created"), resolved=_csv_one(row, "resolved"),
        description=_csv_one(row, "description") or "",
        labels=names(_csv_values(row, "labels")),
        parents=[p for p in (_csv_one(row, "parent", "parent key", "parent id"),
                             _csv_one(row, "custom field (epic link)")) if p],
        assignee=_csv_values(row, "assignee") + _csv_values(row, "assignee id"),
        reporter=_csv_values(row, "reporter") + _csv_values(row, "reporter id"),
        assignee_name=_csv_one(row, "assignee"),
    )


def _issue(item: dict) -> _Issue | None:
    if isinstance(item.get("fields"), dict):
        return _from_rest(item)
    if any(isinstance(h, str) and h.strip().lower() == "issue key" for h in item):
        return _from_csv(item)
    return None


def normalize(pages, rel: str, label: str, username: str, time_range: dict | None) -> Result:
    result = Result(SOURCE, label)
    rows = []
    for page, index, item in iterate(pages, result):
        issue = _issue(item)
        if issue is None:
            result.bad_row(page.line, 'neither a Jira REST issue ("key", "fields") nor a CSV row ("Issue key")',
                           index)
            continue
        rows.append((page, index, issue))
    keys_by_id = {i.issue_id: i.key for _, _, i in rows if i.issue_id and isinstance(i.key, str)}
    for page, index, issue in rows:
        created = parse_timestamp(issue.created)
        resolved = parse_timestamp(issue.resolved) if issue.resolved else None
        problem = ("no issue key" if not isinstance(issue.key, str) or not issue.key.strip()
                   else "no summary" if not isinstance(issue.title, str)
                   else f"created {issue.created!r} is not a timestamp" if created is None
                   else f"resolved {issue.resolved!r} is not a timestamp" if issue.resolved and resolved is None
                   else None)
        if problem:
            result.bad_row(page.line, problem, index)
            continue
        if any(same(v, username) for v in issue.assignee):
            role = "assignee"
        elif any(same(v, username) for v in issue.reporter):
            role = "reporter"
        else:
            result.not_mine += 1
            result.others[issue.assignee_name or "(unassigned)"] += 1
            continue
        key = issue.key.strip()
        draft = Draft(
            source=SOURCE, kind=issue.kind, native_key=key, title=clean(issue.title), engineer_role=role,
            created_at=created, raw_ref=raw_ref(rel, page.line, index), url=issue.url,
            excerpt=excerpt(issue.description), closed_at=resolved,
            state=clean(issue.state) or None if isinstance(issue.state, str) else None, labels=issue.labels,
        )
        draft.refs = refs.find(f"{issue.title}\n{issue.description}")
        for parent in issue.parents:
            parent = keys_by_id.get(parent, parent) if re.fullmatch(r"\d+", parent) else parent
            if isinstance(parent, str) and not parent.isdigit():
                draft.refs.add((SOURCE, parent.strip()))
        result.keep(draft, resolved, time_range)
    return result
