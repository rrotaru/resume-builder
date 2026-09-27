"""The claim diff: what a bullet or summary says that the texts it rests on do not.

A text is compared with its known texts (material.Material.known for a
bullet, the texts of x-summary-sources for the summary). It is flagged, in
the order the claims appear and each once, for:

- a keyword of the version's keywords.json found in it and not in the known texts;
- a technical term not in them: a word with a capital letter after its first
  character (PostgreSQL, gRPC, SLO); one mixing letters and digits (EC2, k8s,
  p99); one holding "+", "#", "_" or an inner "." (C++, Node.js); or a
  capitalized word that does not start the text or a sentence (Kafka). A word
  starting with a digit is a number (40ms, 2M), and hyphens split words;
- a number written with digits that no known text states (rcore.numbers);
- a scope word (SCOPE) that no word of its group in the known texts, and not
  the bullet's project's role or scope, supports.

A term inside a flagged keyword, and a number inside a flagged term, is not
reported again. A text equal to its original has nothing to flag, since the
original is a known text. Job versions record the result in flags.json; the
general resume may have none.
"""
from __future__ import annotations

import re
from decimal import Decimal

from rcore import ids, numbers

from . import match
from .material import Material

# (group, words, whether a project supports it)
_SCOPE_RANK = {"team": 0, "cross-team": 1, "org": 2, "company": 3}
SCOPE = (
    ("leadership", ("led", "lead", "leading", "spearheaded", "headed", "directed"),
     lambda p: p.get("role") == "lead"),
    ("cross-team", ("cross-team", "cross-functional", "multi-team"),
     lambda p: _SCOPE_RANK.get(p.get("scope"), 0) >= 1),
    ("organization", ("org-wide", "organization-wide", "organisation-wide", "department-wide", "division-wide"),
     lambda p: _SCOPE_RANK.get(p.get("scope"), 0) >= 2),
    ("company", ("company-wide", "companywide", "enterprise-wide", "global", "globally", "worldwide"),
     lambda p: _SCOPE_RANK.get(p.get("scope"), 0) >= 3),
)
_WORD = re.compile(r"[^\W_][\w+#]*(?:\.[\w+#]+)*")  # starts with a letter or digit
_DOTTED = re.compile(r"^(?:[^\W\d_]\.)+[^\W\d_]$")  # e.g, i.e: abbreviations, not names
_SENTENCE_END = ".!?"


def _sentence_start(text: str, start: int) -> bool:
    before = text[:start].rstrip()
    return not before or before[-1] in _SENTENCE_END


def technical(word: str, sentence_start: bool) -> bool:
    """Whether a word is a technical term the claim diff checks."""
    if word[0].isdigit():
        return False
    if any(c.isupper() for c in word[1:]):
        return True
    if any(c.isdigit() for c in word) and any(c.isalpha() for c in word):
        return True
    if any(c in "+#_" for c in word) or ("." in word and not _DOTTED.match(word)):
        return True
    return word[0].isupper() and not sentence_start


def _inside(start: int, end: int, spans) -> bool:
    return any(a <= start and end <= b for a, b in spans)


def diff(text: str, known: list[str], keywords: list[str] = (), project: dict | None = None) -> list[str]:
    """The reasons text is flagged, in the order its claims appear; [] when every claim is known."""
    norm = match.normalize(text)
    known_text = "\n".join(match.normalize(k) for k in known)
    found: list[tuple[int, str]] = []
    flagged: list[tuple[int, int]] = []
    for keyword in keywords:
        where = match.spans(norm, keyword)
        if where and not match.mentions(known_text, keyword):
            found.append((where[0][0], f"introduces '{keyword}', which no cited source mentions"))
            flagged += where
    seen: set[str] = set()
    terms: list[tuple[int, int]] = []
    for m in _WORD.finditer(norm):
        word = m.group()
        if _inside(m.start(), m.end(), flagged) or not technical(word, _sentence_start(norm, m.start())):
            continue
        if match.mentions(known_text, word):
            continue
        terms.append(m.span())
        if match.key(word) not in seen:
            seen.add(match.key(word))
            found.append((m.start(), f"introduces '{word}', which no cited source mentions"))
    flagged += terms
    known_values: set[Decimal] = set()
    for k in known:
        known_values |= numbers.values(match.normalize(k))
    written: set[str] = set()
    for start, end, as_written, value in numbers.spans(norm):
        if value in known_values or _inside(start, end, flagged) or as_written in written:
            continue
        written.add(as_written)
        found.append((start, f"states the number '{as_written}', which no cited source states"))
    for _, group, supports in SCOPE:
        if (project is not None and supports(project)) or any(match.mentions(known_text, w) for w in group):
            continue
        for word in group:
            for start, end in match.spans(norm, word):
                if not _inside(start, end, flagged):
                    found.append((start, _scope_reason(norm[start:end], project)))
    found.sort(key=lambda f: f[0])
    reasons: list[str] = []
    for _, reason in found:
        if reason not in reasons:
            reasons.append(reason)
    return reasons


def _scope_reason(word: str, project: dict | None) -> str:
    if project is None:
        return f"claims '{word}', which no cited source supports"
    return f"claims '{word}', which neither its sources nor its project's role and scope support"


def summary_known(resume: dict, material: Material) -> list[str]:
    basics = resume.get("basics") if isinstance(resume.get("basics"), dict) else {}
    return material.source_texts(basics.get("x-summary-sources") or [])


def examined(resume: dict, material: Material, keywords: list[str]):
    """Yield (pointer, bullet ID or 'summary', text, reasons) for the summary and every x-highlights item."""
    basics = resume.get("basics") if isinstance(resume.get("basics"), dict) else {}
    if isinstance(basics.get("summary"), str):
        summary = basics["summary"]
        yield "/basics/summary", "summary", summary, diff(summary, summary_known(resume, material), keywords)
    for section in ("work", "projects"):
        for i, entry in enumerate(resume.get(section, [])):
            for j, highlight in enumerate(entry.get("x-highlights", [])):
                text = highlight["text"]
                reasons = diff(text, material.known(highlight, entry), keywords, material.project_of(highlight))
                yield f"/{section}/{i}/x-highlights/{j}", highlight["bullet_id"], text, reasons


def flags(resume: dict, material: Material, keywords: list[str]) -> dict:
    """flags.json for a job version: the hash of every examined text, and the flagged ones with their reasons."""
    checked, flagged = {}, []
    for _, bullet_id, text, reasons in examined(resume, material, keywords):
        digest = ids.text_sha256(text)
        checked[bullet_id] = digest
        if reasons:
            flagged.append({"bullet_id": bullet_id, "text": text, "text_sha256": digest, "reasons": reasons})
    return {"checked": checked, "flags": flagged}
