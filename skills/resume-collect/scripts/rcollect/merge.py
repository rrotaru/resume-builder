"""Duplicates, evidence IDs and links, over the drafts of every source at once."""
from __future__ import annotations

from rcore import ids

from .common import ROLE_RANK, Draft


def key_of(source: str, native_key: str) -> tuple[str, str]:
    """The canonical (source, native_key): GitHub and GitLab paths in lower case, Jira keys in upper case.

    Evidence stores this form and hashes it into the ID, so the ID does not
    depend on how a source happened to spell the repository or the key.
    """
    if source in ("github", "gitlab"):
        return source, native_key.casefold()
    if source == "jira":
        return source, native_key.upper()
    return source, native_key


def _merge_copies(drafts: list[Draft]) -> tuple[list[Draft], int]:
    """One draft per (source, native_key): the strongest role, then stats, then the earliest."""
    groups: dict[tuple[str, str], list[tuple[int, Draft]]] = {}
    for position, draft in enumerate(drafts):
        groups.setdefault(key_of(draft.source, draft.native_key), []).append((position, draft))
    kept, duplicates = [], 0
    for group in groups.values():
        _, primary = min(group, key=lambda pd: (ROLE_RANK[pd[1].engineer_role], pd[1].stats is None, pd[0]))
        for _, other in group:
            if other is primary:
                continue
            duplicates += 1
            primary.labels += [label for label in other.labels if label not in primary.labels]
            primary.refs |= other.refs
            primary.merge_shas |= other.merge_shas
        kept.append(primary)
    return kept, duplicates


def _drop_merged_commits(drafts: list[Draft]) -> tuple[list[Draft], int]:
    """Drop commits that are an authored pull request's merge or squash commit; move their references."""
    by_sha: dict[str, Draft] = {}
    by_key: dict[tuple[str, str], Draft] = {}
    for draft in drafts:
        if draft.kind in ("pr", "mr") and draft.engineer_role == "author":
            for sha in draft.merge_shas:
                by_sha[sha] = draft
            by_key[key_of(draft.source, draft.native_key)] = draft
    kept, dropped = [], 0
    for draft in drafts:
        if draft.kind == "commit":
            target = by_sha.get(draft.sha or "")
            if target is None and draft.squash_of:
                target = by_key.get(key_of(*draft.squash_of))
            if target is not None:
                target.refs |= draft.refs
                dropped += 1
                continue
        kept.append(draft)
    return kept, dropped


def build(drafts: list[Draft]) -> tuple[list[dict], int]:
    """Evidence records sorted by created_at then id, and the number of duplicates removed."""
    merged, copies = _merge_copies(drafts)
    kept, commits = _drop_merged_commits(merged)
    for draft in kept:
        draft.native_key = key_of(draft.source, draft.native_key)[1]
    id_of = ids.assign_evidence_ids((d.source, d.native_key) for d in kept)
    records = []
    for draft in kept:
        own = id_of[(draft.source, draft.native_key)]
        links = {id_of[key_of(*ref)] for ref in draft.refs if key_of(*ref) in id_of} - {own}
        records.append(draft.record(own, sorted(links)))
    records.sort(key=lambda r: (r["created_at"], r["id"]))
    return records, copies + commits
