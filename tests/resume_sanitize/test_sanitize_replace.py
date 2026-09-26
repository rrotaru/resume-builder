"""Replacing denied terms (rsanitize.replace): matches, capitals, prose and facts."""
import json

from conftest import FIXTURE_WORKSPACE
from rcore import terms, wsio
from rsanitize.replace import prose, replace, sanitize_profile

FIXTURE_TERMS = {"Project Falcon": "real-time fraud-detection platform", "Contoso Bank": "a top-10 US bank"}


def run(text, replacements, allowed=()):
    return replace(text, terms.compile_terms(list(replacements), list(allowed)), replacements)


def test_the_fixture_bullet_and_stories():
    bullets = wsio.read_json(FIXTURE_WORKSPACE / "06-bullets" / "bullets.json")
    done = run(bullets[0]["text"], FIXTURE_TERMS)
    assert done.text == ("Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency "
                         "cache for real-time fraud-detection platform in Go")
    assert done.counts == {"Contoso Bank": 1, "Project Falcon": 1}
    stories = (FIXTURE_WORKSPACE / "06-bullets" / "stories.md").read_text(encoding="utf-8")
    done = run(stories, FIXTURE_TERMS)
    assert done.text == (FIXTURE_WORKSPACE / "07-sanitized" / "stories.md").read_text(encoding="utf-8")
    assert [done.text[s:s + 12] for s in done.starts] == ["Real-time fr", "a top-10 US ", "real-time fr"]


def test_capitals_at_a_sentence_start_only():
    reps = {"Contoso Bank": "a top-10 US bank"}
    assert run("Contoso Bank asked. Contoso Bank paid; for Contoso Bank", reps).text == \
        "A top-10 US bank asked. A top-10 US bank paid; for a top-10 US bank"
    assert run("- **Task:** Contoso Bank asked\n1. Contoso Bank\nfor\nContoso Bank", reps).text == \
        "- **Task:** A top-10 US bank asked\n1. A top-10 US bank\nfor\na top-10 US bank"


def test_a_replacement_is_never_lowercased():
    assert run("for Falcon", {"Falcon": "Nightjar-class platform"}).text == "for Nightjar-class platform"


def test_the_whole_match_is_replaced():
    reps = {"Project Falcon": "the platform"}
    assert run("ran Project​-Falcons, PROJECT_FALCON and ProjectFalcon", reps).text == \
        "ran the platform, the platform and the platform"


def test_allowed_terms_exempt_and_overlaps_take_the_longest():
    assert run("Added a checkpoint at Check Point", {"Check Point": "a vendor"}, ["checkpoint"]).text == \
        "Added a checkpoint at a vendor"
    reps = {"Contoso": "a bank group", "Contoso Bank": "a top-10 US bank"}
    done = run("Contoso Bank and Contoso", reps)
    assert done.text == "A top-10 US bank and a bank group"
    assert done.counts == {"Contoso Bank": 1, "Contoso": 1}


def test_prose_is_summary_description_highlights_and_reference():
    doc = {"basics": {"name": "Falcon", "summary": "s"},
           "work": [{"name": "n", "summary": "s", "description": "d", "highlights": ["h1", "h2"]}],
           "references": [{"name": "n", "reference": "r"}], "skills": [{"keywords": ["k"]}]}
    assert [pointer for pointer, _, _ in prose(doc)] == [
        "/basics/summary", "/work/0/summary", "/work/0/description", "/work/0/highlights/0",
        "/work/0/highlights/1", "/references/0/reference"]


def test_only_prose_changes_in_the_profile():
    doc = {"basics": {"name": "Falcon Rivera", "summary": "Led Falcon.", "url": "https://falcon.dev"},
           "projects": [{"name": "Falcon", "description": "Falcon is a linter", "startDate": "2021",
                         "x-lines": {"first": 1, "last": 2}}],
           "work": [{"name": "Falcon Inc", "highlights": ["Shipped Falcon", "Other"]}]}
    before = json.dumps(doc)
    result, changed, counts = sanitize_profile(doc, terms.compile_terms(["Falcon"]), {"Falcon": "the tool"})
    assert json.dumps(doc) == before  # the input is not modified
    assert changed == {"/basics/summary": "Led the tool.", "/projects/0/description": "The tool is a linter",
                       "/work/0/highlights/0": "Shipped the tool"}
    assert counts == {"Falcon": 3}
    assert result["basics"]["name"] == "Falcon Rivera" and result["basics"]["url"] == "https://falcon.dev"
    assert result["projects"][0]["name"] == "Falcon" and result["work"][0]["name"] == "Falcon Inc"
    assert result["projects"][0]["x-lines"] == {"first": 1, "last": 2}
    assert list(result["projects"][0]) == ["name", "description", "startDate", "x-lines"]
