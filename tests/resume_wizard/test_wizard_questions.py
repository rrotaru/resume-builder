"""The open questions (rwizard.questions): each kind, its order, skips and notes."""
import pytest

from conftest import FIXTURE_WORKSPACE
from rcore import wsio
from rwizard import questions
from rwizard.common import WizardError

from wizard_samples import CONTOSO, NORTHWIND, TAILSPIN, candidate, complete_profile, make_workspace, metric, project


def asked(ws, include_skipped=False):
    found, notes = questions.compute(questions.context(ws))
    return [q.key for q in found if include_skipped or not q.skipped], notes


def test_the_fixture_has_no_open_questions(workspace):
    assert asked(workspace)[0] == []
    assert asked(workspace, include_skipped=True)[0] == ["profile:/basics/phone"]
    state = wsio.read_json(workspace / "decisions" / "wizard.json")
    state["skipped"] = []
    wsio.write_json(workspace / "decisions" / "wizard.json", state)
    [question] = questions.compute(questions.context(workspace))[0]
    assert (question.key, question.text, question.answer) == (
        "profile:/basics/phone", "phone number",
        "answer.py profile /basics/phone VALUE or answer.py skip profile:/basics/phone")


def test_a_complete_workspace_has_none(tmp_path):
    ws = make_workspace(tmp_path, imported=complete_profile(), projects=[], candidates=[])
    assert asked(ws) == ([], [])


@pytest.mark.parametrize("change, keys", [
    (lambda p: p.pop("basics"), ["profile:/basics/name", "profile:/basics/email", "profile:/basics/phone",
                                 "profile:/basics/location", "profile:/basics/profiles"]),
    (lambda p: p["basics"].pop("url"), ["profile:/basics/profiles"]),
    (lambda p: p["basics"].update(url="", profiles=[{"network": "GitHub"}]), []),
    (lambda p: p["basics"]["location"].pop("city"), ["profile:/basics/location"]),
    (lambda p: p["work"].append({"position": "Intern"}), ["profile:/work/2/name", "profile:/work/2/startDate"]),
    (lambda p: p.update(education=[]), ["profile:/education"]),
    (lambda p: p.update(education=[{"institution": "State"}]),
     ["profile:/education/0/studyType", "profile:/education/0/area", "profile:/education/0/endDate"]),
    (lambda p: p.pop("certificates"), ["profile:/certificates"]),
    (lambda p: p.update(certificates=[{"name": "CKA"}]),
     ["profile:/certificates/0/issuer", "profile:/certificates/0/date"]),
])
def test_missing_profile_fields(tmp_path, change, keys):
    imported = complete_profile()
    change(imported)
    ws = make_workspace(tmp_path, imported=imported, projects=[], candidates=[])
    assert asked(ws)[0] == keys


def test_wizard_answers_count_as_present(tmp_path):
    imported = complete_profile()
    imported["basics"].pop("phone")
    ws = make_workspace(tmp_path, imported=imported, wizard={"basics": {"phone": "555"}}, projects=[], candidates=[])
    assert asked(ws)[0] == []


def test_an_open_job_is_asked_about_only_for_json_resume(tmp_path):
    ws = make_workspace(tmp_path, imported=complete_profile(), projects=[], candidates=[], source_format="pdf")
    assert asked(ws)[0] == []
    ws = make_workspace(tmp_path / "j", imported=complete_profile(), projects=[], candidates=[], source_format="json")
    assert asked(ws)[0] == ["profile:/work/0/endDate"]
    [question] = questions.compute(questions.context(ws))[0]
    assert question.text == "end date (skip it if the job is current) of /work/0 'Senior Software Engineer, " \
                            "Northwind Payments'"


def test_the_name_cannot_be_skipped(tmp_path):
    imported = complete_profile()
    imported["basics"].pop("name")
    ws = make_workspace(tmp_path, imported=imported, projects=[], candidates=[])
    [question] = questions.compute(questions.context(ws))[0]
    assert question.key == "profile:/basics/name" and not question.skippable
    assert question.answer == "answer.py profile /basics/name VALUE"


def test_metric_questions_only_for_metric_prompt_projects(tmp_path):
    projects = [project("pj_0000000a", 1), project("pj_0000000b", 2), project("pj_0000000c", 3, prompt=False)]
    ws = make_workspace(tmp_path, imported=complete_profile(), projects=projects, candidates=[],
                        metrics=[metric("m_1", "pj_0000000b")])
    found, _ = questions.compute(questions.context(ws))
    assert [q.key for q in found] == ["metric:pj_0000000a"]
    assert found[0].text == "rank 1 'Project 1' [core, team, 2025-01 to 2025-03]"
    assert found[0].details == ["Made exports reliable.", "reasons: authored 3 of 4 pull requests"]
    ws = make_workspace(tmp_path / "s", imported=complete_profile(), projects=projects, candidates=[],
                        state={"anchors": [], "skipped": [{"question": "metric:pj_0000000a"}]})
    assert asked(ws)[0] == ["metric:pj_0000000b"]


