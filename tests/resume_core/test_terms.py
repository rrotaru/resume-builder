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
    assert terms.scan_json({"a": "Falconry and Falcons"}, patterns, "x") == []
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


def test_no_terms_file_means_nothing_denied(tmp_path):
    assert terms.load_denylist(tmp_path) == []
