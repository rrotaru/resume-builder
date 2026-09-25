import pytest

from rcore import facts, sources, wsio

PROFILE = {
    "basics": {
        "name": "Jordan Rivera",
        "email": "j@example.com",
        "location": {"city": "Denver", "region": "CO"},
        "profiles": [{"network": "GitHub", "username": "jrivera", "url": "https://github.com/jrivera"}],
    },
    "work": [
        {"name": "Northwind Payments", "position": "Senior Software Engineer", "startDate": "2023-01"},
        {"name": "Tailspin Toys", "position": "Software Engineer", "startDate": "2019-06",
         "endDate": "2022-12-15", "location": "Remote"},
    ],
    "education": [{"institution": "State University", "studyType": "BS", "area": "Computer Science",
                   "endDate": "2019"}],
    "skills": [{"name": "Backend", "level": "Advanced", "keywords": ["Go", "Python", "Redis"]}],
}


def check(resume):
    return facts.check(resume, PROFILE, "r.json")


def test_copied_facts_pass():
    resume = {
        "basics": {"name": "Jordan Rivera", "email": "j@example.com", "location": {"city": "Denver"},
                   "profiles": [{"network": "GitHub", "url": "https://github.com/jrivera"}]},
        "work": [
            {"name": "Tailspin Toys", "position": "Software Engineer", "startDate": "2019-06",
             "endDate": "2022-12", "highlights": ["x"], "x-highlights": [{"bullet_id": "b_1", "text": "x"}]},
            {"name": "Northwind Payments", "startDate": "2023", "x-highlights": []},
        ],
        "education": [{"institution": "State University", "endDate": "2019"}],
        "skills": [{"name": "Backend", "keywords": ["Redis", "Go"]}],
    }
    assert check(resume) == []


@pytest.mark.parametrize("section, index, field, value, closest, has", [
    ("work", 0, "position", "CTO", 0, "Senior Software Engineer"),
    ("work", 1, "name", "Google", 1, "Tailspin Toys"),
    ("work", 1, "startDate", "2015-01", 1, "2019-06"),
    ("education", 0, "studyType", "PhD", 0, "BS"),
    ("skills", 0, "level", "Expert", 0, "Advanced"),
])
def test_changed_facts_fail(section, index, field, value, closest, has):
    resume = {section: [dict(PROFILE[section][index])]}
    resume[section][0][field] = value
    assert check(resume) == [
        f"r.json: /{section}/0: {field} {value!r} does not match the profile "
        f"(closest entry /{section}/{closest} has {has!r})"
    ]


def test_title_cannot_move_between_jobs():
    resume = {"work": [{"name": "Tailspin Toys", "position": "Senior Software Engineer",
                        "startDate": "2019-06", "endDate": "2022-12-15"}]}
    assert check(resume) == [
        "r.json: /work/0: position 'Senior Software Engineer' does not match the profile "
        "(closest entry /work/1 has 'Software Engineer')"
    ]


def test_field_missing_from_the_profile_fails():
    resume = {"work": [dict(PROFILE["work"][0], location="New York")]}
    assert check(resume) == [
        "r.json: /work/0: location 'New York' is not in the profile (closest entry /work/0 has no location)"
    ]


def test_keywords_must_come_from_the_matched_entry():
    resume = {"skills": [{"name": "Backend", "keywords": ["Go", "Kubernetes", "Kafka"]}]}
    assert check(resume) == [
        "r.json: /skills/0: keyword 'Kubernetes' is not in the profile (closest entry /skills/0)",
        "r.json: /skills/0: keyword 'Kafka' is not in the profile (closest entry /skills/0)",
    ]


def test_dates_may_be_shortened_but_not_lengthened():
    shortened = dict(PROFILE["work"][1], startDate="2019", endDate="2022-12")
    assert check({"work": [shortened]}) == []
    assert check({"work": [dict(PROFILE["work"][1], endDate="2022")]}) == []
    lengthened = dict(PROFILE["work"][0], startDate="2023-01-01")
    assert check({"work": [lengthened]}) == [
        "r.json: /work/0: startDate '2023-01-01' does not match the profile (closest entry /work/0 has '2023-01')"
    ]


def test_dropping_a_profile_date_fails():
    past_job = {k: v for k, v in PROFILE["work"][1].items() if k != "endDate"}
    assert check({"work": [past_job]}) == [
        "r.json: /work/0: endDate is missing (closest entry /work/1 has '2022-12-15')"
    ]


def test_adding_a_date_the_profile_lacks_fails():
    resume = {"work": [dict(PROFILE["work"][0], endDate="2025-01")]}
    assert check(resume) == [
        "r.json: /work/0: endDate '2025-01' is not in the profile (closest entry /work/0 has no endDate)"
    ]


def test_section_missing_from_the_profile_fails():
    resume = {"certificates": [{"name": "CKA"}], "projects": [{"name": "x", "x-highlights": []}]}
    assert check(resume) == [
        "r.json: /projects/0: the profile has no projects entries",
        "r.json: /certificates/0: the profile has no certificates entries",
    ]


