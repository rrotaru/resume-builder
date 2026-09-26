"""rwrite.stories: the shape of stories.md, which projects get a story, and its numbers."""
from rwrite import common, material, stories
from write_samples import PA, PB, PROJECTS, STORIES, make_workspace, project

S = "06-bullets.tmp/stories.md"
FALCON = "## Checkout latency\n\n"
STAR = ("- **Situation:** Checkout missed its p99 latency target.\n- **Task:** Jordan led the fix.\n"
        "- **Action:** Built an idempotency cache in 3 regions.\n- **Result:** p99 checkout latency fell 40%.\n")


def check(tmp_path, text, **workspace):
    ws = make_workspace(tmp_path, **workspace)
    return stories.check(text, material.build(ws, common.load_inputs(ws)))


def test_the_sample_stories_pass(tmp_path):
    assert STORIES == "# Stories\n\n" + FALCON + STAR
    assert check(tmp_path, STORIES) == []


def test_only_metric_prompt_projects_get_a_story_in_rank_order(tmp_path):
    projects = [project(PB, [3], "Ledger export retries", 2, "2025-06", "2025-06", True), PROJECTS[0]]
    second = "## Ledger export retries\n\n" + STAR.replace(" p99", "").replace("p99 ", "").replace(
        " in 3 regions", "").replace(" 40%", " by half")
    assert check(tmp_path, "# Stories\n\n" + FALCON + STAR + "\n" + second, projects=projects) == []
    swapped = "# Stories\n\n" + second + "\n" + FALCON + STAR
    assert check(tmp_path / "s", swapped, projects=projects) == [
        f"{S}:3: expected '## Checkout latency' (rank 1, {PA})",
        f"{S}:10: expected '## Ledger export retries' (rank 2, {PB})"]


def test_a_missing_and_an_extra_story(tmp_path):
    assert check(tmp_path, "# Stories\n") == [f"{S}: no story for {PA} 'Checkout latency' (rank 1)"]
    extra = STORIES + "\n## Ledger export retries\n\n" + STAR
    assert check(tmp_path, extra) == [f"{S}:10: '## Ledger export retries' is a story too many: stories are only "
                                      "for the 1 project write.py marked 'story'"]
    none = [dict(PROJECTS[0], metric_prompt=False), PROJECTS[1]]
    assert check(tmp_path / "n", "# Stories\n", projects=none) == []
    assert check(tmp_path / "m", STORIES, projects=none) == [
        f"{S}:3: '## Checkout latency' is a story too many: stories are only for projects with a metric prompt, "
        "and there are none"]


def test_the_title_line(tmp_path):
    assert check(tmp_path, "# My stories\n\n" + FALCON + STAR) == [f"{S}:1: the first line must be '# Stories'"]
    assert check(tmp_path, "") == [f"{S}:1: the first line must be '# Stories'",
                                   f"{S}: no story for {PA} 'Checkout latency' (rank 1)"]
    assert check(tmp_path, "# Stories\nIntro text.\n" + FALCON + STAR) == [
        f"{S}:2: text before the first story; stories start with '## <name>'"]


def test_the_four_star_lines(tmp_path):
    lines = STAR.splitlines()
    missing = "# Stories\n\n" + FALCON + "\n".join(lines[:3]) + "\n"
    assert check(tmp_path, missing) == [f"{S}:3: a story has the lines Situation, Task, Action and Result, once "
                                        "each and in that order (found Situation, Task, Action)"]
    swapped = "# Stories\n\n" + FALCON + "\n".join([lines[1], lines[0], lines[2], lines[3]]) + "\n"
    assert check(tmp_path, swapped) == [f"{S}:3: a story has the lines Situation, Task, Action and Result, once "
                                        "each and in that order (found Task, Situation, Action, Result)"]
    empty = STORIES.replace("- **Task:** Jordan led the fix.", "- **Task:**")
    assert check(tmp_path, empty) == [f"{S}:6: the Task line is empty"]
    stray = STORIES.replace("- **Task:** Jordan led the fix.\n", "- **Task:** Jordan led the fix.\n  More text.\n")
    assert check(tmp_path, stray) == [
        f"{S}:7: expected a '## ' heading or one of the lines '- **Situation:** …', '- **Task:** …', "
        "'- **Action:** …' and '- **Result:** …'"]
    blank_lines = STORIES.replace("\n- ", "\n\n- ")
    assert check(tmp_path, blank_lines) == []


def test_numbers_come_from_the_projects_evidence_the_reviews_or_its_metrics(tmp_path):
    from_review = STORIES.replace("Jordan led the fix.", "Jordan led the fix and cut on-call pages by 30%.")
    assert check(tmp_path, from_review) == []
    other_project = STORIES.replace("Jordan led the fix.", "Jordan led the fix across 12 packages.")
    assert check(tmp_path, other_project) == [
        f"{S}:6: the number '12' is in none of {PA}'s evidence, the performance reviews or its metrics"]


def test_problems_are_listed_in_line_order(tmp_path):
    text = "# Stories\n\n" + FALCON + "- **Situation:** 250 ms.\nstray\n" + "\n".join(STAR.splitlines()[1:]) + "\n"
    assert check(tmp_path, text) == [
        f"{S}:5: the number '250' is in none of {PA}'s evidence, the performance reviews or its metrics",
        f"{S}:6: expected a '## ' heading or one of the lines '- **Situation:** …', '- **Task:** …', "
        "'- **Action:** …' and '- **Result:** …'"]
