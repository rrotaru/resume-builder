"""The sanitize command lines end to end: scan.py and apply.py."""
import json
import shutil

import apply
import pytest
import scan

from conftest import FIXTURE_WORKSPACE
from rcore import stages, validation, wsio
from rrender import gate

from sanitize_samples import bullet, eid, item, make_workspace, project, proposal, term

SCANNED = "scanned: 1 project, 3 evidence items in projects, 1 performance review, 03-profile/profile.json\n"


def ws_arg(workspace):
    return ["--workspace", str(workspace)]


def draft_from_fixture():
    saved = wsio.read_json(FIXTURE_WORKSPACE / "05-terms" / "candidates.json")
    return [{k: v for k, v in c.items() if k != "found_in"} for c in saved]


def same_as_fixture(workspace, rel):
    return (workspace / rel).read_bytes() == (FIXTURE_WORKSPACE / rel).read_bytes()


# The fixture -------------------------------------------------------------------------

def test_fixture_end_to_end(workspace, capsys):
    shutil.rmtree(workspace / "05-terms")
    shutil.rmtree(workspace / "07-sanitized")
    assert scan.main(ws_arg(workspace)) == 0
    out = capsys.readouterr().out
    assert out.startswith(SCANNED + " 1. pj_da2a2b53  Project Falcon checkout latency\n")
    assert "  name      'Redis'  1 place: ev_191cc8ce\n" in out
    assert "'Project Falcon'" not in out.split("likely terms")[1]  # decided already
    assert "3 likely terms decided in decisions/terms.json already\n" in out
    assert out.endswith("began 05-terms.tmp/: write 05-terms.tmp/candidates.json, then run scan.py --commit\n")
    wsio.write_json(workspace / "05-terms.tmp" / "candidates.json", draft_from_fixture())
    assert scan.main([*ws_arg(workspace), "--commit"]) == 0
    out = capsys.readouterr().out
    assert out.endswith("committed 05-terms: 2 candidates (0 to decide in the wizard)\n")
    assert same_as_fixture(workspace, "05-terms/candidates.json")
    meta = wsio.read_json(workspace / "05-terms" / "_stage.json")
    assert sorted(meta["inputs"]) == ["01-raw", "02-evidence/evidence.jsonl", "03-profile/profile.json",
                                      "04-projects/projects.json"]
    assert meta["extra"] == {"candidates": 2}

    assert apply.main(ws_arg(workspace)) == 0
    out = capsys.readouterr().out
    assert out.startswith("replaced 5 matches: 'Project Falcon' 3, 'Contoso Bank' 2\n"
                          "06-bullets/bullets.json: 1 of 4 bullets changed\n"
                          "  b_1: Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed "
                          "idempotency cache for real-time fraud-detection platform in Go\n"
                          "06-bullets/stories.md: 3 lines changed\n"
                          "  3: ## Real-time fraud-detection platform checkout latency\n")
    assert "03-profile/profile.json: 0 prose fields changed\n" in out
    assert "  name      'Redis'  2 places: b_1, stories.md:7\n" in out
    wsio.write_json(workspace / "07-sanitized.tmp" / "new-terms.json", [])
    assert apply.main([*ws_arg(workspace), "--commit"]) == 0
    out = capsys.readouterr().out
    assert out.endswith("committed 07-sanitized: 1 of 4 bullets changed, 5 replacements, 0 new terms\n")
    for name in ("bullets.json", "profile.json", "stories.md", "new-terms.json"):
        assert same_as_fixture(workspace, f"07-sanitized/{name}"), name
    meta = wsio.read_json(workspace / "07-sanitized" / "_stage.json")
    assert sorted(meta["inputs"]) == ["03-profile/profile.json", "05-terms/candidates.json",
                                      "06-bullets/bullets.json", "06-bullets/stories.md", "decisions/terms.json"]
    assert meta["extra"] == {"bullets": 4, "changed_bullets": 1, "replacements": 5, "new_terms": 0}

    assert validation.validate_workspace(workspace) == []
    status = stages.status(workspace)
    assert status["05-terms"] == status["07-sanitized"] == "fresh"
    targets, _ = gate.discover(workspace)
    assert gate.run(workspace, targets) == []

    # Deciding a term makes apply stale, and leaves the scan fresh.
    decisions = wsio.read_json(workspace / "decisions" / "terms.json")
    wsio.write_json(workspace / "decisions" / "terms.json", decisions + [term("Redis", None, "product")])
    status = stages.status(workspace)
    assert status["05-terms"] == "fresh" and status["07-sanitized"] == "stale"


# Must promises -----------------------------------------------------------------------

