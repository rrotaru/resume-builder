"""Profile answers (rwizard.profile) and the wizard's bookkeeping (rwizard.state)."""
import pytest

from rcore.profile import overlay
from rwizard import profile as rp
from rwizard.common import WizardError
from rwizard.state import State, entry_of, imported_identity

from wizard_samples import CONTOSO, NORTHWIND, TAILSPIN

IMPORTED = {"basics": {"name": "Jordan"}, "work": [dict(NORTHWIND), dict(TAILSPIN)]}


def set_answer(wizard, pointer, value, imported=IMPORTED):
    target = rp.target(pointer, overlay(imported, wizard))
    rp.set_value(wizard, target, rp.check_value(target.field, value, target.pointer))
    return target


def test_answers_follow_the_overlay_rules():
    """Must: arrays of objects merge by index and {} keeps an imported entry."""
    wizard = {}
    set_answer(wizard, "/work/1/endDate", "2022-11")
    assert wizard == {"work": [{}, {"endDate": "2022-11"}]}
    effective = overlay(IMPORTED, wizard)
    assert effective["work"][0] == NORTHWIND
    assert effective["work"][1] == dict(TAILSPIN, endDate="2022-11")
    set_answer(wizard, "/basics/location/city", "Denver")
    set_answer(wizard, "/basics/profiles/-/network", "GitHub")
    assert wizard == {"work": [{}, {"endDate": "2022-11"}], "basics": {"location": {"city": "Denver"},
                                                                        "profiles": [{"network": "GitHub"}]}}


def test_a_new_entry_is_one_past_the_end():
    wizard = {}
    target = set_answer(wizard, "/work/-/name", "Contoso")
    assert (target.pointer, target.entry, target.new_entry) == ("/work/2/name", "/work/2", True)
    assert wizard == {"work": [{}, {}, {"name": "Contoso"}]}
    assert overlay(IMPORTED, wizard)["work"][2] == {"name": "Contoso"}
    with pytest.raises(WizardError, match=r"/work/4/name: /work has 3 entries; use an index up to 3 "
                                          r"\(3 adds an entry\), or -"):
        rp.target("/work/4/name", overlay(IMPORTED, wizard))


@pytest.mark.parametrize("pointer, message", [
    ("/work/1/summary", "/work/1/summary: summary is prose; the wizard records facts only"),
    ("/work/1/highlights", "/work/1/highlights: highlights is prose; the wizard records facts only"),
    ("/skills/0/keywords", "/skills/0/keywords: keywords is a list; add items with answer.py add"),
    ("/work/1/company", "/work/1/company: not a work field (allowed: name, position, url, location, description, "
                        "startDate, endDate, summary, highlights)"),
    ("/meta/version", "/meta/version: not a JSON Resume section (allowed: basics"),
    ("/basics/summary", "/basics/summary: not a basics field the wizard records"),
    ("/work/1", "/work/1: name a field of one entry, such as /work/0/name"),
    ("/work/01/name", "/work/01/name: '01' is not an entry number"),
    ("work/1/name", "'work/1/name' is not a JSON Pointer"),
])
def test_pointers_the_wizard_refuses(pointer, message):
    with pytest.raises(WizardError) as caught:
        rp.target(pointer, IMPORTED)
    assert caught.value.lines[0].startswith(message)


def test_add_takes_list_fields_only():
    target = rp.target("/skills/-/keywords", {}, for_add=True)
    wizard = {}
    rp.add_item(wizard, target, "Kafka")
    rp.add_item(wizard, target, "Kafka")
    assert wizard == {"skills": [{"keywords": ["Kafka"]}]}
    with pytest.raises(WizardError, match="name is not a list; set it with answer.py profile"):
        rp.target("/skills/0/name", {}, for_add=True)
    with pytest.raises(WizardError, match="not a basics field"):
        rp.target("/basics/email", {}, for_add=True)


@pytest.mark.parametrize("field, value, ok", [("endDate", "2022-12", "2022-12"), ("endDate", "Dec 2022", None),
                                              ("date", "2022-02-30", None), ("name", "  Contoso  ", "Contoso"),
                                              ("name", "   ", None)])
def test_values_are_trimmed_and_dates_checked(field, value, ok):
    if ok is None:
        with pytest.raises(WizardError):
            rp.check_value(field, value, f"/work/0/{field}")
    else:
        assert rp.check_value(field, value, f"/work/0/{field}") == ok


def test_unset_tidies_the_file():
    wizard = {"basics": {"email": "e", "location": {"city": "Denver"}},
              "work": [{"location": "Remote"}, {"endDate": "2022-12"}], "skills": [{"keywords": ["Kafka"]}]}
    rp.unset(wizard, "/work/1/endDate")
    rp.unset(wizard, "/basics/location/city")
    rp.unset(wizard, "/skills/0/keywords")
    assert wizard == {"basics": {"email": "e"}, "work": [{"location": "Remote"}]}
    rp.unset(wizard, "/work/0")
    assert wizard == {"basics": {"email": "e"}}
    with pytest.raises(WizardError, match="decisions/profile.json has no answer at /work/0"):
        rp.unset(wizard, "/work/0")


