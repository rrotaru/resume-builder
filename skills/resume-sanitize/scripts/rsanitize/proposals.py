"""Checks of the model's proposed terms: 05-terms.tmp/candidates.json and 07-sanitized.tmp/new-terms.json.

The model writes term, kind and proposed_replacement; the script fills in
found_in (the places the term occurs, by the terms check's rules) and keeps the
model's order. A proposal fails when the file does not match
term-candidates.schema.json (found_in optional), when its term occurs in none
of the texts, when two proposals are the same term (rcore.terms.key), or when
its replacement is empty or contains a proposed or denied term. New terms
must also be undecided in decisions/terms.json, and must include every
undecided candidate from 05-terms/candidates.json that occurs in the text.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from rcore import schema, terms

from .common import CANDIDATES, TERMS, allowed_terms, decided_keys, plural, shorten
from .texts import Text, places

FIX_CANDIDATES = ("fix: list each term once, spelled as the scanned text spells it, with a non-empty "
                  "generalization that contains no candidate or denied term")
FIX_NEW_TERMS = ("fix: list each undecided term once, spelled as the sanitized text spells it, with a non-empty "
                 "generalization that contains no listed or denied term; leave out terms decisions/terms.json "
                 "decides")


@dataclass
class Checked:
    records: list[dict] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _draft_schema() -> dict:
    spec = copy.deepcopy(schema.load_schema("term-candidates"))
    spec["items"]["required"] = [r for r in spec["items"]["required"] if r != "found_in"]
    return spec


def check(draft, label: str, texts: list[Text], entries: list[dict], new_terms: bool = False,
          candidates: list[dict] | None = None) -> Checked:
    """Check a draft list of proposals against texts and decisions/terms.json entries.

    new_terms: the draft is 07-sanitized.tmp/new-terms.json, so a decided term is a
    problem (not a note), the texts are the sanitized output, and every
    undecided term of candidates (05-terms/candidates.json) that occurs in the
    texts must be listed.
    """
    out = Checked()
    errors = schema.validate(draft, _draft_schema())
    if errors:
        out.problems = [f"{label}: {e}" for e in errors]
        return out
    allowed, decided = allowed_terms(entries), decided_keys(entries)
    denied = [e["term"] for e in entries if e["replacement"] is not None]
    keys: dict[str, int] = {}
    for i, item in enumerate(draft):
        key = terms.key(item["term"])
        where = f"{label}: /{i}"
        if not key:
            out.problems.append(f"{where}/term: {item['term']!r} has no words")
            continue
        if key in keys:
            j = keys[key]
            out.problems.append(f"{where}/term: {item['term']!r} is the same term as /{j} "
                                f"({draft[j]['term']!r})")
            continue
        keys[key] = i
        if key in decided:
            if new_terms:
                out.problems.append(f"{where}/term: {item['term']!r} is decided in {TERMS}; leave it out")
            else:
                out.notes.append(f"/{i} {item['term']!r} is decided in {TERMS} already; "
                                 "the wizard will not ask about it")
        found = places(item["term"], texts, allowed)
        if not found:
            what = "the sanitized text" if new_terms else "the scanned texts"
            out.problems.append(f"{where}/term: {item['term']!r} appears in none of {what}")
        out.records.append({"term": item["term"], "kind": item["kind"],
                            "proposed_replacement": item["proposed_replacement"], "found_in": found})
    out.problems += _replacement_problems(draft, label, denied, allowed)
    if new_terms:
        out.problems += _unlisted_candidates(draft, candidates or [], texts, entries)
    return out


def _replacement_problems(draft: list[dict], label: str, denied: list[str], allowed: list[str]) -> list[str]:
    proposed = [item["term"] for item in draft]
    patterns = terms.compile_terms(proposed + [d for d in denied if d not in proposed], allowed)
    problems = []
    for i, item in enumerate(draft):
        replacement = item["proposed_replacement"]
        where = f"{label}: /{i}/proposed_replacement"
        if not replacement.strip():
            problems.append(f"{where}: is empty; propose a generalization")
            continue
        for term in terms.terms_in(replacement, patterns):
            source = f"/{proposed.index(term)}" if term in proposed else TERMS
            problems.append(f"{where}: {shorten(replacement)!r} contains the term {term!r} ({source})")
    return problems


def _unlisted_candidates(draft: list[dict], candidates: list[dict], texts: list[Text],
                         entries: list[dict]) -> list[str]:
    listed = {terms.key(item["term"]) for item in draft} | decided_keys(entries)
    problems = []
    for candidate, found in must_list(candidates, texts, entries):
        if terms.key(candidate["term"]) not in listed:
            problems.append(f"{candidate['term']!r} from {CANDIDATES} is not decided and appears in "
                            f"{_places(found)}; list it")
    return problems


def must_list(candidates: list[dict], texts: list[Text], entries: list[dict]) -> list[tuple[dict, list[str]]]:
    """(candidate, places) for each undecided candidate that occurs in texts."""
    decided, allowed = decided_keys(entries), allowed_terms(entries)
    result = []
    for candidate in candidates:
        if terms.key(candidate["term"]) in decided:
            continue
        found = places(candidate["term"], texts, allowed)
        if found:
            result.append((candidate, found))
    return result


def _places(found: list[str], limit: int = 3) -> str:
    shown = ", ".join(found[:limit])
    return shown + (f" and {len(found) - limit} more" if len(found) > limit else "")


def describe_places(found: list[str]) -> str:
    """"3 places: pj_1, ev_2, ev_3" (at most three, then "and N more")."""
    return f"{plural(len(found), 'place')}: {_places(found)}"
