import json

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


@pytest.mark.parametrize("text", [
    "for Conto\u00adso Bank",   # soft hyphen
    "for Conto\u034fso Bank",   # combining grapheme joiner
    "for Conto\u2061so Bank",   # function application
    "for Conto\u180eso Bank",   # Mongolian vowel separator
])
def test_invisible_characters_are_ignored(text):
    assert terms.scan_json({"a": text}, PATTERNS, "x") == ["x:/a: contains denylisted term 'Contoso Bank'"]


@pytest.mark.parametrize("sep", ["\u2011", "\u2010", "\u2013", "\u2014", "\u2212", ".", "/", "\u00b7"])
def test_separator_characters_are_accepted(sep):
    assert terms.scan_json({"a": f"Led Project{sep}Falcon"}, PATTERNS, "x") == [
        "x:/a: contains denylisted term 'Project Falcon'"
    ]


def test_plural_suffix_only_for_terms_of_five_or_more_characters():
    patterns = terms.compile_terms(["Falcon", "Rat", "Not", "Tim", "Go"])
    assert terms.scan_json({"a": "two Falcons"}, patterns, "x") == [
        "x:/a: contains denylisted term 'Falcon'"
    ]
    assert terms.scan_json({"a": "rates, notes, times and goes"}, patterns, "x") == []
    assert terms.scan_json({"a": "a Rat"}, patterns, "x") == ["x:/a: contains denylisted term 'Rat'"]


def test_allowed_term_containing_the_match_exempts_it():
    patterns = terms.compile_terms(["Check Point"], allowed=["checkpoint"])
    assert terms.scan_json({"a": "Added a checkpoint"}, patterns, "x") == []
    assert terms.scan_json({"a": "Worked at Check Point"}, patterns, "x") == [
        "x:/a: contains denylisted term 'Check Point'"
    ]
    assert terms.scan_json({"a": "a checkpoint at Check-Point"}, patterns, "x") == [
        "x:/a: contains denylisted term 'Check Point'"
    ]
    patterns = terms.compile_terms(["Air Flow"], allowed=["Airflow"])
    assert terms.scan_json({"a": "Migrated DAGs to Airflow"}, patterns, "x") == []
    patterns = terms.compile_terms(["Falcon"], allowed=["Falcons Club"])
    assert terms.scan_json({"a": "Member of the Falcons Club"}, patterns, "x") == []
    for text in ["Falcon", "Falcons"]:
        assert terms.scan_json({"a": text}, patterns, "x") == [
            "x:/a: contains denylisted term 'Falcon'"
        ], text


def test_allowed_terms_are_read_from_terms_json(workspace):
    path = workspace / "decisions" / "terms.json"
    entries = json.loads(path.read_text(encoding="utf-8"))
    entries += [{"term": "Check Point", "replacement": "a security vendor", "kind": "customer"},
                {"term": "checkpoint", "replacement": None, "kind": "other"}]
    path.write_text(json.dumps(entries), encoding="utf-8")
    (workspace / "06-bullets" / "stories.md").write_text(
        "Added a checkpoint.\nWorked at Check Point.\n", encoding="utf-8")
    assert terms.check_file(workspace, "06-bullets/stories.md") == [
        "06-bullets/stories.md:2: contains denylisted term 'Check Point'"
    ]


def test_scan_text_uses_splitlines_boundaries():
    assert terms.scan_text("a\r\nb\rProject\nFalcon", PATTERNS, "x") == [
        "x:3: contains denylisted term 'Project Falcon'"
    ]
    assert terms.scan_text("a\x0bb\x0cc\x1cd\x85e\u2028f\u2029Contoso Bank", PATTERNS, "x") == [
        "x:7: contains denylisted term 'Contoso Bank'"
    ]


@pytest.mark.parametrize("text", [
    "Conto\ufe0fso Bank",       # variation selector 16
    "Conto\ufe00so Bank",       # variation selector 1
    "Conto\U000E0100so Bank",   # variation selector 17
    "Conto\u180bso Bank",       # Mongolian free variation selector
    "Conto\u17b4so Bank",       # Khmer vowel inherent aq
    "Contoso\u3164Bank",        # Hangul filler
    "Contoso\u115fBank",        # Hangul choseong filler
    "Contoso\uffa0Bank",        # half-width Hangul filler
    "Conto\u1160so Bank",       # Hangul jungseong filler
    "Contoso\u2800Bank",        # Braille blank
])
def test_default_ignorable_characters_are_ignored(text):
    assert terms.scan_json({"a": text}, PATTERNS, "x") == ["x:/a: contains denylisted term 'Contoso Bank'"]