def test_a_middle_entry_becomes_a_placeholder():
    wizard = {"work": [{"location": "Remote"}, {"endDate": "2022-12"}]}
    rp.unset(wizard, "/work/0")
    assert wizard == {"work": [{}, {"endDate": "2022-12"}]}


def test_anchors_record_the_entry_an_answer_was_given_for():
    state, before, wizard = State(), {}, {}
    set_answer(wizard, "/work/1/endDate", "2022-11")
    set_answer(wizard, "/work/-/name", "Contoso")
    rp.anchor_new_entries(before, wizard, IMPORTED, state)
    assert state.anchors == {"/work/1": {"position": "Software Engineer", "name": "Tailspin Toys"}, "/work/2": None}
    rp.unset(wizard, "/work/2")
    rp.anchor_new_entries({"work": [{}, {"endDate": "2022-11"}, {"name": "Contoso"}]}, wizard, IMPORTED, state)
    assert list(state.anchors) == ["/work/1"]
    assert state.to_json()["anchors"] == [{"entry": "/work/1", "answered_for": {"position": "Software Engineer",
                                                                                "name": "Tailspin Toys"}}]


def test_moved_answers_after_a_re_import():
    state = State({"/work/1": {"position": "Software Engineer", "name": "Tailspin Toys"}, "/certificates/0": None})
    wizard = {"work": [{}, {"endDate": "2022-11"}], "certificates": [{"name": "CKA"}], "education": [{"area": "CS"}]}
    assert rp.moved_answers({"work": [NORTHWIND, TAILSPIN]}, wizard, state) == [
        rp.Moved("/education/0", "education", {"area": "CS"}, False, None, None, None)]
    reimported = {"work": [NORTHWIND, CONTOSO, TAILSPIN], "certificates": [{"name": "AWS", "issuer": "Amazon"}]}
    moved = rp.moved_answers(reimported, wizard, state)
    assert [(m.entry, m.suggest) for m in moved] == [("/work/1", 2), ("/certificates/0", 1), ("/education/0", None)]
    assert moved[0].describe() == ('{"endDate": "2022-11"} was answered for \'Software Engineer, Tailspin Toys\'; '
                                   "/work/1 is now 'Engineer, Contoso'")
    assert moved[1].describe() == ('{"name": "CKA"} added a certificates entry; /certificates/0 is now the imported '
                                   "'AWS, Amazon', which it merges into")
    assert moved[2].describe() == ('{"area": "CS"} has no record of the entry it was answered for; it adds an '
                                   "education entry")
    gone = rp.moved_answers({"work": [NORTHWIND]}, {"work": [{}, {"endDate": "2022-11"}]}, state)
    assert gone[0].describe().endswith("there is no imported /work/1 now, so it adds a new entry")


def test_move_the_answer_to_its_entry():
    wizard = {"work": [{}, {"endDate": "2022-11"}]}
    effective = overlay({"work": [NORTHWIND, CONTOSO, TAILSPIN]}, wizard)
    with pytest.raises(WizardError, match="already has an answer at /work/1"):
        rp.move({"work": [{"x": "1"}, {"y": "2"}]}, "/work/0", "/work/1", effective)
    with pytest.raises(WizardError, match="different lists"):
        rp.move(wizard, "/work/1", "/education/0", effective)
    with pytest.raises(WizardError, match="use an index up to 3"):
        rp.move(wizard, "/work/1", "/work/5", effective)
    rp.move(wizard, "/work/1", "/work/2", effective)
    assert wizard == {"work": [{}, {}, {"endDate": "2022-11"}]}
    with pytest.raises(WizardError, match="has no answer at /work/1"):
        rp.move(wizard, "/work/1", "/work/0", effective)


def test_skips_inside_an_entry_lapse_when_the_entry_changes():
    state = State()
    state.skip("profile:/work/1/startDate", {"work": [NORTHWIND, TAILSPIN]})
    state.skip("profile:/basics/phone", {})
    assert state.skipped == [{"question": "profile:/work/1/startDate",
                              "answered_for": {"position": "Software Engineer", "name": "Tailspin Toys"}},
                             {"question": "profile:/basics/phone"}]
    assert state.is_skipped("profile:/work/1/startDate", {"work": [NORTHWIND, TAILSPIN]})
    assert not state.is_skipped("profile:/work/1/startDate", {"work": [NORTHWIND, CONTOSO]})
    assert state.is_skipped("profile:/basics/phone", {"basics": {}})
    assert state.unskip("profile:/basics/phone") and not state.unskip("profile:/basics/phone")


def test_entries_and_identities():
    assert entry_of("/work/1/endDate") == "/work/1"
    assert entry_of("/basics/profiles/0/url") == "/basics/profiles/0"
    assert entry_of("/basics/email") is None and entry_of("/education") is None
    assert imported_identity({"basics": {"profiles": [{"network": "GitHub", "url": "u"}]}},
                             "/basics/profiles/0") == {"network": "GitHub"}
    assert imported_identity({}, "/work/3") is None
