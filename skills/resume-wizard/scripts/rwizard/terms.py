"""Term decisions in decisions/terms.json: recording one, and the checks the whole file must pass.

A decision is {term, replacement, kind}: a replacement denies the term (sanitize
replaces it, render blocks it), null allows it as it is. Recording a term
replaces an earlier decision for the same term (rcore.terms.key) in place. The
resulting file must match terms.schema.json, allow no term that contains a
denied one (rcore.terms.allowed_conflicts), and hold no replacement that
contains a denied term (rcore.terms.replacement_conflicts).
"""
from __future__ import annotations

from rcore import terms as core_terms

from .common import TERMS, WizardError, check_schema

KINDS = ("codename", "customer", "product", "url", "financial", "other")


def record(entries: list[dict], term: str, replacement: str | None, kind: str) -> list[dict]:
    """entries with the decision for term recorded. Raises WizardError when the result would be invalid."""
    term = term.strip()
    if len(term) < 2 or not core_terms.key(term):
        raise WizardError(f"the term {term!r} needs at least two characters and a word")
    if replacement is not None:
        replacement = replacement.strip()
        if not replacement:
            raise WizardError(f"the replacement for {term!r} is empty; give a generalization, or allow the term")
    decision = {"term": term, "replacement": replacement, "kind": kind}
    key = core_terms.key(term)
    updated, placed = [], False
    for entry in entries:
        if core_terms.key(entry["term"]) == key:
            if not placed:
                updated.append(decision)
                placed = True
            continue
        updated.append(entry)
    if not placed:
        updated.append(decision)
    validate(updated)
    return updated


def validate(entries: list[dict]) -> None:
    check_schema(entries, "terms", TERMS)
    denied = [e["term"] for e in entries if e["replacement"] is not None]
    allowed = [e["term"] for e in entries if e["replacement"] is None]
    errors = core_terms.allowed_conflicts(denied, allowed) + core_terms.replacement_conflicts(entries)
    if errors:
        raise WizardError(errors)


def remove(entries, term: str) -> list:
    """entries without the decisions for term. Works on any JSON list, so it can repair an invalid file."""
    if not isinstance(entries, list):
        raise WizardError(f"{TERMS} is not a JSON list; restore it with init_workspace.py")
    key = core_terms.key(term)
    kept = [e for e in entries
            if not (isinstance(e, dict) and isinstance(e.get("term"), str) and core_terms.key(e["term"]) == key)]
    if len(kept) == len(entries):
        raise WizardError(f"{term!r} is not in {TERMS}")
    return kept


def describe(decision: dict) -> str:
    if decision["replacement"] is None:
        return f"{decision['term']!r} allowed as it is ({decision['kind']})"
    return f"{decision['term']!r} denied, replaced by {decision['replacement']!r} ({decision['kind']})"
