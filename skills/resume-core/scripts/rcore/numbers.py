"""Numbers written with digits in a text, and whether a text states a value.

resume-wizard checks that a metric's statement states the metric's value.
resume-write checks that a bullet states the value of each metric it cites,
and that every number in a bullet or a story appears in its sources. Both read
numbers the same way: a run of digits with optional thousands separators and
decimals, so "p99" holds 99, "40%" 40, "1,200" 1200 and "2.5x" 2.5. A sign is
not read, so a statement says "fell 3" for the value -3. Numbers written as
words ("two") are not read.

Values are compared exactly, as decimals: 2.5 equals 2.50, but
9007199254740993 never equals 9007199254740992, as it would as floats.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def spans(text: str) -> list[tuple[int, int, str, Decimal]]:
    """Each number in text, in order, as (start, end, how it is written, its exact value)."""
    found = []
    for match in _NUMBER.finditer(text):
        written = match.group().rstrip(",")
        found.append((match.start(), match.start() + len(written), written, Decimal(written.replace(",", ""))))
    return found


def numbers(text: str) -> list[tuple[str, Decimal]]:
    """Each number in text, in order, as (how it is written, its exact value)."""
    return [(written, value) for _, _, written, value in spans(text)]


def values(text: str) -> set[Decimal]:
    """The exact values of the numbers in text."""
    return {value for _, value in numbers(text)}


def exact(value) -> Decimal:
    """A JSON number as an exact decimal: a float as Python writes it back (2.5, not 2.5000000000000000001)."""
    return Decimal(repr(value)) if isinstance(value, float) else Decimal(value)


def digits(value) -> str:
    """A JSON number written with digits only, never an exponent, so numbers() reads the same value back."""
    return format(exact(value), "f")


def states_value(text: str, value) -> bool:
    """True when some number in text equals value, ignoring its sign."""
    return abs(exact(value)) in values(text)


def unsupported(text: str, sources: Iterable[str]) -> list[str]:
    """The numbers in text that no source text holds, as written, each once, in order."""
    known: set[Decimal] = set()
    for source in sources:
        known |= values(source)
    missing: list[str] = []
    for written, value in numbers(text):
        if value not in known and written not in missing:
            missing.append(written)
    return missing
