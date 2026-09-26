"""Checks of candidates.json and new-terms.json (rsanitize.proposals)."""
from rsanitize.proposals import check, must_list
from rsanitize.texts import Text

from sanitize_samples import proposal, term

LABEL = "05-terms.tmp/candidates.json"
TEXTS = [Text("pj_0000000a", "Falcon cache for Contoso Bank"), Text("ev_00000001", "Contoso Bank asked"),
         Text("resume:/projects/0/name", "Falcon")]


def test_valid_candidates_get_found_in():
    checked = check([proposal("Contoso Bank", "a top-10 US bank", "customer"), proposal("Falcon", "a cache")],
                    LABEL, TEXTS, [])
    assert checked.problems == [] and checked.notes == []
    assert checked.records == [
        {"term": "Contoso Bank", "kind": "customer", "proposed_replacement": "a top-10 US bank",
         "found_in": ["pj_0000000a", "ev_00000001"]},
        {"term": "Falcon", "kind": "codename", "proposed_replacement": "a cache",
         "found_in": ["pj_0000000a", "resume:/projects/0/name"]}]


def test_a_decided_candidate_is_a_note():
    checked = check([proposal("Falcon")], LABEL, TEXTS, [term("falcon", None)])
    assert checked.problems == []
    assert checked.notes == ["/0 'Falcon' is decided in decisions/terms.json already; the wizard will not ask about it"]


def test_each_problem_has_its_line():
    draft = [proposal("Nightjar"), proposal("Contoso Bank", "a bank"), proposal("contoso-bank", "a bank"),
             proposal("Falcon", "  "), proposal("Contoso", "a Falcon-grade bank"), proposal("--", "x"),
             proposal("Fabrikam", "the Tailspin client")]
    checked = check(draft, LABEL, TEXTS + [Text("ev_00000002", "Contoso and Fabrikam")],
                    [term("Tailspin", "a toy maker")])
    assert checked.problems == [
        f"{LABEL}: /0/term: 'Nightjar' appears in none of the scanned texts",
        f"{LABEL}: /2/term: 'contoso-bank' is the same term as /1 ('Contoso Bank')",
        f"{LABEL}: /5/term: '--' has no words",
        f"{LABEL}: /3/proposed_replacement: is empty; propose a generalization",
        f"{LABEL}: /4/proposed_replacement: 'a Falcon-grade bank' contains the term 'Falcon' (/3)",
        f"{LABEL}: /6/proposed_replacement: 'the Tailspin client' contains the term 'Tailspin' "
        "(decisions/terms.json)",
    ]


def test_a_replacement_holding_its_own_term_is_a_problem():
    checked = check([proposal("Falcon", "Falcon platform")], LABEL, TEXTS, [])
    assert checked.problems == [f"{LABEL}: /0/proposed_replacement: 'Falcon platform' contains the term 'Falcon' (/0)"]


def test_schema_problems_stop_the_check():
    checked = check([{"term": "Falcon", "kind": "secret", "proposed_replacement": "x"}], LABEL, TEXTS, [])
    assert checked.problems == [f"{LABEL}: $[0].kind: 'secret' is not one of "
                                "['codename', 'customer', 'product', 'url', 'financial', 'other']"]
    assert check({"term": "x"}, LABEL, TEXTS, []).problems == [f"{LABEL}: $: expected array, got dict"]


NEW = "07-sanitized.tmp/new-terms.json"
OUTPUT = [Text("b_1", "Built a cache for Fabrikam"), Text("stories.md", "# Stories\n\nFabrikam and Nightjar\n",
                                                           by_line=True)]


def test_new_terms_must_be_undecided_and_list_undecided_candidates():
    candidates = [{"term": "Fabrikam", "kind": "customer", "proposed_replacement": "a retailer", "found_in": []},
                  {"term": "Falcon", "kind": "codename", "proposed_replacement": "a cache", "found_in": []}]
    checked = check([proposal("Nightjar")], NEW, OUTPUT, [term("Falcon", "a cache")], new_terms=True,
                    candidates=candidates)
    assert checked.problems == [
        "'Fabrikam' from 05-terms/candidates.json is not decided and appears in b_1, stories.md:3; list it"]
    checked = check([proposal("Fabrikam", "a retailer", "customer"), proposal("Nightjar", "a tool")], NEW, OUTPUT,
                    [term("Falcon", "a cache")], new_terms=True, candidates=candidates)
    assert checked.problems == []
    assert [r["found_in"] for r in checked.records] == [["b_1", "stories.md:3"], ["stories.md:3"]]
    checked = check([proposal("Falcon", "a cache"), proposal("Fabrikam", "a retailer")], NEW,
                    OUTPUT + [Text("b_2", "Falcon")], [term("Falcon", None)], new_terms=True, candidates=candidates)
    assert checked.problems == [f"{NEW}: /0/term: 'Falcon' is decided in decisions/terms.json; leave it out"]
    assert check([proposal("Tailspin")], NEW, OUTPUT, [], new_terms=True).problems == [
        f"{NEW}: /0/term: 'Tailspin' appears in none of the sanitized text"]


def test_must_list_skips_decided_and_absent_candidates():
    candidates = [{"term": "Fabrikam", "kind": "customer", "proposed_replacement": "x", "found_in": []},
                  {"term": "Nightjar", "kind": "codename", "proposed_replacement": "x", "found_in": []},
                  {"term": "Tailspin", "kind": "customer", "proposed_replacement": "x", "found_in": []}]
    assert [(c["term"], found) for c, found in must_list(candidates, OUTPUT, [term("Nightjar", None)])] == [
        ("Fabrikam", ["b_1", "stories.md:3"])]
