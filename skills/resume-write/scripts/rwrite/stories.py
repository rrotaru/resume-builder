"""The model's STAR stories (06-bullets.tmp/stories.md): one per top project, in a fixed shape.

stories.md starts with '# Stories'. Each project with metric_prompt gets one
story, in rank order, headed '## <internal_name>', whose lines (blank ones
aside) are '- **Situation:** …', '- **Task:** …', '- **Action:** …' and
'- **Result:** …', in that order. Stories cite no sources line by line, so
every number in one must appear in its project's evidence, the performance
reviews or the project's metrics.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rcore import numbers

from .common import STORIES, plural, shorten
from .material import Material

TITLE = "# Stories"
PARTS = ("Situation", "Task", "Action", "Result")
FIX = (f"fix: edit {STORIES}: '# Stories', then for each project write.py marked 'story', in its order, "
       "'## <its name>' and one line each for Situation, Task, Action and Result, with only numbers its "
       "evidence, the performance reviews or its metrics state (see SKILL.md)")
_ITEM = re.compile(r"^- \*\*(" + "|".join(PARTS) + r"):\*\* ?(.*)$")


@dataclass
class Story:
    line: int
    heading: str
    items: list[tuple[int, str, str]] = field(default_factory=list)  # (line, part, text)


def told(projects: list[dict]) -> list[dict]:
    """The projects that get a story: those with metric_prompt, in rank order."""
    return [p for p in projects if p["metric_prompt"]]


def parse(text: str) -> tuple[list[Story], list[str]]:
    """The stories in text, and the lines that fit no story."""
    lines = text.splitlines()
    problems = []
    if not lines or lines[0] != TITLE:
        problems.append(f"{STORIES}:1: the first line must be '{TITLE}'")
    stories: list[Story] = []
    for number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        if line.startswith("## "):
            stories.append(Story(number, line[3:]))
            continue
        match = _ITEM.match(line)
        if not stories:
            problems.append(f"{STORIES}:{number}: text before the first story; stories start with '## <name>'")
        elif match is None:
            problems.append(f"{STORIES}:{number}: expected a '## ' heading or one of the lines '- **Situation:** …', "
                            "'- **Task:** …', '- **Action:** …' and '- **Result:** …'")
        else:
            stories[-1].items.append((number, match.group(1), match.group(2).strip()))
    return stories, problems


def check(text, material: Material) -> list[str]:
    """Problems with the model's stories, one line each."""
    stories, problems = parse(text)
    expected = told(material.projects)
    for story, project in zip(stories, expected):
        named = story.heading == project["internal_name"]
        if not named:
            problems.append(f"{STORIES}:{story.line}: expected '## {project['internal_name']}' "
                            f"(rank {project['rank']}, {project['id']})")
        parts = [part for _, part, _ in story.items]
        if parts != list(PARTS):
            found = ", ".join(parts) or "none"
            problems.append(f"{STORIES}:{story.line}: a story has the lines Situation, Task, Action and Result, "
                            f"once each and in that order (found {found})")
        sources = material.story_texts(project)
        for number, part, body in story.items:
            if not body:
                problems.append(f"{STORIES}:{number}: the {part} line is empty")
            if named:  # under another project's heading, its numbers are checked once the heading is right
                problems += [f"{STORIES}:{number}: the number '{n}' is in none of {project['id']}'s evidence, the "
                             "performance reviews or its metrics" for n in numbers.unsupported(body, sources)]
    for story in stories[len(expected):]:
        which = f"the {plural(len(expected), 'project')} write.py marked 'story'" if expected else \
            "projects with a metric prompt, and there are none"
        problems.append(f"{STORIES}:{story.line}: '## {story.heading}' is a story too many: stories are only for "
                        f"{which}")
    problems.sort(key=_line)
    for project in expected[len(stories):]:
        problems.append(f"{STORIES}: no story for {project['id']} {shorten(project['internal_name'])!r} "
                        f"(rank {project['rank']})")
    return problems


def _line(problem: str) -> int:
    """The line a problem names (stories.md:<line>: ...), to list problems in file order."""
    return int(problem[len(STORIES) + 1:].split(":", 1)[0])
