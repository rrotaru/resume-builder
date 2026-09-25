from rcore import profile, wsio


def test_objects_merge_key_by_key():
    imported = {"basics": {"name": "Jordan Rivera", "label": "Backend Engineer"}}
    wizard = {"basics": {"label": "Senior Backend Engineer", "email": "j@example.com"}}
    assert profile.overlay(imported, wizard) == {
        "basics": {"name": "Jordan Rivera", "label": "Senior Backend Engineer", "email": "j@example.com"}
    }


def test_object_arrays_merge_by_index_and_empty_objects_keep_items():
    imported = {"work": [{"name": "A", "position": "Engineer"}, {"name": "B", "startDate": "2019-06"}]}
    wizard = {"work": [{}, {"endDate": "2022-12"}, {"name": "C"}]}
    assert profile.overlay(imported, wizard) == {"work": [
        {"name": "A", "position": "Engineer"},
        {"name": "B", "startDate": "2019-06", "endDate": "2022-12"},
        {"name": "C"},
    ]}


def test_shorter_wizard_array_leaves_the_rest_unchanged():
    imported = {"work": [{"name": "A"}, {"name": "B"}]}
    assert profile.overlay(imported, {"work": [{"position": "Lead"}]}) == {
        "work": [{"name": "A", "position": "Lead"}, {"name": "B"}]
    }


def test_other_arrays_combine_without_duplicates():
    imported = {"skills": [{"keywords": ["Go", "Python"]}]}
    wizard = {"skills": [{"keywords": ["Kafka", "Go", "Kafka"]}]}
    assert profile.overlay(imported, wizard) == {"skills": [{"keywords": ["Go", "Python", "Kafka"]}]}


def test_wizard_value_replaces_anything_else():
    assert profile.overlay({"a": "x"}, {"a": "y"}) == {"a": "y"}
    assert profile.overlay({"a": ["x"]}, {"a": "y"}) == {"a": "y"}
    assert profile.overlay({"a": {"b": 1}}, {"a": None}) == {"a": None}


def test_overlay_does_not_share_structure_with_its_inputs():
    imported = {"work": [{"name": "A"}]}
    merged = profile.overlay(imported, {})
    merged["work"][0]["name"] = "changed"
    assert imported == {"work": [{"name": "A"}]}


def test_effective_profile_of_the_fixture(workspace):
    effective = profile.effective_profile(workspace)
    assert effective["basics"]["name"] == "Jordan Rivera"
    assert effective["basics"]["email"] == "jordan.rivera@example.com"
    assert effective["basics"]["location"] == {"city": "Denver", "region": "CO"}


def test_missing_or_unreadable_files_count_as_empty(workspace, tmp_path):
    assert profile.effective_profile(tmp_path) == {}
    (workspace / "decisions" / "profile.json").write_text("{", encoding="utf-8")
    assert profile.effective_profile(workspace) == wsio.read_json(workspace / "03-profile" / "profile.json")
    wsio.write_json(workspace / "decisions" / "profile.json", ["not", "an", "object"])
    assert profile.effective_profile(workspace) == wsio.read_json(workspace / "03-profile" / "profile.json")
