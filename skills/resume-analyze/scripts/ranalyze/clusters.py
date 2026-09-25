"""Clusters of linked evidence and their signals (04-projects/signals.json)."""
from __future__ import annotations

import re
from pathlib import Path

from . import raw
from .common import (KINDS, OPEN_KINDS, day, days_between, is_authored, is_perf_review, is_reported,
                     last_timestamp)

_REPO_KEY = re.compile(r"^(.+)[#!][0-9]+$")


def build(evidence: list[dict]) -> list[list[dict]]:
    """Connected components of the link graph, links read both ways, without performance reviews.

    Items keep evidence order inside a cluster, and clusters are ordered by their first item.
    """
    items = [item for item in evidence if not is_perf_review(item)]
    position = {item["id"]: i for i, item in enumerate(items)}
    parent = list(range(len(items)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, item in enumerate(items):
        for target in item.get("links", []):
            j = position.get(target)
            if j is not None:
                a, b = root(i), root(j)
                if a != b:
                    parent[max(a, b)] = min(a, b)
    groups: dict[int, list[dict]] = {}
    for i, item in enumerate(items):
        groups.setdefault(root(i), []).append(item)
    return sorted(groups.values(), key=lambda members: position[members[0]["id"]])


def mentions(evidence: list[dict]) -> dict[str, list[str]]:
    """Evidence ID -> the performance reviews that link to it, in evidence order."""
    found: dict[str, list[str]] = {}
    for item in evidence:
        if is_perf_review(item):
            for target in item.get("links", []):
                found.setdefault(target, [])
                if item["id"] not in found[target]:
                    found[target].append(item["id"])
    return found


def _label(items: list[dict]) -> str:
    for kinds in (("epic",), ("ticket", "issue")):
        for item in items:
            if item["kind"] in kinds:
                return item["title"]
    return items[0]["title"]


def _repo(item: dict, record: dict | None) -> str | None:
    if item["source"] in ("github", "gitlab"):
        match = _REPO_KEY.match(item["native_key"])
        return match.group(1) if match else None
    if item["source"] == "git" and record is not None:
        return raw.commit_repo(record)
    return None


def counts(items: list[dict], mentioned: dict[str, list[str]]) -> dict:
    """The evidence-only counts, for a cluster or a project."""
    reviews: list[str] = []
    for item in items:
        reviews += [r for r in mentioned.get(item["id"], []) if r not in reviews]
    return {
        "authored": sum(1 for i in items if is_authored(i)),
        "reviewed": sum(1 for i in items if i["kind"] == "review"),
        "assigned": sum(1 for i in items if i["engineer_role"] == "assignee"),
        "reported": sum(1 for i in items if is_reported(i)),
        "review_mentions": reviews,
    }


def cluster_signals(cluster_id: str, items: list[dict], reader: raw.RawReader, usernames: dict,
                    mentioned: dict[str, list[str]], review_order: dict[str, int]) -> dict:
    start = min(day(i["created_at"]) for i in items)
    end = max(day(last_timestamp(i)) for i in items)
    kinds = {kind: sum(1 for i in items if i["kind"] == kind) for kind in KINDS}
    authored = [i for i in items if is_authored(i)]
    stats = {key: sum(i.get("stats", {}).get(key, 0) for i in authored) for key in ("additions", "deletions",
                                                                                    "files")}
    repos, jira_projects, people = set(), set(), set()
    epics_created = []
    for item in items:
        record = reader.item(item.get("raw_ref")) if item["source"] in ("github", "gitlab", "jira", "git") else None
        repo = _repo(item, record)
        if repo:
            repos.add(repo)
        if item["source"] == "jira":
            jira_projects.add(item["native_key"].rsplit("-", 1)[0])
        username = usernames.get(item["source"])
        if record is not None:
            for identities in raw.people(item["source"], record):
                if not raw.is_engineer(identities, username):
                    people.add((item["source"], identities[0].casefold()))
        if item["kind"] == "epic":
            created = item["engineer_role"] == "reporter"
            if record is not None and item["source"] == "jira":
                created = created or raw.is_engineer(raw.jira_reporter(record), username)
            if created:
                epics_created.append(item["id"])
    first_authored = min((i["created_at"] for i in authored), default=None)
    counted = counts(items, mentioned)
    return {
        "id": cluster_id,
        "label": _label(items),
        "evidence_ids": [i["id"] for i in items],
        "start": start,
        "end": end,
        "days": days_between(start, end),
        "kinds": {kind: n for kind, n in kinds.items() if n},
        "authored": counted["authored"],
        "reviewed": counted["reviewed"],
        "assigned": counted["assigned"],
        "reported": counted["reported"],
        "stats": stats,
        "repos": sorted(repos),
        "jira_projects": sorted(jira_projects),
        "contributors": len(people),
        "epics": [i["id"] for i in items if i["kind"] == "epic"],
        "epics_created": epics_created,
        "first_authored_at": day(first_authored) if first_authored else None,
        "authored_first": first_authored is not None and all(
            i["created_at"] >= first_authored for i in items if i["kind"] == "review"),
        "open_items": sum(1 for i in items if i["kind"] in OPEN_KINDS and not i.get("closed_at")),
        "review_mentions": sorted(counted["review_mentions"], key=review_order.__getitem__),
    }


def compute(workspace: Path, cfg: dict, evidence: list[dict], evidence_sha256: str) -> tuple[dict, list[str]]:
    """(signals.json content, warnings)."""
    reader = raw.RawReader(workspace)
    usernames = {entry["type"]: entry.get("username") for entry in cfg.get("sources", [])}
    mentioned = mentions(evidence)
    review_order = {item["id"]: n for n, item in enumerate(evidence) if is_perf_review(item)}
    clusters = [cluster_signals(f"c{n}", items, reader, usernames, mentioned, review_order)
                for n, items in enumerate(build(evidence), start=1)]
    cluster_of = {ev: c["id"] for c in clusters for ev in c["evidence_ids"]}
    reviews = []
    for item in evidence:
        if is_perf_review(item):
            reached = []
            for target in item.get("links", []):
                cluster = cluster_of.get(target)
                if cluster and cluster not in reached:
                    reached.append(cluster)
            reviews.append({"id": item["id"], "title": item["title"], "date": day(item["created_at"]),
                            "raw_ref": item.get("raw_ref"),
                            "clusters": sorted(reached, key=lambda c: int(c[1:]))})
    return {"evidence_sha256": evidence_sha256, "clusters": clusters, "reviews": reviews}, reader.warnings
