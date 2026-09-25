"""Stable identifiers and text hashes."""
from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Iterable

SHORT_LENGTH = 8
LONG_LENGTH = 12


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def evidence_id(source: str, native_key: str, length: int = SHORT_LENGTH) -> str:
    """ev_ + first `length` hex chars of sha256("<source>:<native_key>")."""
    return "ev_" + _digest(f"{source}:{native_key}")[:length]


def assign_evidence_ids(keys: Iterable[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """Map each (source, native_key) to its ID, using 12 hex chars where 8 collide."""
    unique = sorted(set(keys))
    short = {key: evidence_id(*key) for key in unique}
    counts = Counter(short.values())
    return {
        key: evidence_id(*key, length=LONG_LENGTH) if counts[short[key]] > 1 else short[key]
        for key in unique
    }


def project_id(evidence_ids: Iterable[str]) -> str:
    """Deterministic ID for a new project: pj_ + 8 hex chars of its sorted evidence IDs."""
    return "pj_" + _digest("\n".join(sorted(set(evidence_ids))))[:SHORT_LENGTH]


def text_sha256(text: str) -> str:
    """Hex sha256 of a bullet's text, used by attestations and flags."""
    return _digest(text)
