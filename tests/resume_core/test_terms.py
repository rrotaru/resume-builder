import pytest

from rcore import terms


def test_load_denylist_excludes_allowed_terms(workspace):
    assert terms.load_denylist(workspace) == ["Project Falcon", "Contoso Bank"]


def test_unsanitized_bullets_fail_and_outputs_pass(workspace):
    assert terms.check_file(workspace, "06-bullets/bullets.json") == [
        "06-bullets/bullets.json:/0/text: contains denylisted term 'Project Falcon'",
        "06-bullets/bullets.json:/0/text: contains denylisted term 'Contoso Bank'",
    ]
    for rel in ["07-sanitized/bullets.json", "08-ats/general/resume.json",
                "08-ats/jobs/fintech-sre/resume.json"]:
        assert terms.check_file(workspace, rel) == []


def test_matching_is_case_insensitive_whole_word():
    patterns = terms.compile_terms(["Falcon", "C++"])
    assert terms.scan_json({"a": "the FALCON service"}, patterns, "x") == [
        "x:/a: contains denylisted term 'Falcon'"
    ]
    assert terms.scan_json({"a": "Falconry and Falconer"}, patterns, "x") == []
    assert terms.scan_json({"a": "two Falcons"}, patterns, "x") == [
        "x:/a: contains denylisted term 'Falcon'"
    ]
    assert terms.scan_json({"a": "wrote C++ tooling"}, patterns, "x") == [
        "x:/a: contains denylisted term 'C++'"
    ]


def test_keys_are_not_scanned():
    patterns = terms.compile_terms(["secret"])
    assert terms.scan_json({"secret": "fine"}, patterns, "x") == []


def test_text_files_report_line_numbers(workspace):
    (workspace / "06-bullets" / "stories.md").write_text(
        "# Stories\n\nSituation: Contoso Bank checkout was slow.\n", encoding="utf-8"
    )
    assert terms.check_file(workspace, "06-bullets/stories.md") == [
        "06-bullets/stories.md:3: contains denylisted term 'Contoso Bank'"
    ]


def test_jsonl_files_are_scanned(workspace):
    errors = terms.check_file(workspace, "02-evidence/evidence.jsonl")
    assert "02-evidence/evidence.jsonl:/0/title: contains denylisted term 'Project Falcon'" in errors


def test_missing_terms_file_fails_closed(tmp_path):
    (tmp_path / "notes.md").write_text("nothing secret", encoding="utf-8")
    assert terms.check_file(tmp_path, "notes.md") == [
        "decisions/terms.json: not found; run init_workspace.py"
    ]
    with pytest.raises(ValueError, match="not found; run init_workspace.py"):
        terms.load_denylist(tmp_path)


def test_invalid_terms_file_fails_closed(workspace):
    (workspace / "decisions" / "terms.json").write_text("[{", encoding="utf-8")
    errors = terms.check_file(workspace, "07-sanitized/bullets.json")
    assert len(errors) == 1 and errors[0].startswith("decisions/terms.json: invalid JSON")


PATTERNS = terms.compile_terms(["Project Falcon", "Contoso Bank"])


@pytest.mark.parametrize("text, term", [
    ("Led Project\u00a0Falcon", "Project Falcon"),      # no-break space
    ("Led Project  Falcon", "Project Falcon"),           # double space
    ("Led Project-Falcon", "Project Falcon"),            # hyphen
    ("Led ProjectFalcon", "Project Falcon"),             # joined
    ("Led project_falcon", "Project Falcon"),            # underscore
    ("for Conto\u200bso Bank", "Contoso Bank"),          # zero-width space inside
    ("for \uff23\uff2f\uff2e\uff34\uff2f\uff33\uff2f Bank", "Contoso Bank"),  # full-width
    ("for Contoso Banks", "Contoso Bank"),               # plural
])
def test_disguised_terms_are_caught(text, term):
    assert terms.scan_json({"a": text}, PATTERNS, "x") == [f"x:/a: contains denylisted term {term!r}"]


def test_term_split_across_lines_of_text_file(workspace):
    (workspace / "06-bullets" / "stories.md").write_text(
        "# Stories\n\nWorked on Project\nFalcon for a year.\n", encoding="utf-8"
    )
    assert terms.check_file(workspace, "06-bullets/stories.md") == [
        "06-bullets/stories.md:3: contains denylisted term 'Project Falcon'"
    ]


def test_text_file_reports_each_matching_line(workspace):
    (workspace / "06-bullets" / "stories.md").write_text(
        "Contoso Bank\nok\nProject-Falcon and ProjectFalcon\n", encoding="utf-8"
    )
    assert terms.check_file(workspace, "06-bullets/stories.md") == [
        "06-bullets/stories.md:1: contains denylisted term 'Contoso Bank'",
        "06-bullets/stories.md:3: contains denylisted term 'Project Falcon'",
    ]


def test_unreadable_scanned_files_are_reported(workspace):
    assert terms.check_file(workspace, "06-bullets/nope.md") == ["06-bullets/nope.md: not found"]
    (workspace / "06-bullets" / "bad.json").write_text("{oops", encoding="utf-8")
    [error] = terms.check_file(workspace, "06-bullets/bad.json")
    assert error.startswith("06-bullets/bad.json: invalid JSON")
    (workspace / "06-bullets" / "bin.md").write_bytes(b"\xff\xfe\x00bad")
    assert terms.check_file(workspace, "06-bullets/bin.md") == ["06-bullets/bin.md: not UTF-8 text"]
