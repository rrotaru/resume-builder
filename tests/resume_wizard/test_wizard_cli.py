"""The wizard command lines: questions.py and answer.py."""
import json

import answer
import pytest
import questions as questions_cli

from rcore import facts, profile, sources, validation, wsio
from rrender import gate
from rwizard import metrics as metrics_mod
from rwizard.common import WizardError

from wizard_samples import (CONTOSO, NORTHWIND, TAILSPIN, candidate, complete_profile, make_workspace, metric,
                            project, snapshot)


def ws_arg(workspace):
    return ["--workspace", str(workspace)]


def ok(ws, *args):
    assert answer.main([*ws_arg(ws), *args]) == 0, args


def rejected(ws, capsys, *args) -> str:
    before = snapshot(ws)
    assert answer.main([*ws_arg(ws), *args]) == 1, args
    assert snapshot(ws) == before
    err = capsys.readouterr().err
    assert err.endswith("decisions/ unchanged\n")
    return err


# questions.py ------------------------------------------------------------------------

def test_questions_cli_on_the_fixture(workspace, capsys):
    assert questions_cli.main(ws_arg(workspace)) == 0
    assert capsys.readouterr().out == "wizard: no open questions, 1 skipped (questions.py --all lists them)\n"
    assert questions_cli.main([*ws_arg(workspace), "--all"]) == 0
    assert capsys.readouterr().out == (
        "profile:/basics/phone  phone number  (skipped)\n"
        "  answer: answer.py profile /basics/phone VALUE or answer.py skip profile:/basics/phone\n"
        "wizard: no open questions, 1 skipped\n")
    ok(workspace, "unskip", "profile:/basics/phone")
    capsys.readouterr()
    assert questions_cli.main(ws_arg(workspace)) == 0
    assert capsys.readouterr().out.endswith("wizard: 1 open question\n")


def test_questions_cli_prints_notes_details_and_errors(tmp_path, capsys):
    ws = make_workspace(tmp_path, imported=complete_profile(), projects=[project("pj_0000000a")])
    assert questions_cli.main(ws_arg(ws)) == 0
    assert capsys.readouterr().out == (
        "note: 05-terms/candidates.json not found: no term questions from the scan; run the sanitize scan "
        "(/resume-builder:sanitize)\n"
        "metric:pj_0000000a  rank 1 'Project 1' [core, team, 2025-01 to 2025-03]\n"
        "    Made exports reliable.\n"
        "    reasons: authored 3 of 4 pull requests\n"
        "  answer: answer.py metric pj_0000000a --value N --unit UNIT --statement TEXT or answer.py skip "
        "metric:pj_0000000a\n"
        "wizard: 1 open question\n")
    (ws / "decisions" / "profile.json").write_text("{", encoding="utf-8")
    assert questions_cli.main(ws_arg(ws)) == 1
    assert capsys.readouterr().err.startswith("error: decisions/profile.json: ")


# Profile answers -----------------------------------------------------------------------

def test_profile_answers_follow_the_overlay_rules(tmp_path, capsys):
    """Must: a wizard answer fills the second job's end date and leaves the first unchanged."""
    open_job = dict(TAILSPIN)
    open_job.pop("endDate")
    ws = make_workspace(tmp_path, imported=complete_profile(work=[NORTHWIND, open_job]))
    ok(ws, "profile", "/work/1/endDate", "2022-12")
    assert capsys.readouterr().out == ("recorded /work/1/endDate '2022-12' in decisions/profile.json\n"
                                       "run questions.py to see what is left\n")
    assert wsio.read_json(ws / "decisions" / "profile.json") == {"work": [{}, {"endDate": "2022-12"}]}
    effective = profile.effective_profile(ws)
    assert effective["work"] == [NORTHWIND, TAILSPIN]
    assert wsio.read_json(ws / "decisions" / "wizard.json") == {
        "anchors": [{"entry": "/work/1", "answered_for": {"position": "Software Engineer", "name": "Tailspin Toys"}}],
        "skipped": []}
    ok(ws, "profile", "/certificates/-/name", "AWS SA")
    assert "recorded /certificates/1/name 'AWS SA' in decisions/profile.json (a new entry, /certificates/1)" in \
        capsys.readouterr().out
    assert validation.validate_paths(ws, ["decisions/profile.json", "decisions/wizard.json"]) == []


