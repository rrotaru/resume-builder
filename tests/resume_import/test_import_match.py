"""Whether a value appears in a text (rimport.match)."""
import pytest
from rimport.match import appears, normalize


def found(value, text, kind="text"):
    return appears(value, normalize(text), kind)


@pytest.mark.parametrize("value, text", [
    ("Senior Software Engineer", "Senior Software Engineer, Northwind"),
    ("Jordan Rivera", "JORDAN RIVERA"),  # only case differs
    ("Senior Software Engineer", "Senior Software\nEngineer"),  # wrapped
    ("Senior Software Engineer", "SeniorSoftware  Engineer"),  # extraction lost or added spaces
    ("Senior Software Engineer", "Senior Soft ware Engineer"),
    ("Double-entry ledger", "double–entry ledger"),  # en dash
    ("Double—entry ledger", "double-entry ledger"),  # em dash in the value
    ("Jordan's tools", "Jordan’s tools"),  # curly quote
    ("ﬁle linter", "file linter"),  # ligature (NFKC)
    ("Go", "Backend: Go, Python"),
    ("C++", "Languages: C++, Rust"),
    ("Node.js", "Built with Node.js."),
    ("**Go**", "**Go**"),  # punctuation at both ends needs no boundary
    ("Migrated the order service from PHP to Go, serving 2M requests per day",
     "• Migrated the order service from PHP\nto Go, serving 2M requests per day"),
    ("Zero​width", "Zerowidth"),  # format characters are ignored
])
def test_text_appears(value, text):
    assert found(value, text)


@pytest.mark.parametrize("value, text", [
    ("Go", "Worked at Google"),  # not inside a word
    ("Rat", "rates"),
    ("Java", "JavaScript"),
    ("BS", "JOBS"),
    ("Staff Engineer", "Senior Engineer"),
    ("Sr. Engineer", "Senior Engineer"),
    ("B.S.", "BS, Computer Science"),
    ("BS", "B.S., Computer Science"),
    ("Engineer", "Engi-\nneer"),  # a hyphen is a character, not whitespace
    ("", "anything"),
    ("   ", "anything"),
])
def test_text_does_not_appear(value, text):
    assert not found(value, text)


@pytest.mark.parametrize("value, text", [
    ("https://github.com/jrivera", "github.com/jrivera"),
    ("https://github.com/jrivera/", "https://github.com/jrivera"),
    ("http://www.jrivera.dev", "jrivera.dev"),
    ("https://jrivera.dev", "Portfolio: www.jrivera.dev |"),
    ("mailto:jordan@example.com", "jordan@example.com"),
])
def test_url_appears(value, text):
    assert found(value, text, "url")


def test_url_must_still_match_its_path():
    assert not found("https://github.com/jrivera/other", "github.com/jrivera", "url")
    assert not found("https://", "https://example.com", "url")


@pytest.mark.parametrize("value, text", [
    ("(555) 123-4567", "555.123.4567"),
    ("555-123-4567", "Phone: (555) 123 4567"),
    ("+1 555 123 4567", "+1-555-123-4567"),
])
def test_phone_appears(value, text):
    assert found(value, text, "phone")


@pytest.mark.parametrize("value, text", [
    ("+1 555 123 4567", "(555) 123-4567"),  # a digit the text does not have
    ("555-123-4567", "1555-123-45678"),  # digits run on at either end
    ("555-123-4567", "555-123-4568"),
])
def test_phone_does_not_appear(value, text):
    assert not found(value, text, "phone")
