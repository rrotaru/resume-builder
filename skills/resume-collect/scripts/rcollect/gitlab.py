"""GitLab merge requests and issues: REST or glab JSON."""
from __future__ import annotations

import re

from . import refs
from .common import Draft, Result, clean, excerpt, first, iterate, names, parse_timestamp, raw_ref, same

SOURCE = "gitlab"
_REFERENCE = re.compile(r"^((?:[\w.-]+/)+[\w.-]+)([!#])(\d+)$")
_WEB = re.compile(r"https?://[^/\s]+/((?:[\w.-]+/)+[\w.-]+)/-/(merge_requests|issues)/(\d+)", re.IGNORECASE)
_STATES = {"opened": "open", "merged": "merged", "closed": "closed", "locked": "locked"}


def _identity(item: dict) -> tuple[str, str, int] | None:
    """(project path, "!" or "#", iid) from references.full or web_url."""
    full = first(item, "references.full")
    match = _REFERENCE.match(full) if isinstance(full, str) else None
    if match:
        return match.group(1), match.group(2), int(match.group(3))
    web = item.get("web_url")
    match = _WEB.match(web) if isinstance(web, str) else None
    if match:
        return match.group(1), "!" if match.group(2).lower() == "merge_requests" else "#", int(match.group(3))
    return None


def _reviewer_query(query: str | None, username: str) -> bool:
    return any(same(name, username) for name in re.findall(
        r"reviewer_?username\s*[=:]\s*\"?([\w.-]+)", query or "", re.IGNORECASE))


def normalize(pages, rel: str, label: str, username: str, time_range: dict | None) -> Result:
    result = Result(SOURCE, label)
    for page, index, item in iterate(pages, result):
        identity = _identity(item)
        title = item.get("title")
        created = parse_timestamp(item.get("created_at"))
        problem = ("cannot tell the project and number (no references.full or web_url)" if identity is None
                   else "no title" if not isinstance(title, str)
                   else f"created_at {item.get('created_at')!r} is not a timestamp" if created is None
                   else None)
        if problem:
            result.bad_row(page.line, problem, index)
            continue
        project, sign, iid = identity
        merged = parse_timestamp(item.get("merged_at"))
        closed = merged or parse_timestamp(item.get("closed_at"))
        state = item.get("state")
        state = _STATES.get(state.lower(), state.lower()) if isinstance(state, str) else None
        author = first(item, "author.username")
        assignees = names(item.get("assignees"), "username") + names([item.get("assignee")], "username")
        body = item.get("description") if isinstance(item.get("description"), str) else ""
        web = item.get("web_url") if isinstance(item.get("web_url"), str) else None
        draft = Draft(
            source=SOURCE, kind="mr" if sign == "!" else "issue", native_key=f"{project}{sign}{iid}",
            title=clean(title), engineer_role="author", created_at=created,
            raw_ref=raw_ref(rel, page.line, index), url=web, excerpt=excerpt(body), closed_at=closed,
            state=state, labels=names(item.get("labels"), "name", "title"),
        )
        draft.refs = refs.find(f"{title}\n{body}", gitlab_project=project) | refs.branch_keys(
            item.get("source_branch"))
        if sign == "!":
            reviewers = names(item.get("reviewers"), "username")
            if same(author, username):
                if state == "merged":
                    for key in ("merge_commit_sha", "squash_commit_sha"):
                        if isinstance(item.get(key), str):
                            draft.merge_shas.add(item[key].lower())
            elif any(same(r, username) for r in reviewers) or _reviewer_query(page.query, username):
                draft.kind, draft.engineer_role = "review", "reviewer"
            elif any(same(a, username) for a in assignees):
                draft.engineer_role = "assignee"
            else:
                result.not_mine += 1
                result.others[author or "(unknown)"] += 1
                continue
        elif any(same(a, username) for a in assignees):
            draft.engineer_role = "assignee"
        elif not same(author, username):
            result.not_mine += 1
            result.others[author or "(unknown)"] += 1
            continue
        result.keep(draft, closed, time_range)
    return result