@pytest.mark.parametrize("args, message", [
    (["profile", "/work/1/endDate", "Dec 2022"], "is not a date written as YYYY, YYYY-MM or YYYY-MM-DD"),
    (["profile", "/work/3/name", "X"], "/work has 2 entries; use an index up to 2"),
    (["profile", "/work/0/summary", "X"], "summary is prose; the wizard records facts only"),
    (["profile", "/basics/phone", "  "], "/basics/phone: the value is empty"),
    (["profile", "/projects/-/name", "Falcon v2"], "'Falcon v2' contains the denied term 'Falcon'"),
    (["add", "/skills/-/keywords", "Falcon"], "'Falcon' contains the denied term 'Falcon'"),
    (["unset", "/basics/phone"], "decisions/profile.json has no answer at /basics/phone"),
    (["confirm", "/work/0"], "decisions/profile.json has no answer at /work/0"),
    (["confirm", "/work/0/name"], "'/work/0/name' is not an entry such as /work/1"),
])
def test_profile_rejections_leave_every_file_unchanged(tmp_path, capsys, args, message):
    ws = make_workspace(tmp_path, imported=complete_profile(),
                        terms=[{"term": "Falcon", "replacement": "a cache", "kind": "codename"}])
    assert message in rejected(ws, capsys, *args)


def test_add_and_unset(tmp_path, capsys):
    ws = make_workspace(tmp_path, imported=complete_profile(skills=[{"name": "Backend", "keywords": ["Go"]}]))
    ok(ws, "add", "/skills/0/keywords", "Kafka")
    ok(ws, "add", "/skills/0/keywords", "Go")
    assert "'Go' is already in the profile at /skills/0/keywords; nothing recorded" in capsys.readouterr().out
    assert profile.effective_profile(ws)["skills"][0]["keywords"] == ["Go", "Kafka"]
    ok(ws, "unset", "/skills/0/keywords")
    assert wsio.read_json(ws / "decisions" / "profile.json") == {}
    assert wsio.read_json(ws / "decisions" / "wizard.json") == {"anchors": [], "skipped": []}


def test_a_moved_answer_is_fixed_by_the_wizard(tmp_path, capsys):
    """Must: the wizard owns fixing answers that a re-import moved."""
    ws = make_workspace(tmp_path, imported=complete_profile(), projects=[], candidates=[])
    ok(ws, "profile", "/work/1/location", "Remote")
    wsio.write_json(ws / "03-profile" / "profile.json", complete_profile(work=[NORTHWIND, CONTOSO, TAILSPIN]))
    capsys.readouterr()
    assert questions_cli.main(ws_arg(ws)) == 0
    out = capsys.readouterr().out
    assert out.startswith("moved:/work/1  {\"location\": \"Remote\"} was answered for 'Software Engineer, Tailspin "
                          "Toys'; /work/1 is now 'Engineer, Contoso'\n  answer: answer.py move /work/1 /work/2")
    assert "decisions/profile.json /work/1 is waiting for answer.py move, confirm or unset" in \
        rejected(ws, capsys, "profile", "/work/1/startDate", "2018")
    assert "/work/5: /work has 3 entries; use an index up to 3" in rejected(ws, capsys, "move", "/work/1", "/work/5")
    ok(ws, "move", "/work/1", "/work/2")
    assert wsio.read_json(ws / "decisions" / "profile.json") == {"work": [{}, {}, {"location": "Remote"}]}
    assert profile.effective_profile(ws)["work"][2] == dict(TAILSPIN, location="Remote")
    assert profile.effective_profile(ws)["work"][1] == CONTOSO
    capsys.readouterr()
    assert questions_cli.main(ws_arg(ws)) == 0
    assert capsys.readouterr().out == "wizard: no open questions\n"


def test_confirm_and_unset_resolve_a_moved_answer(tmp_path, capsys):
    ws = make_workspace(tmp_path, imported=complete_profile(certificates=[]),
                        wizard={"certificates": [{"name": "CKA"}]})
    ok(ws, "confirm", "/certificates/0")
    assert "confirmed the answer at /certificates/0 for a new certificates entry" in capsys.readouterr().out
    assert wsio.read_json(ws / "decisions" / "wizard.json")["anchors"] == [
        {"entry": "/certificates/0", "answered_for": None}]
    wsio.write_json(ws / "03-profile" / "profile.json", complete_profile())
    ok(ws, "unset", "/certificates/0")
    assert wsio.read_json(ws / "decisions" / "profile.json") == {}
    assert wsio.read_json(ws / "decisions" / "wizard.json")["anchors"] == []


# Terms ---------------------------------------------------------------------------------

