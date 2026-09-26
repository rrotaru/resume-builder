"""Numbers written with digits in a text, and whether a text states a value.

resume-wizard checks that a metric's statement states the metric's value.
resume-write checks that a bullet states the value of each metric it cites,
and that every number in a bullet or a story appears in its sources. Both read
numbers the same way: a run of digits with optional thousands separators and
decimals, so "p99" holds 99, "40%" 40, "1,200" 1200 and "2.5x" 2.5. A sign is
not read, so a statement says "fell 3" for the value -3. Numbers written as
words ("two") are not read.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers(text: str) -> list[tuple[str, float]]:
    """Each number in text, in order, as (how it is written, its value)."""
    found = []
    for match in _NUMBER.finditer(text):
        written = match.group().rstrip(",")
        found.append((written, float(written.replace(",", ""))))
    return found


def values(text: str) -> set[float]:
    """The values of the numbers in text."""
    return {value for _, value in numbers(text)}


def states_value(text: str, value) -> bool:
    """True when some number in text equals value, ignoring its sign."""
    return abs(float(value)) in values(text)


def unsupported(text: str, sources: Iterable[str]) -> list[str]:
    """The numbers in text that no source text holds, as written, each once, in order."""
    known: set[float] = set()
    for source in sources:
        known |= values(source)
    missing: list[str] = []
    for written, value in numbers(text):
        if value not in known and written not in missing:
            missing.append(written)
    return missing
