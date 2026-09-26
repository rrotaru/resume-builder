"""rwrite.bullets: each check of the model's bullets, places and IDs."""
import copy

import pytest

from rwrite import bullets, common, material
from write_samples import PA, PB, PROFILE, bullet, eid, good_bullets, make_workspace, metric, project

D = "06-bullets.tmp/bullets.json"


def check(tmp_path, draft, **workspace):
    ws = make_workspace(tmp_path, **workspace)
    return bullets.check(draft, material.build(ws, common.load_inputs(ws)))


def edited(index, **changes):
    draft = good_bullets()
    draft[index].update(changes)
    return draft


def test_the_sample_draft_passes(tmp_path):
    assert check(tmp_path, good_bullets()) == []


def test_the_draft_must_match_the_schema_with_id_optional(tmp_path):
    draft = good_bullets()
    draft[0]["id"] = "anything"  # ignored
    assert check(tmp_path, draft) == []
    del draft[1]["work_ref"]
    draft[2]["form"] = "star"
    assert check(tmp_path, draft) == [f"{D}: $[1]: missing required property 'work_ref'",
                                      f"{D}: $[2].form: 'star' is not one of ['xyz_quantified', 'xyz']"]
    assert check(tmp_path, {"bullets": []}) == [f"{D}: $: expected array, got dict"]


@pytest.mark.parametrize("text, problem", [
    ("Made exports retry\non failure", "/1/text: holds a line break; a bullet is one line"),
    ("Made exports retry on failure", "/1/text: holds a line break; a bullet is one line"),
    (" Made exports retry", "/1/text: begins or ends with a space"),
    ("Made exports retry\n", "/1/text: holds a line break; a bullet is one line"),
])
def test_text_is_one_line_without_surrounding_spaces(tmp_path, text, problem):
    assert f"{D}: {problem}" in check(tmp_path, edited(1, text=text))


def test_two_bullets_with_the_same_text(tmp_path):
    draft = good_bullets()
    draft.append(dict(draft[1]))
    assert check(tmp_path, draft) == [f"{D}: /5/text: same text as /1"]


def test_sources(tmp_path):
    assert check(tmp_path, edited(1, sources=[])) == [
        f"{D}: /1/sources: a bullet needs at least one source",
        f"{D}: /1/sources: cites none of {PB}'s evidence; a project bullet cites at least one item of its project"]
    assert check(tmp_path, edited(1, sources=[eid(3), eid(3)])) == [f"{D}: /1/sources/1: {eid(3)} is listed twice"]
    assert check(tmp_path, edited(1, sources=[eid(3), "ev_0badc0de", "metric:m_9"])) == [
        f"{D}: /1/sources/1: ev_0badc0de: unknown evidence id", f"{D}: /1/sources/2: metric:m_9: unknown metric id",
        f"{D}: /1/form: the bullet cites a metric, so its form is xyz_quantified"]
    assert check(tmp_path, edited(3, sources=["resume:/work/1/highlights/9", "resume:/work/1/highlights/0"])) == [
        f"{D}: /3/sources/0: resume:/work/1/highlights/9: does not resolve in 03-profile/profile.json"]
    assert check(tmp_path, edited(3, sources=["resume:/work/1/highlights/0", "resume:/work/1/x-lines/first"])) == [
        f"{D}: /3/sources/1: resume:/work/1/x-lines/first points into x-lines, which is not resume text"]


def test_an_unknown_project(tmp_path):
    problems = check(tmp_path, edited(1, project_id="pj_0badc0de"))
    assert problems[0] == f"{D}: /1/project_id: pj_0badc0de is not a project in 04-projects/projects.json"
    assert f"{D}: /1/sources/0: {eid(3)} is evidence of {PB}, not of this bullet's project pj_0badc0de" in problems
    assert f"{D}: {PB} 'Ledger export retries' has no bullet" in problems


def test_evidence_of_another_project_or_of_no_project(tmp_path):
    assert check(tmp_path, edited(1, sources=[eid(3), eid(1)])) == [
        f"{D}: /1/sources/1: {eid(1)} is evidence of {PA}, not of this bullet's project {PB}"]
    assert check(tmp_path, edited(1, sources=[eid(3), eid(4)])) == [
        f"{D}: /1/sources/1: {eid(4)} is in no project and is not a performance review"]
    assert check(tmp_path, edited(2, sources=[eid(5), eid(3)])) == [
        f"{D}: /2/sources/1: {eid(3)} is evidence of {PB}; a bullet without a project cites only performance "
        "reviews and the profile"]


