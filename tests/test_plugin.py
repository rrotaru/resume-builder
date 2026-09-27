"""The plugin layout: the manifests and the commands, each of which only hands its arguments to its skill."""
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import pytest

REPO = Path(__file__).resolve().parent.parent
PLUGIN = REPO / ".claude-plugin" / "plugin.json"
MARKETPLACE = REPO / ".claude-plugin" / "marketplace.json"
COMMANDS = REPO / "commands"
# The commands in the architecture spec's plugin layout, and the skill each hands its arguments to.
EXPECTED = {"build": "resume-build", "init": "resume-init", "collect": "resume-collect", "import": "resume-import",
            "analyze": "resume-analyze", "wizard": "resume-wizard", "write": "resume-write",
            "sanitize": "resume-sanitize", "ats": "resume-ats", "render": "resume-render"}
KEBAB = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
PLUGIN_FIELDS = {"name", "description", "author", "homepage", "repository", "keywords"}
FRONT_MATTER = {"description", "argument-hint", "disable-model-invocation"}


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def front_matter(text: str) -> tuple[dict[str, str], str]:
    """The front matter of a command file, read as the simple YAML it must be, and the body after it."""
    match = re.match(r"^---\n(.*?)\n---\n\n", text, re.DOTALL)
    assert match, "a command starts with a --- front matter block and a blank line"
    fields = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(": ")
        assert sep and key not in fields, f"one 'key: value' per line: {line!r}"
        if value.startswith("'"):
            assert value.endswith("'") and "'" not in value[1:-1], f"{key}: a single-quoted string"
            value = value[1:-1]
        else:
            # A plain YAML scalar: no ": " or " #" inside, and no leading quote or indicator.
            assert ": " not in value and " #" not in value and value[:1] not in "\"'[{&*!|>%@`", f"{key}: {value!r}"
        fields[key] = value
    return fields, text[match.end():]


# Manifests ---------------------------------------------------------------------------

def test_plugin_manifest():
    manifest = read(PLUGIN)
    assert set(manifest) <= PLUGIN_FIELDS
    assert manifest["name"] == "resume-builder" and KEBAB.fullmatch(manifest["name"])
    assert manifest["description"].strip()
    assert manifest["author"]["name"].strip()
    for field in ("homepage", "repository"):
        url = urlparse(manifest[field])
        assert url.scheme == "https" and url.netloc, field
    assert manifest["keywords"] and all(isinstance(k, str) and k for k in manifest["keywords"])
    # No version: installs from the git-hosted marketplace follow the repository's commits.
    assert "version" not in manifest


def test_plugin_uses_the_default_layout():
    manifest = read(PLUGIN)
    for key in ("commands", "skills", "agents", "hooks", "mcpServers"):
        assert key not in manifest, f"{key}: the plugin uses the default layout"
    assert not (REPO / "agents").exists() and not (REPO / "hooks").exists()
    skills = sorted(p.name for p in (REPO / "skills").iterdir() if (p / "SKILL.md").is_file())
    assert set(EXPECTED.values()) | {"resume-core"} == set(skills)


def test_marketplace_manifest():
    marketplace = read(MARKETPLACE)
    assert set(marketplace) <= {"name", "owner", "description", "plugins"}
    assert KEBAB.fullmatch(marketplace["name"])
    assert marketplace["owner"]["name"].strip() and marketplace["description"].strip()
    [entry] = marketplace["plugins"]
    assert set(entry) <= {"name", "source", "description"}
    assert entry["name"] == read(PLUGIN)["name"]
    assert entry["description"].strip()
    assert "version" not in entry
    # A relative source starts with ./ and resolves from the marketplace root: this repository.
    assert entry["source"].startswith("./") and ".." not in entry["source"]
    assert (REPO / entry["source"]).resolve() == REPO
    assert ((REPO / entry["source"]) / ".claude-plugin" / "plugin.json").is_file()


# Commands ----------------------------------------------------------------------------

def test_there_is_a_command_for_each_step_and_no_other():
    assert sorted(p.name for p in COMMANDS.iterdir()) == sorted(f"{name}.md" for name in EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_command_only_passes_its_arguments_to_its_skill(name):
    fields, body = front_matter((COMMANDS / f"{name}.md").read_text(encoding="utf-8"))
    assert set(fields) == FRONT_MATTER
    assert fields["disable-model-invocation"] == "true"
    assert fields["description"].strip() and len(fields["description"]) <= 200
    assert fields["argument-hint"].startswith("[")
    skill = EXPECTED[name]
    assert body == f"Use the `resume-builder:{skill}` skill with these arguments: $ARGUMENTS\n"
    assert (REPO / "skills" / skill / "SKILL.md").is_file()


def test_the_front_matter_reader_rejects_what_yaml_would():
    for bad in ("---\ndescription: a: b\n---\n\nx\n", "---\nargument-hint: '[x 'y']'\n---\n\nx\n",
                "---\nargument-hint: \"[x]\"\n---\n\nx\n"):
        with pytest.raises(AssertionError):
            front_matter(bad)