@pytest.mark.parametrize("sep", ["\\", "\u2215", "\u2044", "\u2027", "\u2043", "\u02d7", "\u30fb", "\u2022"])
def test_more_separator_lookalikes_are_accepted(sep):
    assert terms.scan_json({"a": f"Led Project{sep}Falcon"}, PATTERNS, "x") == [
        "x:/a: contains denylisted term 'Project Falcon'"
    ]


def _write_terms(workspace, entries):
    (workspace / "decisions" / "terms.json").write_text(json.dumps(entries), encoding="utf-8")


def _deny(term):
    return {"term": term, "replacement": "something else", "kind": "customer"}


def _allow(term):
    return {"term": term, "replacement": None, "kind": "other"}


@pytest.mark.parametrize("denied, allowed", [
    ("Contoso Bank", "Contoso Bank Group"),
    ("Contoso", "Contoso Bank"),
    ("Contoso Bank", "Contoso Bank"),
    ("Contoso Bank", "CONTOSO  BANK"),
    ("Contoso-Bank", "Contoso Bank Group"),
    ("Contoso Bank", "Contoso-Bank Group"),
])
def test_allowed_term_cannot_contain_a_denied_term(workspace, denied, allowed):
    _write_terms(workspace, [_deny(denied), _allow(allowed)])
    expected = [f"decisions/terms.json: allowed term '{allowed}' contains denied term '{denied}'; "
                "remove it or reword"]
    assert terms.check_file(workspace, "07-sanitized/bullets.json") == expected
    with pytest.raises(ValueError, match="contains denied term"):
        terms.load_denylist(workspace)


@pytest.mark.parametrize("denied, allowed", [
    ("Check Point", "checkpoint"),
    ("Air Flow", "Airflow"),
    ("Falcon", "Falcons Club"),
])
def test_allowed_terms_that_do_not_contain_a_denied_term_are_accepted(workspace, denied, allowed):
    _write_terms(workspace, [_deny(denied), _allow(allowed)])
    assert terms.check_file(workspace, "07-sanitized/bullets.json") == []


def _notice(allowed, denied):
    return (f"notice: allowed term '{allowed}' looks like denied term '{denied}'; "
            "confirm at checkpoint 4 that it is a different word")


@pytest.mark.parametrize("denied, allowed", [
    ("Contoso Bank", "ContosoBank"),
    ("Check Point", "checkpoint"),
    ("Contoso Bank", "contoso-banks"),
    ("Air Flow", "Airflow"),
])
def test_allowed_term_that_looks_like_a_denied_term_gives_a_notice(workspace, denied, allowed):
    entries = [_deny(denied), _allow(allowed)]
    assert terms.allowed_notices(entries) == [_notice(allowed, denied)]
    _write_terms(workspace, entries)
    assert terms.allowed_notices(workspace / "decisions" / "terms.json") == [_notice(allowed, denied)]
    assert terms.allowed_notices(workspace) == [_notice(allowed, denied)]
    assert terms.check_file(workspace, "07-sanitized/bullets.json") == []


def test_no_notice_for_unrelated_or_conflicting_allowed_terms(workspace):
    assert terms.allowed_notices([_deny("Contoso Bank"), _allow("Go"), _allow("Contoso")]) == []
    # Conflicts are reported as errors by allowed_conflicts, not as notices.
    assert terms.allowed_notices([_deny("Contoso"), _allow("Contoso Bank")]) == []
    assert terms.allowed_notices(workspace) == []


def test_notices_are_empty_when_terms_json_is_unusable(workspace):
    (workspace / "decisions" / "terms.json").write_text("[{", encoding="utf-8")
    assert terms.allowed_notices(workspace) == []


def test_check_file_chooses_format_ignoring_suffix_case(workspace):
    (workspace / "x.JSON").write_text('{"a": "Contos\\u006f Bank"}', encoding="utf-8")
    assert terms.check_file(workspace, "x.JSON") == [
        "x.JSON:/a: contains denylisted term 'Contoso Bank'"
    ]


