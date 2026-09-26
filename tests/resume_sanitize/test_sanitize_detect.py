"""Likely terms (rsanitize.detect) and the sentence-start rule they share with replacing."""
import pytest

from rsanitize.detect import detect
from rsanitize.replace import sentence_start


def found(text, names=True):
    return [(hit.kind, hit.term) for hit in detect(text, names)]


def test_codenames():
    assert found("We shipped Project Falcon and then operation Nightjar Two.") == [
        ("codename", "Project Falcon"), ("codename", "operation Nightjar Two")]
    assert found("a project plan") == []


def test_urls_and_hosts():
    assert found("See https://wiki.northwind.internal/pay/42. Or www.contoso.com, or build.corp:8080") == [
        ("url", "wiki.northwind.internal/pay/42"), ("url", "www.contoso.com"), ("url", "build.corp")]
    assert found("docs at example.com and node.js") == []


def test_emails():
    assert found("mail jo@contoso.com today") == [("email", "jo@contoso.com")]


def test_money():
    assert found("won $1.2M ARR and €300k, a 2 million USD deal, USD 5M budget") == [
        ("money", "$1.2M"), ("money", "€300k"), ("money", "2 million USD"), ("money", "USD 5M")]
    assert found("served 2M requests in 3 regions") == []


def test_names_are_runs_of_capitalized_words():
    assert found("Cut latency for Contoso Bank and Fabrikam in Go") == [
        ("name", "Contoso Bank"), ("name", "Fabrikam"), ("name", "Go")]


def test_a_single_word_at_a_sentence_start_is_not_a_name():
    assert found("Reduce latency. Contoso asked: Fabrikam too") == []
    assert found("## Fabrikam\n- Tailspin rollout") == []


def test_a_run_at_a_sentence_start_also_counts_without_its_first_word():
    assert found("Fix Falcon cache") == [("name", "Fix Falcon"), ("name", "Falcon")]
    assert found("Contoso Bank onboarding") == [("name", "Contoso Bank"), ("name", "Bank")]


def test_short_capitals_jira_keys_and_i_end_a_run():
    assert found("the API for Contoso PR and I Nightjar") == [("name", "Contoso"), ("name", "Nightjar")]
    assert found("fixed PAYMENTS-12 for Northwind") == [("name", "Northwind")]
    assert found("the iPhone and Redis-backed cache") == [("name", "Redis")]


def test_function_words_are_dropped_and_long_runs_skipped():
    assert found("then The Contoso Bank team") == [("name", "Contoso Bank")]
    assert found("then A Very Long Title Case Heading here") == []


def test_names_never_overlap_earlier_hits():
    assert found("for Project Falcon Checkout at https://Contoso.example/Page") == [
        ("codename", "Project Falcon Checkout"), ("url", "Contoso.example/Page")]


def test_names_can_be_turned_off():
    assert found("the Contoso Bank site www.contoso.com", names=False) == [("url", "www.contoso.com")]


@pytest.mark.parametrize("before, start", [
    ("", True), ("## ", True), ("- ", True), ("1. ", True), ("> ", True), ("x\n- ", True),
    ("- **Task:** ", True), ("Done. ", True), ("Why? ", True), ("Intro.\n\n", True), ("(", True),
    ("Checkout for ", False), ("Checkout for\n", False), ("the ", False), ("a, ", False),
])
def test_sentence_start(before, start):
    assert sentence_start(before) is start
