"""Replacing denied terms in text, and which fields of a profile are prose.

Each denied match (rcore.terms.find: the terms check's rules, allowed terms
exempting, overlaps resolved leftmost-longest) is replaced by its term's
replacement as decisions/terms.json writes it. At the start of a sentence the
replacement's first letter is capitalized; nothing is ever lowercased.
"""
from __future__ import annotations

import copy
import re
from collections import Counter
from dataclasses import dataclass, field

from rcore import terms
from rcore.profile import PROSE_FIELDS

# Ignored around a sentence start: spaces, Markdown markers, quotes and opening brackets.
_MARKERS = " \t*_#>+•-\"'“‘([`"
_BREAKS = "\n\r\x0b\x0c\x1c\x1d\x1e\x85  "
_LINE_BREAK = re.compile("\r\n|[" + _BREAKS + "]")


def sentence_start(before: str) -> bool:
    """True when the text that follows `before` starts a sentence.

    - The line so far, ignoring spaces and Markdown markers, is a list number
      ("1."); or it is empty and the line has a marker ("## ", "- "), is the
      first line, or follows a blank line.
    - Or `before`, ignoring spaces, line breaks and markers at its end, is
      empty or ends with ".", "!", "?" or ":".

    So a heading or list item starts a sentence, and so does a word after
    "**Task:** ", but a line that continues a wrapped sentence does not.
    """
    lines = _LINE_BREAK.split(before)
    line = lines[-1]
    rest = line.strip(_MARKERS)
    if rest:
        if re.fullmatch(r"\d+[.)]", rest):
            return True
    elif len(lines) == 1 or line.strip(" \t") or not lines[-2].strip():
        return True
    tail = before.rstrip(_MARKERS + _BREAKS)
    return not tail or tail.endswith((".", "!", "?", ":"))


def _capitalized(text: str) -> str:
    return text[0].upper() + text[1:] if text and text[0].islower() else text


@dataclass
class Replaced:
    text: str
    counts: Counter = field(default_factory=Counter)  # term -> matches replaced
    starts: list[int] = field(default_factory=list)  # where each replacement starts in text


def replace(text: str, patterns: terms.Patterns, replacements: dict[str, str]) -> Replaced:
    """text with every denied match replaced; replacements maps each denied term to its replacement."""
    parts: list[str] = []
    result = Replaced("")
    at = 0
    for start, end, term in terms.find(text, patterns):
        parts.append(text[at:start])
        before = "".join(parts)
        value = replacements[term]
        result.starts.append(len(before))
        parts.append(_capitalized(value) if sentence_start(before) else value)
        result.counts[term] += 1
        at = end
    parts.append(text[at:])
    result.text = "".join(parts)
    return result


def prose(profile: dict):
    """Yield (pointer, container, key) for each prose string of a profile.

    Prose is basics.summary, and summary, description, highlights (each item)
    and reference in any entry of a top-level section. Everything else is a fact.
    """
    basics = profile.get("basics")
    if isinstance(basics, dict) and isinstance(basics.get("summary"), str):
        yield "/basics/summary", basics, "summary"
    for section, entries in profile.items():
        if section == "basics" or not isinstance(entries, list):
            continue
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            for name in entry:
                if name not in PROSE_FIELDS:
                    continue
                value = entry[name]
                if isinstance(value, str):
                    yield f"/{section}/{i}/{name}", entry, name
                elif isinstance(value, list):
                    for j, item in enumerate(value):
                        if isinstance(item, str):
                            yield f"/{section}/{i}/{name}/{j}", value, j


def sanitize_profile(profile: dict, patterns: terms.Patterns,
                     replacements: dict[str, str]) -> tuple[dict, dict[str, str], Counter]:
    """(sanitized copy, {pointer: new text} for each prose field changed, matches per term).

    Only prose changes; every other value, x-lines and the key order are kept.
    """
    result = copy.deepcopy(profile)
    changed: dict[str, str] = {}
    counts: Counter = Counter()
    for pointer, container, key in list(prose(result)):
        done = replace(container[key], patterns, replacements)
        if done.counts:
            container[key] = done.text
            changed[pointer] = done.text
            counts.update(done.counts)
    return result, changed, counts