def test_an_excluded_projects_evidence_cannot_come_back(tmp_path):
    """Evidence of a project the engineer excluded is in no project of projects.json."""
    draft = [b for b in good_bullets() if b["project_id"] != PB]
    draft.append(bullet("Made ledger exports retry on failure", [eid(3)], None, 0))
    assert check(tmp_path, draft, projects=[project(PA, [1, 2], "Checkout latency", 1, "2025-02", "2025-05", True)]
                 ) == [f"{D}: /4/sources/0: {eid(3)} is in no project and is not a performance review"]


def test_a_project_bullet_needs_its_own_evidence_but_may_add_reviews_and_resume_text(tmp_path):
    assert check(tmp_path, edited(0, sources=[eid(5), "metric:m_1"])) == [
        f"{D}: /0/sources: cites none of {PA}'s evidence; a project bullet cites at least one item of its project"]
    draft = good_bullets()
    draft[1]["sources"] = [eid(3), eid(5), "wizard:/basics/email"]
    assert check(tmp_path, draft, wizard={"basics": {"email": "j@example.com"}}) == []


def test_metrics(tmp_path):
    metrics = [metric("m_1", PA, 40, "p99 checkout latency reduced 40%"), metric("m_2", PB, 3, "3 retries")]
    draft = good_bullets()
    draft[1] = bullet("Made ledger exports retry 3 times", [eid(3), "metric:m_1", "metric:m_2"], PB, 0,
                      "xyz_quantified")
    assert check(tmp_path, draft, metrics=metrics) == [
        f"{D}: /1/sources/1: metric:m_1 belongs to {PA}, not to this bullet's project {PB}"]
    draft[1] = bullet("Made ledger exports retry", [eid(3), "metric:m_2"], PB, 0, "xyz_quantified")
    assert check(tmp_path, draft, metrics=metrics) == [f"{D}: /1/text: does not state 3, the value of metric:m_2"]
    draft = edited(2, sources=[eid(5), "metric:m_1"], form="xyz_quantified", text="Cut pages by 30% and latency 40%")
    assert check(tmp_path, draft) == [f"{D}: /2/sources/1: metric:m_1: a bullet without a project cannot cite a metric"]


def test_a_metric_of_a_project_that_is_gone(tmp_path):
    metrics = [metric("m_1", PA, 40, "p99 checkout latency reduced 40%"), metric("m_2", "pj_1d2c3b4a", 5, "5 fewer")]
    assert check(tmp_path, good_bullets(), metrics=metrics) == []  # not required
    draft = edited(1, sources=[eid(3), "metric:m_2"], form="xyz_quantified", text="Cut failed exports by 5")
    assert check(tmp_path, draft, metrics=metrics) == [
        f"{D}: /1/sources/1: metric:m_2 belongs to pj_1d2c3b4a (not a project in 04-projects/projects.json; the "
        f"wizard re-links or removes it), not to this bullet's project {PB}"]


def test_forms_follow_the_metric(tmp_path):
    assert check(tmp_path, edited(0, form="xyz")) == [
        f"{D}: /0/form: the bullet cites a metric, so its form is xyz_quantified"]
    assert check(tmp_path, edited(1, form="xyz_quantified")) == [
        f"{D}: /1/form: xyz_quantified needs a metric: source; without one the form is xyz"]


def test_every_number_needs_a_source(tmp_path):
    assert check(tmp_path, edited(0, text="Cut p99 checkout latency 40% to 250 ms across 3 regions")) == [
        f"{D}: /0/text: the number '250' is in none of its sources"]  # 3 regions is in ev 2
    assert check(tmp_path, edited(1, text="Made 12 ledger exports retry")) == [
        f"{D}: /1/text: the number '12' is in none of its sources"]  # 12 is in evidence it does not cite
    assert check(tmp_path, edited(2, sources=[eid(5)], text="Cut on-call pages by 30%")) == []  # the review's full text
    assert check(tmp_path, edited(3, text="Migrated the order service to Go, serving 2,000,000 requests a day")) == [
        f"{D}: /3/text: the number '2,000,000' is in none of its sources"]
    assert check(tmp_path, edited(4, text="Built ledger-lint, a linter with 300 GitHub stars")) == []


