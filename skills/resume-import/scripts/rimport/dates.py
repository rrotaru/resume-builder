"""Dates a text states, each at the precision written.

stated_dates("Jun 2019 - Present") == {"2019-06", "2019"}. A full date also
yields its month and year, and a month yields its year, so a profile date
passes when it is in the set: it is then stated at that precision or finer.
Month names are English. A two-digit year yields both centuries, so the
result does not depend on today's date. A numeric day/month/year date yields
both readings that are real dates.
"""
from __future__ import annotations

import datetime
import re

from .match import normalize

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH = (r"(?<![^\W\d_])(?P<mon>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?"
          r"|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
_YEAR = r"(?:(?P<year>(?:19|20)\d{2})|'(?P<yy>\d{2}))(?!\d)"
_DAY = r"(?P<day>\d{1,2})(?:st|nd|rd|th)?"

_MONTH_DAY_YEAR = re.compile(_MONTH + r"\.?\s+" + _DAY + r",?\s+" + _YEAR)
_DAY_MONTH_YEAR = re.compile(r"(?<!\d)" + _DAY + r"\s+" + _MONTH + r"\.?,?\s+" + _YEAR)
_MONTH_YEAR = re.compile(_MONTH + r"\.?,?\s*" + _YEAR)
_YEAR_MONTH_DAY = re.compile(r"(?<!\d)(?P<year>(?:19|20)\d{2})[-/.](?P<m>\d{1,2})(?:[-/.](?P<day>\d{1,2}))?(?!\d)")
_NUMERIC_DATE = re.compile(r"(?<![\d/.-])(?P<a>\d{1,2})[-/.](?P<b>\d{1,2})[-/.](?P<year>(?:19|20)\d{2})(?!\d)")
_MONTH_NUMBER_YEAR = re.compile(r"(?<![\d/.-])(?P<m>\d{1,2})[-/.](?P<year>(?:19|20)\d{2})(?!\d)")
_MONTH_SHORT_YEAR = re.compile(r"(?<![\d/.-])(?P<m>\d{2})/(?P<yy>\d{2})(?![\d/])")
_YEAR_ONLY = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
ISO_DATE = re.compile(r"\d{4}(-\d{2}(-\d{2})?)?")


def _years(match: re.Match) -> list[int]:
    year = match.groupdict().get("year")
    if year:
        return [int(year)]
    yy = int(match.group("yy"))
    return [1900 + yy, 2000 + yy]


def _month(name: str) -> int:
    return MONTHS[name[:3]]


def _add(found: set[str], year: int, month: int | None = None, day: int | None = None) -> None:
    """Add a date and its coarser forms, if it is a real date."""
    try:
        datetime.date(year, month or 1, day or 1)
    except ValueError:
        return
    found.add(f"{year:04d}")
    if month is not None:
        found.add(f"{year:04d}-{month:02d}")
        if day is not None:
            found.add(f"{year:04d}-{month:02d}-{day:02d}")


def stated_dates(text: str) -> set[str]:
    """Every date text states, as YYYY, YYYY-MM or YYYY-MM-DD, with the coarser forms of each."""
    text = normalize(text)
    found: set[str] = set()
    for match in _YEAR_ONLY.finditer(text):
        _add(found, int(match.group()))
    for pattern in (_MONTH_DAY_YEAR, _DAY_MONTH_YEAR):
        for match in pattern.finditer(text):
            for year in _years(match):
                _add(found, year, _month(match.group("mon")), int(match.group("day")))
    for match in _MONTH_YEAR.finditer(text):
        for year in _years(match):
            _add(found, year, _month(match.group("mon")))
    for match in _YEAR_MONTH_DAY.finditer(text):
        day = match.group("day")
        _add(found, int(match.group("year")), int(match.group("m")), int(day) if day else None)
    for match in _NUMERIC_DATE.finditer(text):
        year, a, b = int(match.group("year")), int(match.group("a")), int(match.group("b"))
        _add(found, year, a, b)
        _add(found, year, b, a)
    for match in _MONTH_NUMBER_YEAR.finditer(text):
        _add(found, int(match.group("year")), int(match.group("m")))
    for match in _MONTH_SHORT_YEAR.finditer(text):
        for year in _years(match):
            _add(found, year, int(match.group("m")))
    return found


def is_iso_date(value) -> bool:
    """True for a real date written as YYYY, YYYY-MM or YYYY-MM-DD."""
    if not isinstance(value, str) or not ISO_DATE.fullmatch(value):
        return False
    parts = [int(p) for p in value.split("-")]
    try:
        datetime.date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
    except ValueError:
        return False
    return True


def finest(dates: set[str]) -> list[str]:
    """The dates that are not a coarser form of another, sorted (for messages)."""
    return sorted(d for d in dates if not any(o != d and o.startswith(d + "-") for o in dates))