def test_basics_facts():
    resume = {"basics": {"name": "J. Rivera", "phone": "555-0100", "location": {"city": "Boulder"},
                         "label": "anything", "summary": "s", "x-summary-sources": ["ev_1"]}}
    assert check(resume) == [
        "r.json: /basics/name: 'J. Rivera' does not match the profile ('Jordan Rivera')",
        "r.json: /basics/phone: '555-0100' is not in the profile",
        "r.json: /basics/location/city: 'Boulder' does not match the profile ('Denver')",
    ]


def test_profiles_items_match_like_entries():
    resume = {"basics": {"profiles": [{"network": "LinkedIn", "url": "https://github.com/jrivera"}]}}
    assert check(resume) == [
        "r.json: /basics/profiles/0: network 'LinkedIn' does not match the profile "
        "(closest entry /basics/profiles/0 has 'GitHub')"
    ]


def test_values_compare_with_their_types():
    profile = {"education": [{"institution": "U", "score": "4"}]}
    assert facts.check({"education": [{"institution": "U", "score": 4}]}, profile, "r") == [
        "r: /education/0: score 4 does not match the profile (closest entry /education/0 has '4')"
    ]
    assert facts.check({"basics": {"name": True}}, {"basics": {"name": 1}}, "r") == [
        "r: /basics/name: True does not match the profile (1)"
    ]


def test_malformed_input_is_reported_not_raised():
    assert check({"basics": "x", "work": ["Staff Engineer at Google"], "skills": "x"}) == [
        "r.json: /basics: must be an object",
        "r.json: /work/0: must be an object",
        "r.json: /skills: must be an array",
    ]
    assert facts.check({"work": [{"name": "A"}]}, {"work": ["junk", {"name": "A"}]}, "r") == []
    assert facts.check({"basics": {"location": "Denver"}}, {"basics": {"location": "Denver"}}, "r") == []


# Through the source check, on the fixture workspace.

JOB = "08-ats/jobs/fintech-sre/resume.json"


def _edit_job(workspace, change):
    resume = wsio.read_json(workspace / JOB)
    change(resume)
    wsio.write_json(workspace / JOB, resume)


def test_source_check_rejects_inflated_facts(workspace):
    def inflate(resume):
        resume["work"][0]["position"] = "CTO"
        resume["education"][0]["studyType"] = "PhD"
        resume["skills"][0]["keywords"].append("Kubernetes")
    _edit_job(workspace, inflate)
    assert sources.check_file(workspace, JOB) == [
        f"{JOB}: /work/0: position 'CTO' does not match the profile "
        "(closest entry /work/0 has 'Senior Software Engineer')",
        f"{JOB}: /education/0: studyType 'PhD' does not match the profile (closest entry /education/0 has 'BS')",
        f"{JOB}: /skills/0: keyword 'Kubernetes' is not in the profile (closest entry /skills/0)",
    ]


def test_wizard_answer_beats_the_imported_value(workspace):
    wizard = wsio.read_json(workspace / "decisions" / "profile.json")
    wizard["work"] = [{"position": "Staff Software Engineer"}]
    wsio.write_json(workspace / "decisions" / "profile.json", wizard)
    assert sources.check_file(workspace, JOB) == [
        f"{JOB}: /work/0: position 'Senior Software Engineer' does not match the profile "
        "(closest entry /work/0 has 'Staff Software Engineer')"
    ]
    _edit_job(workspace, lambda r: r["work"][0].update(position="Staff Software Engineer"))
    assert sources.check_file(workspace, JOB) == []


def test_profile_files_are_exempt(workspace):
    assert facts.check({"work": [{"position": "CTO"}]}, {}, "x")  # tailored would fail
    known = sources.load_known(workspace)
    assert sources.check_resume({"work": [{"position": "CTO", "x-highlights": []}]}, known,
                                "07-sanitized/profile.json") == []


def test_label_uses_the_wizard_label(workspace):
    wizard = wsio.read_json(workspace / "decisions" / "profile.json")
    wizard["basics"]["label"] = "Platform Engineer"
    wsio.write_json(workspace / "decisions" / "profile.json", wizard)
    _edit_job(workspace, lambda r: r["basics"].update(label="Platform Engineer"))
    assert sources.check_file(workspace, JOB) == []
    _edit_job(workspace, lambda r: r["basics"].update(label="Backend Engineer"))  # overridden import
    assert sources.check_file(workspace, JOB) == [f"{JOB}: {sources.LABEL_ERROR}"]


def test_schema_invalid_resume_is_a_problem_line(workspace):
    _edit_job(workspace, lambda r: r.update(work=["Staff Engineer at Google"]))
    assert sources.check_file(workspace, JOB) == [f"{JOB}: does not match its schema; run validate.py"]
    _edit_job(workspace, lambda r: r.update(work=[], awards=[{"title": "x"}]))
    assert sources.check_file(workspace, JOB) == [f"{JOB}: does not match its schema; run validate.py"]
