"""Likely sensitive terms in a text: hints for the model, not decisions.

Kinds, in the order they are shown:
- codename: Project, Operation, Codename, Code name, Program or Initiative
  followed by one or two capitalized words ("Project Falcon");
- url: http(s) URLs (shown without the scheme), www. hosts, and hosts ending in
  .internal, .corp, .local, .lan or .intranet;
- email: email addresses;
- money: a currency sign or code with a number ("$1.2M", "2 million USD");
- name: a run of one to four capitalized words separated by single spaces.
  Words of two or three capital letters (PR, API), a word followed by
  -<digits> (the PAY of PAY-42) and "I" end a run, and leading function words
  (The, For, ...) are dropped. At the start of a sentence the position may be
  what capitalizes the first word, so a run there also counts without it
  ("Fix Falcon cache" gives "Fix Falcon" and "Falcon"), and a single word
  there does not count.

A hit that overlaps an earlier hit of another kind is skipped; the detectors
run in the order url, email, host, money, codename, name, so a name never
repeats part of a URL or a codename.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .replace import sentence_start

KINDS = ("codename", "url", "email", "money", "name")

_URL = re.compile(r"https?://[^\s<>()\[\]{}\"'`]+", re.IGNORECASE)
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_HOST = re.compile(r"(?<![\w.@/-])(?:www\.[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
                   r"|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:internal|corp|local|lan|intranet))(?![\w-])",
                   re.IGNORECASE)
_SCALE = r"(?:[kKmMbB]|mm|bn|million|billion|thousand)"
_CODE = r"(?:USD|EUR|GBP|dollars|euros|pounds)"
_MONEY = re.compile(
    r"[$€£¥]\s?\d[\d,]*(?:\.\d+)?(?:\s?" + _SCALE + r")?(?![\w])"
    r"|(?<![\w.])\d[\d,]*(?:\.\d+)?\s?" + _SCALE + r"?\s?" + _CODE + r"\b"
    r"|\b(?:USD|EUR|GBP)\s?\d[\d,]*(?:\.\d+)?(?:\s?" + _SCALE + r")?(?![\w])")
_CODENAME = re.compile(r"\b(?i:project|operation|codename|code name|program|initiative)"
                       r"\s+[A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*)?")
_WORD = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Za-z0-9]*")
_TRAILING = ".,;:!?)]}'\""
_FUNCTION_WORDS = frozenset(
    "a an and as at by for from if in into of on or our the their this that these those to via "
    "when while with".split())
_MAX_WORDS = 4


@dataclass(frozen=True)
class Hit:
    kind: str
    term: str
    start: int
    end: int


def _breaks_run(text: str, word: re.Match) -> bool:
    value = word.group()
    if value == "I" or (value.isupper() and 2 <= len(value) <= 3):
        return True
    return re.match(r"-\d", text[word.end():]) is not None


def _names(text: str) -> list[Hit]:
    runs: list[list[re.Match]] = []
    for word in _WORD.finditer(text):
        if _breaks_run(text, word):
            runs.append([])
            continue
        if runs and runs[-1] and text[runs[-1][-1].end():word.start()] == " ":
            runs[-1].append(word)
        else:
            runs.append([word])
    hits = []
    for run in runs:
        while run and run[0].group().lower() in _FUNCTION_WORDS:
            run = run[1:]
        if not run or len(run) > _MAX_WORDS:
            continue
        start, end = run[0].start(), run[-1].end()
        if sentence_start(text[:start]):
            if len(run) == 1:
                continue
            hits.append(Hit("name", text[start:end], start, end))
            start = run[1].start()
        hits.append(Hit("name", text[start:end], start, end))
    return hits


def detect(text: str, names: bool = True) -> list[Hit]:
    """Likely terms in text, in order of position; without names, the name detector is skipped."""
    found: list[Hit] = []

    def add(kind: str, start: int, end: int, term: str | None = None) -> None:
        if not any(start < h.end and h.start < end for h in found):
            found.append(Hit(kind, term if term is not None else text[start:end], start, end))

    for match in _URL.finditer(text):
        url = match.group().rstrip(_TRAILING)
        add("url", match.start(), match.start() + len(url), re.sub(r"^https?://", "", url, flags=re.I))
    for pattern, kind in ((_EMAIL, "email"), (_HOST, "url"), (_MONEY, "money"), (_CODENAME, "codename")):
        for match in pattern.finditer(text):
            value = match.group().rstrip(_TRAILING) if kind != "money" else match.group()
            add(kind, match.start(), match.start() + len(value))
    others = list(found)
    for hit in _names(text) if names else ():
        if not any(hit.start < h.end and h.start < hit.end for h in others):
            found.append(hit)
    return sorted(found, key=lambda h: (h.start, h.end))
