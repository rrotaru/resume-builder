"""rats.match: how a keyword or term is found in a text."""
import pytest

from rats import match


def found(text, phrase):
    return match.mentions(match.normalize(text), phrase)


@pytest.mark.parametrize("text, phrase, expected", [
    ("Built on Node.js", "Node.js", True),
    ("Built on NodeJS", "Node.js", True),
    ("Built on node js", "Node.js", True),
    ("Ran CI CD pipelines", "CI/CD", True),
    ("Ran CICD pipelines", "CI/CD", True),
    ("Owned SLO compliance", "SLO compliance", True),
    ("Owned SLO-compliance reviews", "SLO compliance", True),
    ("Owned SLO\ncompliance", "SLO compliance", True),
    ("incident-response drills", "incident response", True),
    ("Wrote C++ and C#", "C", False),
    ("Wrote C++ and C#", "C++", True),
    ("Wrote C++ and C#", "C#", True),
    ("Wrote C code", "C", True),
    ("A Go-based service", "Go", True),
    ("Rewrote the Golang services", "Go", False),
    ("Designed REST APIs", "API", True),
    ("Designed REST APIs", "REST API", True),
    ("Fixed caches", "cache", True),
    ("Fixed caching", "cache", False),
    ("Tuned PostgreSQL", "postgresql", True),
    ("Tuned postgresql", "PostgreSQL", True),
    ("Ready to go live", "Go", False),
    ("Wrote Go", "go", True),
    ("for a top-10 US bank", "US", True),
    ("helped us ship", "US", False),
    ("Moved to AWS", "aws", True),
    ("Moved to aws", "AWS", False),
    ("Tuned K8s clusters", "k8s", True),
    ("Tuned k8s clusters", "K8s", False),  # three characters with a capital: case counts
    ("Kubernetes", "", False),
])
def test_mentions(text, phrase, expected):
    assert found(text, phrase) is expected


def test_nfkc_and_format_characters():
    assert found("Tuned Post​greSQL", "PostgreSQL")  # zero-width space removed
    assert found("Ran Ｇｏ services", "Go")  # full-width letters
    assert match.normalize("ﬁle") == "file"


def test_spans_are_in_the_normalized_text():
    text = match.normalize("Cut latency, raising SLO compliance and SLO-compliance")
    assert [text[s:e] for s, e in match.spans(text, "SLO compliance")] == ["SLO compliance", "SLO-compliance"]


@pytest.mark.parametrize("phrase, sensitive", [
    ("Go", True), ("AWS", True), ("SLO", True), ("C++", True), ("k8s", False), ("CI/CD", False),
    ("Redis", False), ("go", False),
])
def test_case_sensitive(phrase, sensitive):
    assert match.case_sensitive(phrase) is sensitive


def test_key():
    assert match.key("Node.js") == match.key("node js") == "node js"
    assert match.key("Go") != match.key("go")
    assert match.key("SLO  compliance") == match.key("slo-compliance")