PROFILE = {
    "basics": {"name": "Jordan Rivera", "summary": "Led Falcon for Contoso."},
    "work": [{"name": "Contoso", "position": "Falcon Lead", "startDate": "2023-01",
              "highlights": ["Scaled Falcon 10x", "Hired two engineers"], "x-lines": {"first": 3, "last": 5}}],
    "projects": [{"name": "Falcon", "description": "Falcon is the Contoso checkout", "url": "https://falcon.dev",
                  "x-lines": {"first": 7, "last": 8}}],
}


def must_workspace(tmp_path):
    return make_workspace(
        tmp_path, profile=PROFILE, terms=[term("Falcon", "the checkout platform"), term("Contoso", None, "other")],
        bullets=[bullet(1, "Scaled Falcon 10x", "pj_0000000a")],
        stories="# Stories\n\n## Falcon\n\n- **Result:** Falcon scaled.\n")


def test_apply_writes_stories_and_changes_only_profile_prose(tmp_path, capsys):
    ws = must_workspace(tmp_path)
    assert apply.main(ws_arg(ws)) == 0
    out = capsys.readouterr().out
    assert "warning: /work/0/position 'Falcon Lead' holds the denied term 'Falcon'; set a replacement value " \
           "with /resume-builder:wizard\n" in out
    assert "warning: /projects/0/name 'Falcon' holds the denied term 'Falcon'" in out
    wsio.write_json(ws / "07-sanitized.tmp" / "new-terms.json", [])
    assert apply.main([*ws_arg(ws), "--commit"]) == 0
    assert (ws / "07-sanitized" / "stories.md").read_text(encoding="utf-8") == \
        "# Stories\n\n## The checkout platform\n\n- **Result:** The checkout platform scaled.\n"
    sanitized = wsio.read_json(ws / "07-sanitized" / "profile.json")
    assert sanitized["basics"]["summary"] == "Led the checkout platform for Contoso."
    assert sanitized["work"][0]["highlights"] == ["Scaled the checkout platform 10x", "Hired two engineers"]
    assert sanitized["projects"][0]["description"] == "The checkout platform is the Contoso checkout"
    for doc in (sanitized, PROFILE):  # every fact field and x-lines unchanged
        doc["basics"].pop("summary")
        doc["work"][0].pop("highlights")
        doc["projects"][0].pop("description")
    assert json.dumps(sanitized) == json.dumps(PROFILE)
    assert wsio.read_json(ws / "07-sanitized" / "bullets.json")[0]["text"] == "Scaled the checkout platform 10x"


def test_without_a_profile_the_sanitized_profile_is_empty(tmp_path, capsys):
    ws = make_workspace(tmp_path, terms=[], bullets=[bullet(1, "Did work")], stories="# Stories\n")
    assert apply.main(ws_arg(ws)) == 0
    assert wsio.read_json(ws / "07-sanitized.tmp" / "profile.json") == {}


# scan.py -----------------------------------------------------------------------------

def test_scan_needs_projects_evidence_and_valid_terms(tmp_path, capsys):
    ws = make_workspace(tmp_path, evidence=[item(1, "Fix")])
    assert scan.main(ws_arg(ws)) == 1
    assert "error: 04-projects/projects.json not found; run /resume-builder:analyze first" in capsys.readouterr().err
    assert not (ws / "05-terms.tmp").exists()
    ws = make_workspace(tmp_path / "b", projects=[project("pj_0000000a", [1])])
    assert scan.main(ws_arg(ws)) == 1
    assert "error: 02-evidence/evidence.jsonl not found; run /resume-builder:collect first" in capsys.readouterr().err
    ws = make_workspace(tmp_path / "c", projects=[project("pj_0000000a", [1])], evidence=[item(1, "Fix")],
                        terms=[term("Contoso", "a bank"), term("Contoso Bank", None)])
    assert scan.main(ws_arg(ws)) == 1
    err = capsys.readouterr().err
    assert "error: decisions/terms.json: allowed term 'Contoso Bank' contains denied term 'Contoso'" in err
    assert err.endswith("05-terms not begun\n")


def small_scan(tmp_path):
    evidence = [item(1, "Add Falcon cache", "For Fabrikam's checkout."),
                item(2, "2025 review", "Led Falcon", kind="perf_review", raw_ref="01-raw/reviews.jsonl:1#/items/0")]
    return make_workspace(tmp_path, projects=[project("pj_0000000a", [1], name="Falcon cache")], evidence=evidence,
                          raw={"reviews.jsonl": [{"items": [{"text": "Led Falcon for Nightjar Retail."}]}]})


