"""Render model: the only view of a tailored resume that the writers see.

build() copies named fields from named sections into a Document. Writers read
only the Document, never the resume, so a section or field that is not listed
here never reaches the page, even if validation were bypassed.

Section order is fixed: Summary, Experience, Projects, Skills, Education,
Certifications. Entries keep the order resume-ats gave them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .dates import date_range, format_date

# Every field tailored-resume.schema.json allows, by object: what the render
# model shows and what it leaves out. A test checks these against the schema,
# so a new schema field needs a rendering decision before it ships.
RENDERED = {
    "": {"basics", "work", "projects", "education", "certificates", "skills"},
    "basics": {"name", "label", "email", "phone", "url", "location", "profiles", "summary"},
    "basics.location": {"city", "region", "countryCode"},
    "basics.profiles": {"network", "username", "url"},
    "work": {"position", "name", "location", "startDate", "endDate", "x-highlights"},
    "projects": {"name", "position", "url", "startDate", "endDate", "x-highlights"},
    "x-highlights": {"text"},
    "education": {"studyType", "area", "institution", "startDate", "endDate", "score"},
    "certificates": {"name", "issuer", "date", "url"},
    "skills": {"name", "keywords"},
}
NOT_RENDERED = {
    "": set(),
    "basics": {"x-summary-sources"},
    "basics.location": {"address", "postalCode"},
    "basics.profiles": set(),
    "work": {"url", "highlights"},  # highlights mirrors x-highlights; render reads x-highlights
    "projects": {"location", "highlights"},
    "x-highlights": {"bullet_id", "sources"},
    "education": {"url"},
    "certificates": set(),
    "skills": {"level"},
}

HEADINGS = {
    "summary": "Summary",
    "work": "Experience",
    "projects": "Projects",
    "skills": "Skills",
    "education": "Education",
    "certificates": "Certifications",
}
LINK_SCHEMES = ("http://", "https://", "mailto:")
_SPACE = re.compile(r"[\s\x00-\x1f\x7f-\x9f]+")


@dataclass(frozen=True)
class Link:
    text: str
    href: str | None = None  # set only for http, https and mailto


@dataclass(frozen=True)
class Item:
    title: str
    dates: tuple[str, ...] = ()  # writers join the parts with their own dash
    details: tuple[Link, ...] = ()
    bullets: tuple[str, ...] = ()


@dataclass(frozen=True)
class Line:
    label: str | None
    text: str


@dataclass(frozen=True)
class Section:
    heading: str
    paragraph: str | None = None
    lines: tuple[Line, ...] = ()
    items: tuple[Item, ...] = ()


@dataclass(frozen=True)
class Document:
    name: str
    label: str | None
    contacts: tuple[Link, ...]
    sections: tuple[Section, ...]

    def checked_texts(self) -> list[str]:
        """Texts the output check requires in every output file, in reading order."""
        texts = [self.name]
        for section in self.sections:
            texts.append(section.heading)
            if section.paragraph:
                texts.append(section.paragraph)
            for item in section.items:
                texts += item.bullets
        return texts


def _text(value) -> str | None:
    """A display string: whitespace and control-character runs become one space."""
    if not isinstance(value, str):
        return None
    return _SPACE.sub(" ", value).strip() or None


def _plain(value) -> Link | None:
    text = _text(value)
    return Link(text) if text else None


def _link(value) -> Link | None:
    text = _text(value)
    if text is None:
        return None
    return Link(text, text if text.lower().startswith(LINK_SCHEMES) else None)


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value) -> list:
    return value if isinstance(value, list) else []


def _join(*parts, sep: str = ", ") -> str:
    return sep.join(p for p in (_text(v) for v in parts) if p)


def _bullets(entry: dict) -> tuple[str, ...]:
    texts = (_text(_dict(h).get("text")) for h in _list(entry.get("x-highlights")))
    return tuple(t for t in texts if t)


def _dates(entry: dict, ongoing: bool = True) -> tuple[str, ...]:
    return date_range(_text(entry.get("startDate")), _text(entry.get("endDate")), ongoing)


def _details(*links) -> tuple[Link, ...]:
    return tuple(link for link in links if link is not None)


def _location(location) -> Link | None:
    location = _dict(location)
    return _plain(_join(location.get("city"), location.get("region"), location.get("countryCode")))


def _profile(item: dict) -> Link | None:
    link = _link(item.get("url"))
    if link:
        return link
    return _plain(_join(item.get("network"), item.get("username"), sep=": "))


def _contacts(basics: dict) -> tuple[Link, ...]:
    email = _text(basics.get("email"))
    links = [Link(email, f"mailto:{email}") if email else None,
             _plain(basics.get("phone")),
             _link(basics.get("url"))]
    links += [_profile(_dict(p)) for p in _list(basics.get("profiles"))]
    links.append(_location(basics.get("location")))
    return _details(*links)


def _work(entry: dict) -> Item:
    return Item(_join(entry.get("position"), entry.get("name")), _dates(entry),
                _details(_plain(entry.get("location"))),
                _bullets(entry))


def _project(entry: dict) -> Item:
    return Item(_join(entry.get("name"), entry.get("position")), _dates(entry),
                _details(_link(entry.get("url"))), _bullets(entry))


def _education(entry: dict) -> Item:
    return Item(_join(entry.get("studyType"), entry.get("area"), entry.get("institution")),
                _dates(entry), _details(_plain(entry.get("score"))))


def _certificate(entry: dict) -> Item:
    date = _text(entry.get("date"))
    return Item(_join(entry.get("name"), entry.get("issuer")), (format_date(date),) if date else (),
                _details(_link(entry.get("url"))))


def _skill(entry: dict) -> Line | None:
    name, keywords = _text(entry.get("name")), _join(*_list(entry.get("keywords")))
    if name and keywords:
        return Line(name, keywords)
    if name or keywords:
        return Line(None, name or keywords)
    return None


def build(resume: dict) -> Document:
    """Build the render model. Raises ValueError without a basics.name."""
    basics = _dict(resume.get("basics"))
    name = _text(basics.get("name"))
    if name is None:
        raise ValueError("basics.name is required to render")
    sections = []
    summary = _text(basics.get("summary"))
    if summary and _list(basics.get("x-summary-sources")):
        sections.append(Section(HEADINGS["summary"], paragraph=summary))
    for key, make in (("work", _work), ("projects", _project)):
        items = tuple(make(e) for e in map(_dict, _list(resume.get(key))))
        if items:
            sections.append(Section(HEADINGS[key], items=items))
    lines = tuple(line for line in (_skill(_dict(e)) for e in _list(resume.get("skills"))) if line)
    if lines:
        sections.append(Section(HEADINGS["skills"], lines=lines))
    for key, make in (("education", _education), ("certificates", _certificate)):
        items = tuple(make(e) for e in map(_dict, _list(resume.get(key))))
        if items:
            sections.append(Section(HEADINGS[key], items=items))
    return Document(name, _text(basics.get("label")), _contacts(basics), tuple(sections))
