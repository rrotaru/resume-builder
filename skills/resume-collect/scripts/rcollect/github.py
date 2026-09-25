"""GitHub pull requests, reviews and issues: REST, GraphQL or gh CLI JSON."""
from __future__ import annotations

import re

from . import refs
from .common import (Draft, Result, as_list, clean, excerpt, first, iterate, names, parse_timestamp,
                     raw_ref, same)

SOURCE = "github"
_WEB = re.compile(r"https?://([^/\s]+)/([\w.-]+)/([\w.-]+)/(pull|pulls|issues)/(\d+)", re.IGNORECASE)
_API_REPO = re.compile(r"/repos/([\w.-]+)/([\w.-]+)/?$")
_PR_FIELDS = ("merged_at", "mergedAt", "head", "headRefName", "merge_commit_sha", "mergeCommit")


def _web_url(item: dict) -> str | None:
    for key in ("html_url", "url"):
        value = item.get(key)
        if isinstance(value, str) and _WEB.match(value) and "/repos/" not in value:
            return value
    return None


def _repository(item: dict, web: str | None) -> str | None:
    name = first(item, "base.repo.full_name", "repository.nameWithOwner", "repository.full_name")
    if isinstance(name, str) and name.count("/") == 1:
        return name
    api = item.get("repository_url")
    if isinstance(api, str) and _API_REPO.search(api):
        return "/".join(_API_REPO.search(api).groups())
    match = _WEB.match(web) if web else None
    return f"{match.group(2)}/{match.group(3)}" if match else None


def _is_pull_request(item: dict, web: str | None) -> bool:
    if isinstance(item.get("isPullRequest"), bool):
        return item["isPullRequest"]
    if "pull_request" in item or any(key in item for key in _PR_FIELDS):
        return True
    match = _WEB.match(web) if web else None
    return bool(match and match.group(4).lower().startswith("pull"))


def _reviewed_by(query: str | None, username: str) -> bool:
    """The query asks for pull requests reviewed by the engineer (not negated with a leading -)."""
    return any(same(login, username)
               for login in re.findall(r"(?<![\w-])reviewed-by:@?([\w-]+)", query or "", re.IGNORECASE))


def _engineer_reviews(item: dict, username: str) -> list[str]:
    """Submission times of the engineer's reviews embedded in the item (possibly empty strings)."""
    times = []
    for key in ("reviews", "latestReviews"):
        for review in as_list(item.get(key)):
            if isinstance(review, dict) and same(first(review, "user.login", "author.login"), username):
                times.append(first(review, "submitted_at", "submittedAt") or "")
    return times


def _stats(item: dict) -> dict | None:
    values = (item.get("additions"), item.get("deletions"), first(item, "changed_files", "changedFiles"))
    if all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in values):
        return {"additions": values[0], "deletions": values[1], "files": values[2]}
    return None


def normalize(pages, rel: str, label: str, username: str, time_range: dict | None) -> Result:
    result = Result(SOURCE, label)
    for page, index, item in iterate(pages, result):
        web = _web_url(item)
        repo = _repository(item, web)
        number = item.get("number")
        if not (isinstance(number, int) and not isinstance(number, bool)):
            match = _WEB.match(web) if web else None
            number = int(match.group(5)) if match else None
        title = item.get("title")
        created = parse_timestamp(first(item, "created_at", "createdAt"))
        problem = ("cannot tell the repository" if repo is None
                   else "no number" if number is None
                   else "no title" if not isinstance(title, str)
                   else f"created_at {first(item, 'created_at', 'createdAt')!r} is not a timestamp"
                   if created is None else None)
        if problem:
            result.bad_row(page.line, problem, index)
            continue
        is_pr = _is_pull_request(item, web)
        merged_raw = first(item, "merged_at", "mergedAt", "pull_request.merged_at")
        merged = parse_timestamp(merged_raw)
        closed = merged or parse_timestamp(first(item, "closed_at", "closedAt"))
        state_raw = item.get("state")
        if merged or item.get("merged") is True or (isinstance(state_raw, str) and state_raw.lower() == "merged"):
            state = "merged"
        else:
            state = state_raw.lower() if isinstance(state_raw, str) else None
        author = first(item, "user.login", "author.login")
        assignees = names(item.get("assignees"), "login") + names([item.get("assignee")], "login")
        body = item.get("body") if isinstance(item.get("body"), str) else ""
        draft = Draft(
            source=SOURCE, kind="issue", native_key=f"{repo}#{number}", title=clean(title),
            engineer_role="author", created_at=created, raw_ref=raw_ref(rel, page.line, index),
            url=web, excerpt=excerpt(body), closed_at=closed, state=state,
            labels=names(item.get("labels"), "name"),
        )
        branch = first(item, "head.ref", "headRefName")
        draft.refs = (refs.find(f"{title}\n{body}", github_repo=repo) | refs.branch_keys(branch))
        if is_pr:
            draft.kind = "pr"
            if same(author, username):
                draft.stats = _stats(item)
                sha = first(item, "merge_commit_sha", "mergeCommit.oid")
                if state == "merged" and isinstance(sha, str):
                    draft.merge_shas.add(sha.lower())
            else:
                reviews = _engineer_reviews(item, username)
                if not reviews and not _reviewed_by(page.query, username):
                    result.not_mine += 1
                    result.others[author or "(unknown)"] += 1
                    continue
                draft.kind, draft.engineer_role = "review", "reviewer"
                submitted = sorted(t for t in (parse_timestamp(r) for r in reviews) if t)
                if submitted:
                    draft.created_at = submitted[0]
        elif any(same(a, username) for a in assignees):
            draft.engineer_role = "assignee"
        elif not same(author, username):
            result.not_mine += 1
            result.others[author or "(unknown)"] += 1
            continue
        result.keep(draft, closed, time_range)
    return result