def test_line_counts_are_not_a_source(tmp_path):
    evidence = [dict(e) for e in make_evidence()]
    evidence[2]["stats"] = {"additions": 812, "deletions": 140, "files": 23}
    assert check(tmp_path, edited(1, text="Made ledger exports retry in an 812-line change"), evidence=evidence) == [
        f"{D}: /1/text: the number '812' is in none of its sources"]


def make_evidence():
    from write_samples import EVIDENCE
    return copy.deepcopy(EVIDENCE)


# Places ------------------------------------------------------------------------

def test_a_project_bullets_job_must_overlap_the_project(tmp_path):
    assert check(tmp_path, edited(0, work_ref=1)) == [
        f"{D}: /0/work_ref: /work/1 (2019-06 to 2022-12) does not overlap {PA} (2025-02 to 2025-05); use /work/0"]
    assert check(tmp_path, edited(0, work_ref=None)) == [
        f"{D}: /0/work_ref: null, but /work/0 overlaps {PA} (2025-02 to 2025-05); set work_ref to it"]
    assert check(tmp_path, edited(0, work_ref=2)) == [
        f"{D}: /0/work_ref: 2 is not a job in the profile (it has 2)"]


def test_a_project_overlapping_two_jobs_may_go_under_either(tmp_path):
    wizard = {"work": [{"endDate": "2025-03"}, {}, {"name": "Contoso", "position": "Staff", "startDate": "2025-04"}]}
    for work_ref in (0, 2):
        draft = edited(0, work_ref=work_ref)
        draft[1]["work_ref"] = draft[2]["work_ref"] = 2  # pj_0000000b and the review are after /work/0 ended
        assert check(tmp_path / str(work_ref), draft, wizard=wizard) == []
    draft = edited(0, work_ref=None)
    draft[1]["work_ref"] = 2
    assert check(tmp_path / "null", draft, wizard=wizard) == [
        f"{D}: /0/work_ref: null, but /work/0, /work/2 overlaps {PA} (2025-02 to 2025-05); set work_ref to one "
        "of them"]


def test_a_project_no_job_overlaps_has_no_place(tmp_path):
    profile = copy.deepcopy(PROFILE)
    profile["work"][0]["endDate"] = "2024-12"
    draft = edited(0, work_ref=None)
    draft[1]["work_ref"] = None
    draft[2]["work_ref"] = 1
    assert check(tmp_path, draft, profile=profile) == []
    assert bullets.place(draft[0]) is None
    assert check(tmp_path / "x", edited(0, work_ref=0), profile=profile)[0] == (
        f"{D}: /0/work_ref: /work/0 (2023-01 to 2024-12) does not overlap {PA} (2025-02 to 2025-05); no job "
        "overlaps it: use null")


def test_resume_pointers_into_a_job_need_that_work_ref(tmp_path):
    assert check(tmp_path, edited(3, work_ref=0)) == [
        f"{D}: /3/sources/0: resume:/work/1/highlights/0 is in /work/1, so work_ref must be 1"]
    assert check(tmp_path, edited(3, work_ref=None)) == [
        f"{D}: /3/sources/0: resume:/work/1/highlights/0 is in /work/1, so work_ref must be 1"]
    draft = edited(0, sources=[eid(1), "metric:m_1", "resume:/work/0/position"])
    assert check(tmp_path, draft) == []  # a pointer into its own job


def test_a_profile_project_bullet(tmp_path):
    assert check(tmp_path, edited(4, work_ref=0)) == [
        f"{D}: /4/work_ref: must be null: the bullet cites the profile project /projects/0"]
    profile = copy.deepcopy(PROFILE)
    profile["projects"].append({"name": "ledger-fmt", "description": "Formatter"})
    draft = edited(4, sources=["resume:/projects/0/description", "resume:/projects/1/description"])
    assert check(tmp_path, draft, profile=profile) == [
        f"{D}: /4/sources/1: resume:/projects/1/description is in /projects/1, but /sources/0 is in /projects/0; a "
        "bullet goes in one place"]
    draft = edited(4, sources=["resume:/projects/0/description", "resume:/work/1/name"])
    assert check(tmp_path / "x", draft) == [
        f"{D}: /4/sources/1: resume:/work/1/name is in /work/1, but the bullet cites the profile project "
        "/projects/0; a bullet goes in one place"]


