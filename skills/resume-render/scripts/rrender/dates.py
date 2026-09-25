"""Resume date formatting: 2023-01 and 2023-01-15 read "Jan 2023", 2019 reads "2019"."""
from __future__ import annotations

import re

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
PRESENT = "Present"
_DATE = re.compile(r"(\d{4})(?:-(\d{2})(?:-\d{2})?)?")


def format_date(value: str) -> str:
    """Format an ISO date (YYYY, YYYY-MM or YYYY-MM-DD). Anything else is returned unchanged."""
    match = _DATE.fullmatch(value)
    if not match:
        return value
    year, month = match.group(1), match.group(2)
    if month is None:
        return year
    number = int(month)
    return f"{MONTHS[number - 1]} {year}" if 1 <= number <= 12 else value


def date_range(start: str | None, end: str | None, ongoing: bool = True) -> tuple[str, ...]:
    """The parts of a date range, for a writer to join with its own dash.

    A start with no end reads as ongoing ("Present") when ongoing is True.
    """
    if start and end:
        first, last = format_date(start), format_date(end)
        return (first,) if first == last else (first, last)
    if start:
        return (format_date(start), PRESENT) if ongoing else (format_date(start),)
    if end:
        return (format_date(end),)
    return ()