def test_scan_prints_likely_terms_and_warns_about_raw_records(tmp_path, capsys):
    ws = small_scan(tmp_path)
    assert scan.main(ws_arg(ws)) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[:5] == [
        "scanned: 1 project, 1 evidence item in projects, 1 performance review",
        " 1. pj_0000000a  Falcon cache",
        "    Made exports reliable.",
        "    reasons: authored 3 of 4 pull requests",
        "likely terms not in decisions/terms.json: 5"]
    assert "  name      'Falcon'  2 places: ev_00000001, ev_00000002\n" in out
    assert "  name      'Nightjar Retail'  1 place: ev_00000002\n" in out
    (ws / "01-raw" / "reviews.jsonl").unlink()
    assert scan.main(ws_arg(ws)) == 0
    assert capsys.readouterr().out.startswith(
        f"warning: {eid(2)}: the raw record 01-raw/reviews.jsonl:1#/items/0 01-raw/reviews.jsonl not found; "
        "its excerpt stands in for the review's text\n")


def test_scan_commit_checks_the_candidates(tmp_path, capsys):
    ws = small_scan(tmp_path)
    assert scan.main([*ws_arg(ws), "--commit"]) == 1
    assert "error: 05-terms.tmp/ not found; run scan.py first" in capsys.readouterr().err
    assert scan.main(ws_arg(ws)) == 0
    assert scan.main([*ws_arg(ws), "--commit"]) == 1
    assert "05-terms.tmp/candidates.json: not found; write the candidates first" in capsys.readouterr().err
    wsio.write_json(ws / "05-terms.tmp" / "candidates.json",
                    [proposal("Falcon", "a Nightjar Retail cache"),
                     proposal("Nightjar Retail", "a retailer", "customer"), proposal("Tailspin")])
    assert scan.main([*ws_arg(ws), "--commit"]) == 1
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "05-terms.tmp/candidates.json: /2/term: 'Tailspin' appears in none of the scanned texts",
        "05-terms.tmp/candidates.json: /0/proposed_replacement: 'a Nightjar Retail cache' contains the term "
        "'Nightjar Retail' (/1)",
        "  fix: list each term once, spelled as the scanned text spells it, with a non-empty generalization that "
        "contains no candidate or denied term"]
    assert captured.err == "candidates check failed: 2 problems; 05-terms not committed\n"
    assert not (ws / "05-terms").exists()
    wsio.write_json(ws / "05-terms.tmp" / "candidates.json",
                    [proposal("Falcon", "a checkout cache"), proposal("Nightjar Retail", "a retailer", "customer")])
    assert scan.main([*ws_arg(ws), "--commit"]) == 0
    out = capsys.readouterr().out
    assert "  codename  'Falcon' -> 'a checkout cache'  (3 places: pj_0000000a, ev_00000001, ev_00000002; " \
           "to decide in the wizard)\n" in out
    assert out.endswith("committed 05-terms: 2 candidates (2 to decide in the wizard)\n")
    assert sorted(wsio.read_json(ws / "05-terms" / "_stage.json")["inputs"]) == [
        "01-raw", "02-evidence/evidence.jsonl", "04-projects/projects.json"]


def test_scan_begins_fresh(tmp_path, capsys):
    ws = small_scan(tmp_path)
    assert scan.main(ws_arg(ws)) == 0
    wsio.write_json(ws / "05-terms.tmp" / "candidates.json", [])
    assert scan.main(ws_arg(ws)) == 0
    assert not (ws / "05-terms.tmp" / "candidates.json").exists()


# apply.py ----------------------------------------------------------------------------

def test_apply_needs_bullets_and_stories(tmp_path, capsys):
    ws = make_workspace(tmp_path, stories="# Stories\n")
    assert apply.main(ws_arg(ws)) == 1
    assert "error: 06-bullets/bullets.json not found; run /resume-builder:write first" in capsys.readouterr().err
    ws = make_workspace(tmp_path / "b", bullets=[])
    assert apply.main(ws_arg(ws)) == 1
    assert "error: 06-bullets/stories.md not found; run /resume-builder:write first" in capsys.readouterr().err
    assert not (ws / "07-sanitized.tmp").exists()


@pytest.mark.parametrize("decisions, line", [
    ([term("Falcon", "a Contoso tool"), term("Contoso", "a bank", "customer")],
     "error: decisions/terms.json: the replacement for 'Falcon' ('a Contoso tool') contains the denied term "
     "'Contoso'"),
    ([term("Falcon", "a tool"), term("falcon", "a cache")],
     "error: decisions/terms.json: 'Falcon' and 'falcon' are the same term with different replacements "
     "('a tool' and 'a cache')"),
])
def test_apply_refuses_unusable_terms(tmp_path, capsys, decisions, line):
    ws = make_workspace(tmp_path, terms=decisions, bullets=[bullet(1, "Led Falcon")], stories="# Stories\n")
    assert apply.main(ws_arg(ws)) == 1
    err = capsys.readouterr().err
    assert line in err and "error: change these decisions with /resume-builder:wizard" in err
    assert not (ws / "07-sanitized.tmp").exists()


