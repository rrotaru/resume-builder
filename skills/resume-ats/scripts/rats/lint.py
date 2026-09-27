"""Lint rules for a version, the engineer's experience, and the length estimate.

Errors stop the commit; warnings go to report.json. Headings, the date format
on the page and the one-column template are render's: its fixed render model
and template guarantee them, and its tests check them.

Experience is the union of the effective profile's work date ranges, in whole
months counting the first and the last: a year alone runs from January to
December, a job without endDate runs to the current month, and a job without
startDate is not counted. Under 96 months (8 years) the budget is 1 page,
otherwise 2, at LINES_PER_PAGE lines a page.

The estimate counts lines of body text (10.5 pt at 1.3 line height) as render's
classic template lays the resume out, in hundredths of a line so the sum is
exact, rounded up. Measured in Chromium at A4 width, it is 4 to 15% above the
real height, and a resume estimated at 52 lines or fewer prints on one Letter
page (about 51.7 lines).
"""
from __future__ import annotations

import unicodedata

from rcore import facts
from rcore.profile import describe, is_date

from .material import Material

LINES_PER_PAGE = 50
EXPERIENCE_FOR_TWO_PAGES = 96  # months
LONG_BULLET = 200  # characters
# Lines, in hundredths.
NAME, LABEL, CONTACTS, HEADING = 160, 130, 130, 240
LINE, BULLETS_SPACE, BULLET_SPACE, ENTRY_SPACE, SKILL_SPACE = 100, 15, 15, 45, 15
TITLE_WIDTH, BULLET_WIDTH, LINE_WIDTH = 90, 95, 100
SEP = " · "  # render's separator between contact items

BULLET_GLYPHS = "•◦‣⁃∙▪▫■□●○◆◇►▸-–—*+>·"
_BREAKS = "\n\r\t\v\f\x1c\x1d\x1e\x85  "
_EMOJI = ((0x2600, 0x27BF), (0x2B00, 0x2BFF), (0x1F000, 0x1FAFF), (0xFE0F, 0xFE0F))
ENTRY_SECTIONS = ("work", "projects", "education", "certificates", "skills")


# Experience ------------------------------------------------------------------------

def month(value, end: bool = False) -> int | None:
    """A date as a month count (year * 12 + month - 1); a year alone is January, or with end December."""
    if not is_date(value):
        return None
    parts = value.split("-")
    return int(parts[0]) * 12 + (int(parts[1]) if len(parts) > 1 else (12 if end else 1)) - 1


def experience_months(effective: dict, today: tuple[int, int]) -> int:
    now = today[0] * 12 + today[1] - 1
    ranges = []
    work = effective.get("work")
    for job in work if isinstance(work, list) else []:
        if not isinstance(job, dict):
            continue
        start = month(job.get("startDate"))
        end = month(job.get("endDate"), end=True) if job.get("endDate") is not None else now
        if start is None or end is None:
            continue
        end = min(end, now)
        if start <= end:
            ranges.append((start, end))
    total, reached = 0, None
    for start, end in sorted(ranges):
        if reached is not None and start <= reached:
            if end > reached:
                total += end - reached
                reached = end
            continue
        total += end - start + 1
        reached = end
    return total


def budget(months: int) -> tuple[int, int]:
    """(pages, line budget) for this much experience."""
    pages = 1 if months < EXPERIENCE_FOR_TWO_PAGES else 2
    return pages, pages * LINES_PER_PAGE


# The estimate ----------------------------------------------------------------------

def _text(value) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _join(*parts, sep: str = ", ") -> str:
    return sep.join(p for p in (_text(v) for v in parts) if p)


