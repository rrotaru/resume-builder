"""resume-build's SKILL.md keeps the promises earlier pieces rely on (the roadmap's Must lines)."""
from pathlib import Path

import pytest

SKILL = (Path(__file__).resolve().parents[2] / "skills" / "resume-build" / "SKILL.md").read_text(encoding="utf-8")
BODY = SKILL.split("\n---\n", 1)[1]


def one_line(text: str) -> str:
    return " ".join(text.split())


@pytest.mark.parametrize("skill", ["resume-init", "resume-collect", "resume-import", "resume-analyze",
                                   "resume-sanitize", "resume-wizard", "resume-write", "resume-ats", "resume-render"])
def test_each_step_is_handed_to_its_skill_by_name(skill):
    assert f"**{skill}** skill" in BODY
    assert f"../{skill}/" not in BODY  # portability rule 1: never a path into another skill


@pytest.mark.parametrize("promise", [
    # Every session starts where the run stands.
    "Run `uv run scripts/progress.py --workspace WS`",
    # Collect: a collection in progress is continued, never begun again.
    "never run `stage.py begin 01-raw`, which deletes it",
    # Checkpoint 2: choices only through decide.py.
    "only with resume-analyze's `decide.py`, never by editing `decisions/projects.json` or regrouping `groups.json`",
    "Re-link or discard every orphaned decision before the commit",
    # Checkpoint 3 until nothing is open, again after each round.
    "Run its `questions.py` until it prints `wizard: no open questions`, again after each round of answers",
    "run it before write, sanitize apply or ats begins again",
    # A wizard answer: write recommits unchanged.
    "`write.py --from-current` then `write.py --commit` recommits the bullets unchanged",
    # Checkpoint 4: notices, flags and attestations.
    "Show every `notice:` line",
    "Ask the engineer to confirm that each allowed term is a different word",
    "**Accept:** `uv run scripts/attest.py --workspace WS accept SLUG BULLET`",
    "**Revert:** `ats.py --revise SLUG`, set the text in `08-ats.tmp/jobs/SLUG/resume.json` to its original",
    "**Edit:** `ats.py --revise SLUG`",
    "`uv run scripts/attest.py --workspace WS edit SLUG BULLET`",
    "Only `scripts/attest.py` writes `decisions/attestations.json`",
    "run it again, until it prints `checkpoint 4: no open items`",
    "Never edit a stage folder or `decisions/` by hand",
])
def test_the_skill_keeps_each_promise(promise):
    assert promise in one_line(BODY)
