"""rats.draft: every fact from the effective profile, every placed bullet under its entry."""
import copy

from ats_samples import B1_SANITIZED, build, edit, fix_month
from conftest import FIXTURE_WORKSPACE
from rats import draft, report
from rcore import schema, wsio


def fixture_general():
    return wsio.read_json(FIXTURE_WORKSPACE / "08-ats" / "general" / "resume.json")


def test_the_fixture_draft_is_the_general_resume_before_rewording(workspace, monkeypatch):
    fix_month(monkeypatch)
    drafted = draft.build(build(workspace))
    expected = fixture_general()
    for key in ("highlights",):
        expected["work"][0][key][0] = B1_SANITIZED
    expected["work"][0]["x-highlights"][0]["text"] = B1_SANITIZED
    assert drafted == expected
    assert list(drafted["education"][0]) == ["institution", "area", "studyType", "endDate"]  # schema order
    assert list(drafted["certificates"][0]) == ["name", "date", "issuer"]
    assert schema.validate(drafted, schema.load_schema("tailored-resume")) == []
    assert "x-sources" not in str(drafted) and "x-lines" not in str(drafted)


def test_bullets_come_from_07_sanitized_not_06_bullets(workspace):
    edit(workspace / "06-bullets" / "bullets.json", lambda b: b[1].update(text="Unsanitized text"))
    drafted = draft.build(build(workspace))
    assert drafted["work"][0]["x-highlights"][0]["text"] == B1_SANITIZED
    assert drafted["work"][0]["x-highlights"][1]["text"] == "Mentored two new engineers through on-call onboarding"


def test_the_label_is_the_target_role_else_the_profiles(workspace):
    edit(workspace / "config.json", lambda c: c.update(target_role=""))
    assert draft.build(build(workspace))["basics"]["label"] == "Backend Engineer"
    edit(workspace / "03-profile" / "profile.json", lambda p: p["basics"].pop("label"))
    assert "label" not in draft.build(build(workspace))["basics"]


def test_facts_come_from_the_effective_profile_and_only_shown_location_fields(workspace):
    edit(workspace / "decisions" / "profile.json", lambda p: p["basics"].update(
        phone="555-0100", location={"address": "1 Main St", "postalCode": "80202", "city": "Denver",
                                    "countryCode": "US", "region": "CO"}))
    edit(workspace / "03-profile" / "profile.json", lambda p: p["work"][1].update(
        location={"city": "Austin"}, description="Toys", summary="Built toys"))
    basics = draft.build(build(workspace))["basics"]
    assert basics["phone"] == "555-0100"
    assert basics["location"] == {"city": "Denver", "countryCode": "US", "region": "CO"}
    job = draft.build(build(workspace))["work"][1]
    assert "location" not in job  # an object does not fit the schema: left out, and the fact check names it
    assert "description" not in job and "summary" not in job


def test_each_bullet_goes_under_its_place(workspace):
    def change(bullets):
        bullets.append({"id": "b_5", "project_id": None, "work_ref": None, "text": "Wrote the ledger-lint docs",
                        "form": "xyz", "sources": ["wizard:/basics/email", "resume:/projects/0/name"]})
        bullets.append({"id": "b_6", "project_id": None, "work_ref": 1, "text": "Shipped toys",
                        "form": "xyz", "sources": ["resume:/work/1/name"]})
    edit(workspace / "07-sanitized" / "bullets.json", change)
    drafted = draft.build(build(workspace))
    assert [h["bullet_id"] for h in drafted["work"][0]["x-highlights"]] == ["b_1", "b_2"]
    assert [h["bullet_id"] for h in drafted["work"][1]["x-highlights"]] == ["b_3", "b_6"]
    assert [h["bullet_id"] for h in drafted["projects"][0]["x-highlights"]] == ["b_4", "b_5"]
    for entry in drafted["work"] + drafted["projects"]:
        assert entry["highlights"] == [h["text"] for h in entry["x-highlights"]]


def test_a_bullet_with_no_place_is_left_out_and_reported(workspace):
    def change(bullets):
        bullets[0]["work_ref"] = None  # its project falls in no job
        bullets[1]["work_ref"] = 7  # past the end of the profile's work
    edit(workspace / "07-sanitized" / "bullets.json", change)
    found = build(workspace)
    drafted = draft.build(found)
    assert [h["bullet_id"] for h in drafted["work"][0]["x-highlights"]] == []
    assert report.homeless_warnings(found) == [
        "b_1 (pj_da2a2b53 'Project Falcon checkout latency') has no place: no job of the profile overlaps its "
        "project; it is left out until the job is added with /resume-builder:wizard",
        "b_2 has no place: /work/7 is not in the profile (07-sanitized is out of date); it is left out"]


def test_a_keyword_holding_a_denied_term_is_left_out(workspace):
    edit(workspace / "decisions" / "terms.json", lambda t: t.append(
        {"term": "Falcon SDK", "replacement": "an internal SDK", "kind": "product"}))
    edit(workspace / "decisions" / "profile.json", lambda p: p.update(
        skills=[{"keywords": ["Falcon SDK"]}, {"name": "Internal", "keywords": ["Falcon-SDK"]}]))
    found = build(workspace)
    drafted = draft.build(found)
    assert drafted["skills"] == [{"name": "Backend", "keywords": ["Go", "Python", "Redis", "PostgreSQL"]},
                                 {"name": "Internal"}]
    assert report.withheld_notes(found) == [
        "/skills/0/keywords/4 'Falcon SDK' holds the denied term 'Falcon SDK'; a keyword cannot be replaced, so it "
        "is left out",
        "/skills/1/keywords/0 'Falcon-SDK' holds the denied term 'Falcon SDK'; a keyword cannot be replaced, so it "
        "is left out"]


def test_the_summary_is_the_sanitized_profiles(workspace):
    edit(workspace / "03-profile" / "profile.json", lambda p: p["basics"].update(
        summary="Backend engineer who sped up\ncheckout for Contoso Bank."))
    sanitized = copy.deepcopy(wsio.read_json(workspace / "07-sanitized" / "profile.json"))
    sanitized["basics"]["summary"] = "Backend engineer who sped up\ncheckout for a top-10 US bank."
    wsio.write_json(workspace / "07-sanitized" / "profile.json", sanitized)
    basics = draft.build(build(workspace))["basics"]
    assert basics["summary"] == "Backend engineer who sped up checkout for a top-10 US bank."
    assert basics["x-summary-sources"] == ["resume:/basics/summary"]
    assert list(basics)[-2:] == ["summary", "x-summary-sources"]


def test_no_summary_without_an_imported_one(workspace):
    edit(workspace / "07-sanitized" / "profile.json", lambda p: p["basics"].update(summary="Invented"))
    assert "summary" not in draft.build(build(workspace))["basics"]


def test_normalize_orders_keys_and_sets_highlights():
    resume = {"skills": [{"keywords": ["Go"], "name": "Backend"}],
              "work": [{"x-highlights": [{"sources": ["ev_191cc8ce"], "text": "New", "bullet_id": "b_1"}],
                        "highlights": ["Old"], "name": "Northwind Payments"}],
              "basics": {"name": "Jordan Rivera"}}
    normalized = draft.normalize(resume)
    assert list(normalized) == ["basics", "work", "skills"]
    assert normalized["work"][0] == {"name": "Northwind Payments", "highlights": ["New"],
                                     "x-highlights": [{"bullet_id": "b_1", "text": "New",
                                                       "sources": ["ev_191cc8ce"]}]}
    assert list(normalized["skills"][0]) == ["name", "keywords"]
