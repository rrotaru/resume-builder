"""References to other work items found in text: Jira keys, GitHub and GitLab references and URLs.

Each reference is (source, native_key). Linking keeps only references that
name an evidence item, so a candidate that names nothing is harmless.
"""
from __future__ import annotations

import re

_JIRA_KEY = re.compile(r"(?<![A-Za-z0-9_])([A-Z][A-Z0-9_]+-[1-9][0-9]*)(?![A-Za-z0-9_])")
_GITHUB_URL = re.compile(r"https?://[^/\s]+/([\w.-]+)/([\w.-]+)/(?:pull|pulls|issues)/(\d+)", re.IGNORECASE)
_GITLAB_URL = re.compile(r"https?://[^/\s]+/((?:[\w.-]+/)+[\w.-]+)/-/(merge_requests|issues)/(\d+)",
                         re.IGNORECASE)
_PATH_REF = re.compile(r"(?<![\w./-])((?:[\w.-]+/)+[\w.-]+)([#!])(\d+)\b")
_BARE_REF = re.compile(r"(?<![\w&/#!])([#!])(\d+)\b")


def jira_keys(text: str) -> set[tuple[str, str]]:
    return {("jira", key) for key in _JIRA_KEY.findall(text or "")}


def branch_keys(branch) -> set[tuple[str, str]]:
    """Jira keys in a branch name, which is often lower case (pay-42-cache)."""
    return jira_keys(branch.upper()) if isinstance(branch, str) else set()


def find(text, github_repo: str | None = None, gitlab_project: str | None = None) -> set[tuple[str, str]]:
    """Every reference in text. Bare #n and !n resolve against the item's own repository or project."""
    if not isinstance(text, str) or not text:
        return set()
    found = jira_keys(text)
    for owner, repo, number in _GITHUB_URL.findall(text):
        found.add(("github", f"{owner}/{repo}#{number}"))
    for path, kind, number in _GITLAB_URL.findall(text):
        found.add(("gitlab", f"{path}{'!' if kind.lower() == 'merge_requests' else '#'}{number}"))
    for path, sign, number in _PATH_REF.findall(text):
        found.add(("gitlab", f"{path}{sign}{number}"))
        if sign == "#" and path.count("/") == 1:
            found.add(("github", f"{path}#{number}"))
    for sign, number in _BARE_REF.findall(text):
        if sign == "#" and github_repo:
            found.add(("github", f"{github_repo}#{number}"))
        if gitlab_project:
            found.add(("gitlab", f"{gitlab_project}{sign}{number}"))
    return found
