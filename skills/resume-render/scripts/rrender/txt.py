"""Plain-text writer. UTF-8, LF line endings, one line per bullet, no wrapping.

The writer's own punctuation is ASCII (" - " in date ranges, " | " between
contact items and details, "- " before bullets); content keeps its characters.
"""
from __future__ import annotations

from .model import Document


def render(doc: Document) -> str:
    lines = [doc.name]
    if doc.label:
        lines.append(doc.label)
    if doc.contacts:
        lines.append(" | ".join(c.text for c in doc.contacts))
    for section in doc.sections:
        lines += ["", section.heading.upper(), ""]
        if section.paragraph:
            lines.append(section.paragraph)
        lines += [f"{line.label}: {line.text}" if line.label else line.text for line in section.lines]
        for i, item in enumerate(section.items):
            if i:
                lines.append("")
            if item.title:
                lines.append(item.title)
            meta = [" - ".join(item.dates)] if item.dates else []
            meta += [d.text for d in item.details]
            if meta:
                lines.append(" | ".join(meta))
            lines += [f"- {bullet}" for bullet in item.bullets]
    return "\n".join(lines) + "\n"