def test_apply_refuses_a_denied_term_it_could_not_replace(tmp_path, capsys):
    # Conjoining jamo compose only when the whole text is normalized, so find() misses them; the check does not.
    ws = make_workspace(tmp_path, terms=[term("가가", "a name")],
                        bullets=[bullet(1, "at 가가 today")], stories="# Stories\n")
    assert apply.main(ws_arg(ws)) == 1
    err = capsys.readouterr().err
    assert "error: b_1: contains denylisted term '가가' after replacing" in err
    assert "  fix: reword the text at its source" in err
    assert not (ws / "07-sanitized.tmp").exists()


def new_terms_workspace(tmp_path):
    return make_workspace(
        tmp_path, profile={"basics": {"name": "Jordan"}, "skills": [{"keywords": ["Falcon SDK"]}]},
        terms=[term("Falcon", "the platform"), term("Checkpoint", None, "other"),
               term("Check Point", "a vendor", "customer")],
        bullets=[bullet(1, "Built Falcon for Fabrikam"), bullet(2, "Wrote docs")],
        stories="# Stories\n\n## Falcon\n\nFabrikam asked for it.\n",
        candidates=[{"term": "Fabrikam", "kind": "customer", "proposed_replacement": "a retailer", "found_in": []}])


def test_apply_prints_warnings_notices_and_likely_new_terms(tmp_path, capsys):
    ws = new_terms_workspace(tmp_path)
    assert apply.main(ws_arg(ws)) == 0
    out = capsys.readouterr().out.splitlines()
    assert "warning: /skills/0/keywords/0 'Falcon SDK' holds the denied term 'Falcon'; a keyword cannot be " \
           "replaced, so resume-ats leaves it out" in out
    assert "notice: allowed term 'Checkpoint' looks like denied term 'Check Point'; confirm at checkpoint 4 " \
           "that it is a different word" in out
    assert "  must list  'Fabrikam' (a 05-terms/candidates.json candidate not yet decided)  2 places: b_1, " \
           "stories.md:5" in out


def test_apply_commit_checks_new_terms(tmp_path, capsys):
    ws = new_terms_workspace(tmp_path)
    assert apply.main([*ws_arg(ws), "--commit"]) == 1
    assert "error: 07-sanitized.tmp/ not found; run apply.py first" in capsys.readouterr().err
    assert apply.main(ws_arg(ws)) == 0
    assert apply.main([*ws_arg(ws), "--commit"]) == 1
    assert "07-sanitized.tmp/new-terms.json: not found; write the new terms first" in capsys.readouterr().err
    wsio.write_json(ws / "07-sanitized.tmp" / "new-terms.json", [])
    assert apply.main([*ws_arg(ws), "--commit"]) == 1
    captured = capsys.readouterr()
    assert captured.out.splitlines()[0] == ("'Fabrikam' from 05-terms/candidates.json is not decided and appears in "
                                            "b_1, stories.md:5; list it")
    assert captured.out.splitlines()[1].startswith("  fix: list each undecided term once")
    assert not (ws / "07-sanitized").exists()
    wsio.write_json(ws / "07-sanitized.tmp" / "new-terms.json", [proposal("Fabrikam", "a retailer", "customer")])
    assert apply.main([*ws_arg(ws), "--commit"]) == 0
    assert wsio.read_json(ws / "07-sanitized" / "new-terms.json") == [
        {"term": "Fabrikam", "kind": "customer", "proposed_replacement": "a retailer",
         "found_in": ["b_1", "stories.md:5"]}]
    assert wsio.read_json(ws / "07-sanitized" / "_stage.json")["extra"] == {
        "bullets": 2, "changed_bullets": 1, "replacements": 2, "new_terms": 1}


def test_apply_commit_refuses_inputs_changed_since_apply(tmp_path, capsys):
    ws = new_terms_workspace(tmp_path)
    assert apply.main(ws_arg(ws)) == 0
    wsio.write_json(ws / "07-sanitized.tmp" / "new-terms.json", [proposal("Fabrikam", "a retailer", "customer")])
    wsio.write_json(ws / "06-bullets" / "bullets.json", [bullet(1, "Built Falcon for Fabrikam and Nightjar")])
    assert apply.main([*ws_arg(ws), "--commit"]) == 1
    assert "error: 07-sanitized.tmp/bullets.json differs from what the inputs give now: the inputs changed since " \
           "apply.py ran; run apply.py again and review the new text" in capsys.readouterr().err
    assert not (ws / "07-sanitized").exists()