def test_a_project_bullet_placed_in_a_profile_project(tmp_path):
    draft = edited(1, work_ref=None, sources=[eid(3), "resume:/projects/0/name"])
    assert check(tmp_path, draft) == []
    assert bullets.place(draft[1]) == "/projects/0"


def test_a_bullet_without_a_project_needs_a_place(tmp_path):
    assert check(tmp_path, edited(2, work_ref=None)) == [
        f"{D}: /2: a bullet without a project needs a place: a work_ref, or a resume: pointer into /projects/<i>"]
    draft = edited(2, work_ref=None, sources=[eid(5), "resume:/basics/name"], text="Led the cache work")
    assert check(tmp_path, draft)[0] == \
        f"{D}: /2: a bullet without a project needs a place: a work_ref, or a resume: pointer into /projects/<i>"


def test_a_job_the_wizard_added_is_a_place(tmp_path):
    wizard = {"work": [{}, {}, {"name": "Contoso", "position": "Staff Engineer", "startDate": "2025-08"}]}
    assert check(tmp_path, edited(2, work_ref=2), wizard=wizard) == []


def test_without_a_profile_every_bullet_without_a_project_is_refused(tmp_path):
    draft = [edited(0, work_ref=None)[0], edited(1, work_ref=None)[1], edited(2, work_ref=0)[2]]
    assert check(tmp_path, draft, profile=None) == [
        f"{D}: /2/work_ref: 0 is not a job in the profile (the profile has no jobs)"]


# Completeness ------------------------------------------------------------------

def test_every_project_metric_and_resume_highlight_is_covered(tmp_path):
    assert check(tmp_path, good_bullets()[2:]) == [
        f"{D}: {PA} 'Checkout latency' has no bullet", f"{D}: {PB} 'Ledger export retries' has no bullet",
        f"{D}: metric:m_1 ({PA}) is cited by no bullet"]
    assert check(tmp_path, good_bullets()[:3]) == [f"{D}: resume:/work/1/highlights/0 is cited by no bullet",
                                                   f"{D}: resume:/projects/0/description is cited by no bullet"]
    draft = edited(0, form="xyz", sources=[eid(1), eid(2)], text="Cut p99 checkout latency with a cache")
    assert check(tmp_path, draft) == [f"{D}: metric:m_1 ({PA}) is cited by no bullet"]


# Places and IDs ----------------------------------------------------------------

def test_place():
    draft = good_bullets()
    assert [bullets.place(b) for b in draft] == ["/work/0", "/work/0", "/work/0", "/work/1", "/projects/0"]


def test_ids_count_in_file_order_on_a_first_run():
    records = bullets.assign_ids(good_bullets(), [])
    assert [r["id"] for r in records] == ["b_1", "b_2", "b_3", "b_4", "b_5"]
    assert list(records[0]) == ["id", "project_id", "work_ref", "text", "form", "sources"]
    assert records[0]["sources"] == [eid(1), eid(2), "metric:m_1"]


def test_unchanged_texts_keep_their_ids():
    previous = [{**b, "id": i} for b, i in zip(good_bullets(), ["b_1", "b_2", "b_7", "b_x", "b_5"])]
    draft = good_bullets()
    draft.insert(1, bullet("A new bullet", [eid(3)], PB, 0))
    draft[3]["text"] = "Cut on-call pages by 30%"  # changed
    draft.append(dict(draft[0]))  # the same text twice takes the ID once
    ids = [r["id"] for r in bullets.assign_ids(draft, previous)]
    assert ids == ["b_1", "b_8", "b_2", "b_9", "b_x", "b_5", "b_10"]


def test_a_models_id_is_ignored():
    draft = good_bullets()
    draft[0]["id"] = "b_42"
    assert bullets.assign_ids(draft, [])[0]["id"] == "b_1"
