"""Portability rules from the architecture spec, enforced for every skill."""
import re
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parent.parent / "skills"
ALLOWED_ENTRIES = {"SKILL.md", "scripts", "references", "templates", "schemas"}
FORBIDDEN = ["CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR", "$ARGUMENTS"]
SKILL_DIRS = sorted(p for p in SKILLS.iterdir() if p.is_dir())


def front_matter(text: str) -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "SKILL.md must start with a --- front matter block"
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def test_there_are_skills():
    assert SKILL_DIRS


@pytest.mark.parametrize("skill", SKILL_DIRS, ids=lambda p: p.name)
def test_front_matter(skill):
    fields = front_matter((skill / "SKILL.md").read_text(encoding="utf-8"))
    assert fields.get("name") == skill.name
    assert re.fullmatch(r"[a-z0-9-]{1,64}", fields["name"])
    assert 0 < len(fields.get("description", "")) <= 1024


@pytest.mark.parametrize("skill", SKILL_DIRS, ids=lambda p: p.name)
def test_only_portable_entries(skill):
    extra = {p.name for p in skill.iterdir()} - ALLOWED_ENTRIES
    assert not extra, f"unexpected entries in {skill.name}: {sorted(extra)}"


@pytest.mark.parametrize("skill", SKILL_DIRS, ids=lambda p: p.name)
def test_no_harness_specific_constructs(skill):
    for path in [skill / "SKILL.md", *skill.rglob("*.py")]:
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            assert token not in text, f"{path.relative_to(SKILLS)} uses {token}"


@pytest.mark.parametrize("skill", SKILL_DIRS, ids=lambda p: p.name)
def test_cross_skill_references_only_to_resume_core(skill):
    for path in [skill / "SKILL.md", *skill.glob("scripts/**/*.py")]:
        text = path.read_text(encoding="utf-8")
        for name in re.findall(r"\.\./([A-Za-z0-9_-]+)/", text):
            assert name == "resume-core", f"{path.relative_to(SKILLS)} references ../{name}/"


@pytest.mark.parametrize("skill", SKILL_DIRS, ids=lambda p: p.name)
def test_entry_scripts_declare_inline_metadata(skill):
    for path in skill.glob("scripts/*.py"):
        text = path.read_text(encoding="utf-8")
        if '__name__ == "__main__"' in text:
            assert text.startswith("# /// script\n"), f"{path.name} needs a PEP 723 header"
            assert 'requires-python = ">=3.10"' in text