def test_term_decisions(tmp_path, capsys):
    ws = make_workspace(tmp_path, imported=complete_profile(projects=[{"name": "Falcon"}]),
                        candidates=[candidate("Falcon"), candidate("Contoso Bank", "a bank", "customer")])
    ok(ws, "term", "Contoso Bank", "--replacement", "a top-10 US bank")
    assert capsys.readouterr().out.startswith(
        "recorded 'Contoso Bank' denied, replaced by 'a top-10 US bank' (customer) in decisions/terms.json\n")
    ok(ws, "term", "falcon", "--allow")
    ok(ws, "term", "Falcon", "--replacement", "the checkout platform")
    out = capsys.readouterr().out
    assert "1 fact field of the profile holds a denied term: questions.py lists them as fact: questions" in out
    assert wsio.read_json(ws / "decisions" / "terms.json") == [
        {"term": "Contoso Bank", "replacement": "a top-10 US bank", "kind": "customer"},
        {"term": "Falcon", "replacement": "the checkout platform", "kind": "codename"}]
    ok(ws, "term", "ContosoBank", "--allow", "--kind", "other")
    assert "notice: allowed term 'ContosoBank' looks like denied term 'Contoso Bank'" in capsys.readouterr().out
    assert "give --kind" in rejected(ws, capsys, "term", "Nightjar", "--allow")
    assert "the replacement for 'Nightjar' ('a Falcon tool') contains the denied term 'Falcon'" in \
        rejected(ws, capsys, "term", "Nightjar", "--replacement", "a Falcon tool", "--kind", "codename")
    assert "allowed term 'Contoso Bank Group' contains denied term 'Contoso Bank'" in \
        rejected(ws, capsys, "term", "Contoso Bank Group", "--allow", "--kind", "customer")
    assert "the replacement for 'Nightjar' is empty" in \
        rejected(ws, capsys, "term", "Nightjar", "--replacement", " ", "--kind", "codename")
    assert "is not in decisions/terms.json" in rejected(ws, capsys, "remove-term", "Nightjar")


def test_remove_term_repairs_an_invalid_file(tmp_path, capsys):
    ws = make_workspace(tmp_path, terms=[{"term": "Contoso", "replacement": "a bank", "kind": "customer"},
                                         {"term": "Contoso Bank", "replacement": None, "kind": "customer"}])
    assert "allowed term 'Contoso Bank' contains denied term 'Contoso'" in \
        rejected(ws, capsys, "term", "Falcon", "--allow", "--kind", "codename")
    ok(ws, "remove-term", "contoso bank")
    assert wsio.read_json(ws / "decisions" / "terms.json") == [
        {"term": "Contoso", "replacement": "a bank", "kind": "customer"}]


def test_a_denied_fact_field_gets_a_replacement_at_its_path(tmp_path, capsys):
    """Must: a fact field holding a denied term is asked about, and the answer is stored at that path."""
    ws = make_workspace(tmp_path, imported=complete_profile(projects=[{"name": "Falcon", "url": "https://x.dev"}]),
                        projects=[], candidates=[candidate("Falcon")])
    ok(ws, "term", "Falcon", "--replacement", "the checkout platform")
    capsys.readouterr()
    assert questions_cli.main(ws_arg(ws)) == 0
    assert capsys.readouterr().out == ("fact:/projects/0/name  'Falcon' holds the denied term 'Falcon'\n"
                                       "  answer: answer.py profile /projects/0/name VALUE\n"
                                       "wizard: 1 open question\n")
    assert "cannot be skipped" in rejected(ws, capsys, "skip", "fact:/projects/0/name")
    ok(ws, "profile", "/projects/0/name", "Checkout platform")
    assert wsio.read_json(ws / "decisions" / "profile.json") == {"projects": [{"name": "Checkout platform"}]}
    tailored = {"projects": [{"name": "Checkout platform", "url": "https://x.dev", "x-highlights": []}]}
    assert facts.check(tailored, profile.effective_profile(ws), "resume.json") == []
    capsys.readouterr()
    assert questions_cli.main(ws_arg(ws)) == 0
    assert capsys.readouterr().out == "wizard: no open questions\n"


# Metrics -------------------------------------------------------------------------------