@pytest.mark.parametrize("decisions, reason", [
    ([], "pj_0000dead is not a project in 04-projects/projects.json"),
    ([{"project_id": "pj_0000dead", "action": "exclude"}], "pj_0000dead was excluded by decision 1"),
    ([{"project_id": "pj_0000000a", "action": "set_role", "role": "lead"},
      {"project_id": "pj_0000000a", "action": "merge", "merge_with": ["pj_0000dead"]}],
     "pj_0000dead was merged into pj_0000000a by decision 2"),
])
def test_a_metric_whose_project_is_gone(tmp_path, decisions, reason):
    projects = [project("pj_0000000a", 1, evidence=["ev_00000001", "ev_00000002"], name="Ledger"),
                project("pj_0000000b", 2, evidence=["ev_00000003"])]
    ws = make_workspace(tmp_path, imported=complete_profile(), projects=projects, candidates=[], decisions=decisions,
                        metrics=[metric("m_1", "pj_0000dead", evidence=["ev_00000001", "ev_00000009"]),
                                 metric("m_2", "pj_0000000a"), metric("m_3", "pj_0000000b")])
    found, _ = questions.compute(questions.context(ws))
    assert found[0].key == "metric-gone:m_1"
    assert found[0].text == f"'latency cut 40%': {reason}; closest is pj_0000000a 'Ledger' (1 of its 2 items)"
    assert found[0].answer == "answer.py relink-metric m_1 PJ or answer.py remove-metric m_1"


def test_terms_from_the_scan_and_new_terms(tmp_path):
    ws = make_workspace(tmp_path, imported=complete_profile(), projects=[],
                        terms=[{"term": "Falcon", "replacement": "a cache", "kind": "codename"}],
                        candidates=[candidate("falcon"), candidate("Contoso Bank", "a bank", "customer",
                                                                  ["pj_1", "ev_1", "ev_2", "ev_3"])],
                        new_terms=[candidate("contoso-bank"), candidate("Nightjar", found=["b_1", "stories.md:3"])])
    found, _ = questions.compute(questions.context(ws))
    assert [(q.key, q.text, q.answer) for q in found] == [
        ("term:Contoso Bank", "customer, proposed 'a bank'; in 4 places: pj_1, ev_1, ev_2 and 1 more",
         "answer.py term 'Contoso Bank' --replacement TEXT or answer.py term 'Contoso Bank' --allow"),
        ("term:Nightjar",
         "codename, proposed 'a generic name'; in 2 places: b_1, stories.md:3; a new term from 07-sanitized",
         "answer.py term Nightjar --replacement TEXT or answer.py term Nightjar --allow"),
    ]


def test_fact_fields_holding_a_denied_term(tmp_path):
    imported = complete_profile(projects=[{"name": "Falcon", "description": "Falcon linter"}],
                                skills=[{"name": "Tools", "keywords": ["Falcon SDK", "Go"]}])
    ws = make_workspace(tmp_path, imported=imported, projects=[], candidates=[],
                        terms=[{"term": "Falcon", "replacement": "a cache", "kind": "codename"}])
    found, notes = questions.compute(questions.context(ws))
    assert [(q.key, q.text, q.answer) for q in found] == [
        ("fact:/projects/0/name", "'Falcon' holds the denied term 'Falcon'",
         "answer.py profile /projects/0/name VALUE")]
    assert notes == ["note: /skills/0/keywords/0 'Falcon SDK' holds the denied term 'Falcon'; a keyword cannot be "
                     "replaced, so resume-ats leaves it out"]
    ws = make_workspace(tmp_path / "w", imported=imported, projects=[], candidates=[],
                        wizard={"projects": [{"name": "Checkout linter"}]},
                        state={"anchors": [{"entry": "/projects/0", "answered_for": {"name": "Falcon"}}],
                               "skipped": []},
                        terms=[{"term": "Falcon", "replacement": "a cache", "kind": "codename"}])
    assert asked(ws)[0] == []


def test_moved_answers_come_first_with_a_suggestion(tmp_path):
    ws = make_workspace(
        tmp_path, imported=complete_profile(work=[dict(NORTHWIND), dict(CONTOSO), dict(TAILSPIN)]), projects=[],
        candidates=[candidate("Nightjar")], wizard={"work": [{}, {"location": "Remote"}]},
        state={"anchors": [{"entry": "/work/1", "answered_for": {"position": "Software Engineer",
                                                                 "name": "Tailspin Toys"}}], "skipped": []})
    found, _ = questions.compute(questions.context(ws))
    assert [q.key for q in found] == ["moved:/work/1", "term:Nightjar"]
    assert found[0].answer == ("answer.py move /work/1 /work/2 ('Software Engineer, Tailspin Toys' is now /work/2), "
                               "answer.py confirm /work/1 or answer.py unset /work/1")


def test_notes_for_missing_inputs_and_notices(tmp_path):
    ws = make_workspace(tmp_path, terms=[{"term": "Contoso Bank", "replacement": "a bank", "kind": "customer"},
                                         {"term": "ContosoBank", "replacement": None, "kind": "other"}])
    keys, notes = asked(ws)
    assert notes == [
        "note: 03-profile/profile.json not found: profile questions use decisions/profile.json only; run "
        "/resume-builder:import to import a resume",
        "note: 04-projects/projects.json not found: no metric questions; run /resume-builder:analyze",
        "note: 05-terms/candidates.json not found: no term questions from the scan; run the sanitize scan "
        "(/resume-builder:sanitize)",
        "notice: allowed term 'ContosoBank' looks like denied term 'Contoso Bank'; confirm at checkpoint 4 that it "
        "is a different word"]
    assert keys[0] == "profile:/basics/name"


def test_an_invalid_file_stops_the_wizard(tmp_path):
    ws = make_workspace(tmp_path, metrics=[{"id": "m_1"}])
    with pytest.raises(WizardError) as caught:
        questions.context(ws)
    assert "decisions/metrics.json: $[0]: missing required property 'project_id'" in str(caught.value)


def test_the_fixture_anchors_its_certificate_and_skips_the_phone():
    saved = wsio.read_json(FIXTURE_WORKSPACE / "decisions" / "wizard.json")
    assert saved == {"anchors": [{"entry": "/certificates/0", "answered_for": None}],
                     "skipped": [{"question": "profile:/basics/phone"}]}
