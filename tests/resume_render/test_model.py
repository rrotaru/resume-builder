import json

import pytest
from conftest import FIXTURE_WORKSPACE, REPO

from rrender import dates, model, txt

GENERAL = FIXTURE_WORKSPACE / "08-ats" / "general" / "resume.json"
SCHEMA = REPO / "skills" / "resume-core" / "schemas" / "tailored-resume.schema.json"


def general() -> dict:
    return json.loads(GENERAL.read_text(encoding="utf-8"))


@pytest.mark.parametrize("value, expected", [
    ("2023-01", "Jan 2023"), ("2023-12-15", "Dec 2023"), ("2019", "2019"),
    ("2023-13", "2023-13"), ("soon", "soon"),
])
def test_format_date(value, expected):
    assert dates.format_date(value) == expected


def test_date_range():
    assert dates.date_range("2023-01", None) == ("Jan 2023", "Present")
    assert dates.date_range("2023-01", None, ongoing=False) == ("Jan 2023",)
    assert dates.date_range("2019-06", "2022-12") == ("Jun 2019", "Dec 2022")
    assert dates.date_range("2022-12-01", "2022-12-20") == ("Dec 2022",)
    assert dates.date_range(None, "2019") == ("2019",)
    assert dates.date_range(None, None) == ()


def test_sections_come_in_fixed_order():
    resume = general()
    resume["basics"].update(summary="Backend engineer", **{"x-summary-sources": ["ev_191cc8ce"]})
    reordered = {key: resume[key] for key in reversed(list(resume))}
    doc = model.build(reordered)
    assert [s.heading for s in doc.sections] == [
        "Summary", "Experience", "Projects", "Skills", "Education", "Certifications"]


def test_summary_renders_only_with_sources():
    resume = general()
    resume["basics"]["summary"] = "Unsourced summary"
    assert "Unsourced summary" not in txt.render(model.build(resume))
    resume["basics"]["x-summary-sources"] = []
    assert "Unsourced summary" not in txt.render(model.build(resume))


def test_unknown_sections_and_fields_never_render():
    resume = general()
    resume["awards"] = [{"title": "Engineer of the year AWARDTEXT"}]
    resume["basics"]["objective"] = "OBJECTIVETEXT"
    resume["work"][0]["summary"] = "SUMMARYTEXT"
    resume["work"][0]["description"] = "DESCRIPTIONTEXT"
    resume["skills"][0]["level"] = "LEVELTEXT"
    resume["basics"]["location"]["address"] = "ADDRESSTEXT"
    resume["work"][0]["highlights"] = ["HIGHLIGHTTEXT"]  # render reads x-highlights only
    text = txt.render(model.build(resume))
    for marker in ["AWARDTEXT", "OBJECTIVETEXT", "SUMMARYTEXT", "DESCRIPTIONTEXT", "LEVELTEXT",
                   "ADDRESSTEXT", "HIGHLIGHTTEXT"]:
        assert marker not in text


def test_links_only_for_safe_schemes():
    resume = general()
    resume["basics"]["url"] = "javascript:alert(1)"
    resume["projects"][0]["url"] = "HTTPS://example.com/x"
    doc = model.build(resume)
    assert doc.contacts[0] == model.Link("jordan.rivera@example.com", "mailto:jordan.rivera@example.com")
    assert model.Link("javascript:alert(1)") in doc.contacts
    assert doc.sections[1].items[0].details == (model.Link("HTTPS://example.com/x", "HTTPS://example.com/x"),)


def test_profiles_without_url_show_network_and_username():
    resume = general()
    resume["basics"]["profiles"] = [{"network": "Mastodon", "username": "@jr"}]
    assert model.Link("Mastodon: @jr") in model.build(resume).contacts


def test_whitespace_and_control_characters_collapse():
    resume = general()
    resume["work"][0]["x-highlights"][0]["text"] = "  Cut\nlatency\t\x00 40%  "
    assert model.build(resume).sections[0].items[0].bullets[0] == "Cut latency 40%"


def test_name_is_required():
    resume = general()
    resume["basics"]["name"] = " "
    with pytest.raises(ValueError, match="basics.name is required"):
        model.build(resume)


def test_education_without_end_date_is_ongoing_but_certificates_never_are():
    resume = general()
    resume["education"][0] = {"institution": "State University", "startDate": "2024-09"}
    doc = model.build(resume)
    education = next(s for s in doc.sections if s.heading == "Education")
    certificates = next(s for s in doc.sections if s.heading == "Certifications")
    assert education.items[0].dates == ("Sep 2024", "Present")
    assert certificates.items[0].dates == ("May 2024",)


def test_skills_with_only_a_name_or_only_keywords():
    resume = general()
    resume["skills"] = [{"name": "Go"}, {"keywords": ["Redis", "Kafka"]}, {}]
    skills = next(s for s in model.build(resume).sections if s.heading == "Skills")
    assert skills.lines == (model.Line(None, "Go"), model.Line(None, "Redis, Kafka"))


def test_empty_sections_get_no_heading():
    resume = general()
    resume["projects"] = []
    resume.pop("certificates")
    assert [s.heading for s in model.build(resume).sections] == ["Experience", "Skills", "Education"]


def test_checked_texts():
    doc = model.build(general())
    texts = doc.checked_texts()
    assert texts[:2] == ["Jordan Rivera", "Experience"]
    assert "Mentored two new engineers through on-call onboarding" in texts
    assert texts.index("Projects") < texts.index(
        "Built ledger-lint, an open-source linter for double-entry ledger files with 300 GitHub stars")


@pytest.mark.parametrize("name", ["general", "job-fintech-sre"])
def test_txt_matches_saved_copy(name):
    rel = "general" if name == "general" else "jobs/fintech-sre"
    resume = json.loads((FIXTURE_WORKSPACE / "08-ats" / rel / "resume.json").read_text(encoding="utf-8"))
    saved = (REPO / "tests" / "fixtures" / "render" / f"{name}.txt").read_bytes().decode("utf-8")
    assert txt.render(model.build(resume)) == saved


def _property_objects(schema: dict) -> dict[str, dict]:
    defs = schema["$defs"]
    basics = schema["properties"]["basics"]["properties"]
    return {
        "": schema["properties"],
        "basics": basics,
        "basics.location": basics["location"]["properties"],
        "basics.profiles": basics["profiles"]["items"]["properties"],
        "work": defs["entry"]["properties"],
        "projects": defs["entry"]["properties"],
        "x-highlights": defs["entry"]["properties"]["x-highlights"]["items"]["properties"],
        "education": defs["education"]["properties"],
        "certificates": defs["certificate"]["properties"],
        "skills": defs["skill"]["properties"],
    }


def _all_property_dicts(node, found):
    if isinstance(node, dict):
        if isinstance(node.get("properties"), dict):
            found[id(node["properties"])] = node["properties"]
        for value in node.values():
            _all_property_dicts(value, found)
    elif isinstance(node, list):
        for value in node:
            _all_property_dicts(value, found)
    return found


def test_every_schema_field_has_a_rendering_decision():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    objects = _property_objects(schema)
    assert set(model.RENDERED) == set(model.NOT_RENDERED) == set(objects)
    for key, properties in objects.items():
        assert model.RENDERED[key] | model.NOT_RENDERED[key] == set(properties), key
        assert not model.RENDERED[key] & model.NOT_RENDERED[key], key
    covered = {id(p) for p in objects.values()}
    assert set(_all_property_dicts(schema, {})) == covered, "a schema object has no rendering decision"