def test_metrics(tmp_path, capsys):
    projects = [project("pj_0000000a", 1, evidence=["ev_00000002", "ev_00000001"], name="Ledger"),
                project("pj_0000000b", 2, prompt=False)]
    ws = make_workspace(tmp_path, imported=complete_profile(), projects=projects,
                        metrics=[metric("m_1", "pj_0000dead"), metric("m_old", "pj_0000000b")])
    ok(ws, "metric", "pj_0000000a", "--value", "1200", "--unit", "requests/s", "--statement",
       "raised throughput to 1,200 requests/s")
    assert "recorded m_2 'raised throughput to 1,200 requests/s' (1200 requests/s) for pj_0000000a 'Ledger'" in \
        capsys.readouterr().out
    saved = wsio.read_json(ws / "decisions" / "metrics.json")[-1]
    assert saved == {"id": "m_2", "project_id": "pj_0000000a", "value": 1200, "unit": "requests/s",
                     "statement": "raised throughput to 1,200 requests/s",
                     "evidence_ids": ["ev_00000001", "ev_00000002"]}
    ok(ws, "relink-metric", "m_1", "pj_0000000a")
    assert wsio.read_json(ws / "decisions" / "metrics.json")[0]["project_id"] == "pj_0000000a"
    ok(ws, "remove-metric", "m_old")
    assert [m["id"] for m in wsio.read_json(ws / "decisions" / "metrics.json")] == ["m_1", "m_2"]
    assert "does not state the value 40" in rejected(ws, capsys, "metric", "pj_0000000a", "--value", "40", "--unit",
                                                     "%", "--statement", "cut latency a lot")
    assert "is not a project in 04-projects/projects.json" in \
        rejected(ws, capsys, "metric", "pj_0000dead", "--value", "4", "--unit", "x", "--statement", "4x")
    assert "the value 'lots' is not a number" in \
        rejected(ws, capsys, "metric", "pj_0000000a", "--value", "lots", "--unit", "x", "--statement", "4x")
    # An exponent would pass as a value but could never be found in the statement.
    assert "the value '1e6' is not a number written as digits" in \
        rejected(ws, capsys, "metric", "pj_0000000a", "--value", "1e6", "--unit", "requests", "--statement",
                 "processed 1e6 requests")
    # A blank unit would record an incomplete metric and silence the project's metric question.
    assert "the unit is empty" in \
        rejected(ws, capsys, "metric", "pj_0000000a", "--value", "4", "--unit", "  ", "--statement", "4x faster")
    assert "m_9 is not in decisions/metrics.json" in rejected(ws, capsys, "remove-metric", "m_9")


def test_metric_helpers():
    assert metrics_mod.parse_value("40") == 40 and metrics_mod.parse_value("2.5") == 2.5
    assert metrics_mod.parse_value(" -3 ") == -3 and metrics_mod.parse_value("0.5") == 0.5
    for text in ("1e6", "1,200", "inf", "nan", ".5", "40%"):
        with pytest.raises(WizardError, match="is not a number written as digits"):
            metrics_mod.parse_value(text)
    assert metrics_mod.states_value("cut costs by $1,200,000 a year", 1200000)
    assert metrics_mod.states_value("error rate fell 3.5 points", -3.5)
    assert not metrics_mod.states_value("latency cut 40%", 4)
    assert metrics_mod.next_id([{"id": "m_1"}, {"id": "m_7"}, {"id": "m_custom"}]) == "m_8"
    assert metrics_mod.next_id([]) == "m_1"


# Skips ---------------------------------------------------------------------------------

def test_skip_and_unskip(tmp_path, capsys):
    imported = complete_profile()
    imported["basics"].pop("phone")
    ws = make_workspace(tmp_path, imported=imported, projects=[project("pj_0000000a")], candidates=[])
    ok(ws, "skip", "profile:/basics/phone")
    ok(ws, "skip", "metric:pj_0000000a")
    ok(ws, "skip", "metric:pj_0000000a")
    assert "metric:pj_0000000a is skipped already" in capsys.readouterr().out
    assert wsio.read_json(ws / "decisions" / "wizard.json")["skipped"] == [
        {"question": "profile:/basics/phone"}, {"question": "metric:pj_0000000a"}]
    assert "profile:/basics/email is not an open question" in rejected(ws, capsys, "skip", "profile:/basics/email")
    assert "profile:/basics/email is not skipped" in rejected(ws, capsys, "unskip", "profile:/basics/email")
    ok(ws, "unskip", "metric:pj_0000000a")
    assert wsio.read_json(ws / "decisions" / "wizard.json")["skipped"] == [{"question": "profile:/basics/phone"}]


# The fixture ---------------------------------------------------------------------------

def test_answers_keep_the_fixture_renderable(workspace, capsys):
    ok(workspace, "unskip", "profile:/basics/phone")
    ok(workspace, "profile", "/basics/phone", "(555) 010-0100")
    ok(workspace, "metric", "pj_da2a2b53", "--value", "99.9", "--unit", "%", "--statement",
       "kept checkout availability at 99.9%")
    assert validation.validate_workspace(workspace) == []
    targets, _ = gate.discover(workspace)
    assert gate.run(workspace, targets) == []
    assert sources.check_file(workspace, "06-bullets/bullets.json") == []
    assert json.loads((workspace / "decisions" / "wizard.json").read_text(encoding="utf-8"))["skipped"] == []