def _wrap(text: str, width: int) -> int:
    return max(1, -(-len(text) // width))


def _contacts(basics: dict) -> list[str]:
    found = [_text(basics.get(k)) for k in ("email", "phone", "url")]
    profiles = basics.get("profiles")
    for item in profiles if isinstance(profiles, list) else []:
        if isinstance(item, dict):
            found.append(_text(item.get("url")) or _join(item.get("network"), item.get("username"), sep=": "))
    location = basics.get("location") if isinstance(basics.get("location"), dict) else {}
    found.append(_join(location.get("city"), location.get("region"), location.get("countryCode")))
    return [f for f in found if f]


def _entry(title: str, meta: bool, bullets: list[str]) -> int:
    lines = (LINE * _wrap(title, TITLE_WIDTH) if title else 0) + (LINE if meta else 0)
    if bullets:
        lines += BULLETS_SPACE + sum(BULLET_SPACE + LINE * _wrap(b, BULLET_WIDTH) for b in bullets)
    return lines + ENTRY_SPACE


def _bullets(entry: dict) -> list[str]:
    return [_text(h.get("text")) for h in entry.get("x-highlights", []) if isinstance(h, dict) and _text(h.get("text"))]


def _dated(entry: dict, *fields) -> bool:
    return any(_text(entry.get(f)) for f in fields)


def estimate(resume: dict) -> int:
    """Estimated lines of the rendered resume, rounded up."""
    basics = resume.get("basics") if isinstance(resume.get("basics"), dict) else {}
    lines = NAME + (LABEL if _text(basics.get("label")) else 0)
    contacts = _contacts(basics)
    if contacts:
        lines += CONTACTS * _wrap(SEP.join(contacts), LINE_WIDTH)
    if _text(basics.get("summary")) and basics.get("x-summary-sources"):
        lines += HEADING + LINE * _wrap(_text(basics["summary"]), LINE_WIDTH)
    sections = {
        "work": lambda e: _entry(_join(e.get("position"), e.get("name")),
                                 _dated(e, "startDate", "endDate", "location"), _bullets(e)),
        "projects": lambda e: _entry(_join(e.get("name"), e.get("position")),
                                     _dated(e, "startDate", "endDate", "url"), _bullets(e)),
        "education": lambda e: _entry(_join(e.get("studyType"), e.get("area"), e.get("institution")),
                                      _dated(e, "startDate", "endDate", "score"), []),
        "certificates": lambda e: _entry(_join(e.get("name"), e.get("issuer")), _dated(e, "date", "url"), []),
    }
    for section, size in sections.items():
        entries = [e for e in resume.get(section, []) if isinstance(e, dict)]
        if entries:
            lines += HEADING + sum(size(e) for e in entries)
    skills = []
    for entry in resume.get("skills", []):
        if isinstance(entry, dict):
            keywords = _join(*(entry.get("keywords") or []))
            name = _text(entry.get("name"))
            line = f"{name}: {keywords}" if name and keywords else name or keywords
            if line:
                skills.append(line)
    if skills:
        lines += HEADING + sum(SKILL_SPACE + LINE * _wrap(s, LINE_WIDTH) for s in skills)
    return -(-lines // 100)


# Lint ------------------------------------------------------------------------------

def _texts(resume: dict):
    """(pointer, text, is a bullet) for the summary and every bullet."""
    basics = resume.get("basics") if isinstance(resume.get("basics"), dict) else {}
    if isinstance(basics.get("summary"), str):
        yield "/basics/summary", basics["summary"], False
    for section in ("work", "projects"):
        for i, entry in enumerate(resume.get(section, [])):
            for j, highlight in enumerate(entry.get("x-highlights", [])):
                yield f"/{section}/{i}/x-highlights/{j}", highlight["text"], True


def _garbled(char: str) -> bool:
    code = ord(char)
    if char in _BREAKS:
        return False  # reported as a line break
    if unicodedata.category(char) in ("Cc", "Co", "Cn", "Cs"):
        return True
    return any(first <= code <= last for first, last in _EMOJI)


def _text_errors(resume: dict) -> list[str]:
    errors = []
    for pointer, text, is_bullet in _texts(resume):
        what = "a bullet" if is_bullet else "the summary"
        if any(c in _BREAKS for c in text):
            errors.append(f"{pointer}: holds a line break or tab; {what} is one line")
        if text != text.strip():
            errors.append(f"{pointer}: begins or ends with a space")
        if is_bullet and text and text[0] in BULLET_GLYPHS:
            errors.append(f"{pointer}: begins with '{text[0]}'; render adds the bullet")
        for char in dict.fromkeys(c for c in text if _garbled(c)):
            errors.append(f"{pointer}: holds {char!r} (U+{ord(char):04X}), which ATS parsers garble")
    return errors


def copies(entry: dict, candidates: list) -> list[int]:
    """The indexes of the profile entries a resume entry copies."""
    return [j for j, c in enumerate(candidates) if facts.matches(entry, c)]


def _duplicate_errors(resume: dict, material: Material) -> list[str]:
    errors = []
    ids: dict[str, str] = {}
    for section in ("work", "projects"):
        for i, entry in enumerate(resume.get(section, [])):
            for j, highlight in enumerate(entry.get("x-highlights", [])):
                pointer = f"/{section}/{i}/x-highlights/{j}"
                bullet_id = highlight["bullet_id"]
                if bullet_id in ids:
                    errors.append(f"{pointer}: {bullet_id} is already at {ids[bullet_id]}; use a bullet once")
                ids.setdefault(bullet_id, pointer)
    for section in ENTRY_SECTIONS:
        claimed: dict[int, int] = {}
        for i, entry in enumerate(resume.get(section, [])):
            found = copies(entry, material.entries(section))
            if len(found) == 1 and found[0] in claimed:
                errors.append(f"/{section}/{i}: copies the profile's /{section}/{found[0]}, as /{section}/"
                              f"{claimed[found[0]]} does; list each entry once")
            elif len(found) == 1:
                claimed[found[0]] = i
    return errors


def _order_key(entry: dict, now: int) -> tuple[int, int] | None:
    start, end = month(entry.get("startDate")), month(entry.get("endDate"), end=True)
    if start is None and end is None:
        return None
    return (end if end is not None else (now if "endDate" not in entry else -1)), (start if start is not None else -1)


def _warnings(resume: dict, material: Material) -> list[str]:
    warnings = []
    basics = resume.get("basics") if isinstance(resume.get("basics"), dict) else {}
    if not _text(basics.get("email")) and not _text(basics.get("phone")):
        warnings.append("/basics: no email and no phone; add one with /resume-builder:wizard so recruiters can "
                        "reach the engineer")
    now = material.month[0] * 12 + material.month[1] - 1
    work = [e for e in resume.get("work", []) if isinstance(e, dict)]
    dated = [(i, key) for i, e in enumerate(work) for key in [_order_key(e, now)] if key is not None]
    for (i, first), (j, second) in zip(dated, dated[1:]):
        if second > first:
            warnings.append(f"/work/{j}: {describe('work', work[j])} is more recent than /work/{i}; list jobs "
                            "most recent first")
    for j, job in enumerate(material.entries("work")):
        if isinstance(job, dict) and not any(facts.matches(e, job) for e in work):
            warnings.append(f"the profile's /work/{j} ({describe('work', job)}) is left out; a gap in the dates can "
                            "read as a gap in employment")
    for i, entry in enumerate(work):
        if not _text(entry.get("startDate")):
            warnings.append(f"/work/{i}: {describe('work', entry)} has no start date; ATS parsers compute experience "
                            "from dates; add it with /resume-builder:wizard")
    for pointer, text, is_bullet in _texts(resume):
        if is_bullet and len(text) > LONG_BULLET:
            warnings.append(f"{pointer}: {len(text)} characters; a bullet over two lines is hard to scan")
    for i, entry in enumerate(resume.get("projects", [])):
        if not entry.get("x-highlights"):
            warnings.append(f"/projects/{i}: {describe('projects', entry)} has no bullets")
    if not any(entry.get("keywords") for entry in resume.get("skills", []) if isinstance(entry, dict)):
        warnings.append("no skill keywords: an ATS matches skills by keyword; add them with /resume-builder:wizard")
    return warnings


def lint(resume: dict, material: Material) -> tuple[list[str], list[str], dict]:
    """(errors, warnings, length) for a schema-valid resume. Lines start with a pointer, not the file."""
    errors = []
    basics = resume.get("basics") if isinstance(resume.get("basics"), dict) else {}
    if not _text(basics.get("name")):
        errors.append("/basics/name: a resume needs a name; add it with /resume-builder:wizard")
    errors += _text_errors(resume)
    errors += _duplicate_errors(resume, material)
    months = experience_months(material.effective, material.month)
    pages, line_budget = budget(months)
    lines = estimate(resume)
    if lines > line_budget:
        errors.append(f"estimated {lines} lines, over the {pages}-page budget of {line_budget} lines ({months} "
                      "months of experience); leave out the weakest bullets or entries")
    length = {"experience_months": months, "pages": pages, "estimated_lines": lines, "line_budget": line_budget}
    return errors, _warnings(resume, material), length