@pytest.mark.parametrize("text", [
    "Conto\u2065so Bank",   # unassigned default-ignorable
    "Conto\ufff0so Bank",   # U+FFF0..FFF8 reserved default-ignorables
    "Conto\ufff8so Bank",
])
def test_more_default_ignorables_are_ignored(text):
    assert terms.scan_json({"a": text}, PATTERNS, "x") == ["x:/a: contains denylisted term 'Contoso Bank'"]


def test_bullet_operator_is_a_separator():
    assert terms.scan_json({"a": "Led Project\u2219Falcon"}, PATTERNS, "x") == [
        "x:/a: contains denylisted term 'Project Falcon'"
    ]


# Helpers for resume-sanitize and resume-wizard ------------------------------------

def test_key_names_the_same_term_whatever_the_spelling():
    assert terms.key("Contoso Bank") == terms.key("contoso-bank") == terms.key("CONTOSO  _Bank") == "contoso bank"
    assert terms.key("ContosoBank") == "contosobank"


def test_find_returns_spans_of_the_original_text():
    patterns = terms.compile_terms(["Project Falcon", "Contoso"])
    text = "Led Project​-Falcons for CONTOSO, then Contoso."
    spans = terms.find(text, patterns)
    assert [(text[s:e], term) for s, e, term in spans] == [
        ("Project​-Falcons", "Project Falcon"), ("CONTOSO", "Contoso"), ("Contoso", "Contoso")]


def test_find_keeps_the_leftmost_then_longest_match():
    patterns = terms.compile_terms(["Contoso", "Contoso Bank", "Bank of Contoso"])
    text = "Contoso Bank of Contoso"
    assert [(text[s:e], term) for s, e, term in terms.find(text, patterns)] == [
        ("Contoso Bank", "Contoso Bank"), ("Contoso", "Contoso")]


def test_find_respects_allowed_terms_like_the_check():
    patterns = terms.compile_terms(["Check Point"], ["checkpoint"])
    assert terms.find("Added a checkpoint", patterns) == []
    assert [term for _, _, term in terms.find("Worked at Check Point", patterns)] == ["Check Point"]


def test_find_maps_accents_and_compatibility_characters_back():
    patterns = terms.compile_terms(["Café Nova", "file"])
    text = "At Café Nova we ship a ﬁle."
    assert [text[s:e] for s, e, _ in terms.find(text, patterns)] == ["Café Nova", "ﬁle"]


def test_terms_in_lists_each_term_once_in_denylist_order():
    patterns = terms.compile_terms(["Falcon", "Contoso"])
    assert terms.terms_in("Contoso and Falcon and Contoso", patterns) == ["Falcon", "Contoso"]
    assert terms.terms_in("nothing here", patterns) == []


def test_read_entries_fails_closed(workspace):
    entries, errors = terms.read_entries(workspace)
    assert errors == [] and [e["term"] for e in entries] == ["Project Falcon", "Contoso Bank", "Go"]
    (workspace / "decisions" / "terms.json").unlink()
    assert terms.read_entries(workspace) == ([], ["decisions/terms.json: not found; run init_workspace.py"])
    (workspace / "decisions" / "terms.json").write_text(json.dumps(
        [{"term": "Contoso", "replacement": "a bank", "kind": "customer"},
         {"term": "Contoso Bank", "replacement": None, "kind": "customer"}]), encoding="utf-8")
    assert terms.read_entries(workspace)[1] == [
        "decisions/terms.json: allowed term 'Contoso Bank' contains denied term 'Contoso'; remove it or reword"]


def test_replacement_conflicts_name_each_denied_term_in_a_replacement():
    entries = [{"term": "Contoso", "replacement": "a bank", "kind": "customer"},
               {"term": "Falcon", "replacement": "a Contoso-grade falcon tool", "kind": "codename"},
               {"term": "checkpoint", "replacement": None, "kind": "other"},
               {"term": "Check Point", "replacement": "a checkpoint vendor", "kind": "customer"}]
    assert terms.replacement_conflicts(entries) == [
        "decisions/terms.json: the replacement for 'Falcon' ('a Contoso-grade falcon tool') contains the denied "
        "term 'Contoso'",
        "decisions/terms.json: the replacement for 'Falcon' ('a Contoso-grade falcon tool') contains the denied "
        "term 'Falcon'"]
