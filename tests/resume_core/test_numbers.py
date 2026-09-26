"""rcore.numbers: numbers written with digits, states_value and unsupported."""
from decimal import Decimal

import pytest

from rcore import numbers


def test_numbers_as_written_and_their_values():
    assert numbers.numbers("Cut p99 latency 40% for 1,200 users, 2.5x faster, in Q3,") == [
        ("99", Decimal(99)), ("40", Decimal(40)), ("1,200", Decimal(1200)), ("2.5", Decimal("2.5")),
        ("3", Decimal(3))]
    assert numbers.numbers("two engineers") == []


@pytest.mark.parametrize("text, value, stated", [
    ("p99 checkout latency reduced 40%", 40, True),
    ("cut costs by $1,200,000 a year", 1200000, True),
    ("error rate fell 3.5 points", -3.5, True),
    ("latency cut 40%", 4, False),
    ("2.50 times faster", 2.5, True),
    ("0.1 s faster", 0.1, True),
    ("served 9007199254740993 requests", 9007199254740992, False),
    ("served 9007199254740993 requests", 9007199254740993, True),
])
def test_states_value(text, value, stated):
    assert numbers.states_value(text, value) is stated


def test_unsupported_lists_each_missing_number_once_in_order():
    sources = ["Reduce p99 latency.", "40"]
    assert numbers.unsupported("Cut p99 latency 40% in 250 ms, then 250 ms again, for 3 teams", sources) == [
        "250", "3"]
    assert numbers.unsupported("Mentored two engineers", []) == []
    assert numbers.unsupported("Served 1,200 users", ["1200 users"]) == []


def test_large_numbers_compare_exactly():
    """As floats, 9007199254740993 and 9007199254740992 are the same number."""
    assert numbers.unsupported("served 9007199254740993 requests", ["9007199254740992 requests"]) == [
        "9007199254740993"]
    assert numbers.unsupported("served 9,007,199,254,740,993 requests", ["9007199254740993"]) == []


@pytest.mark.parametrize("value, written", [
    (40, "40"), (-3, "-3"), (2.5, "2.5"), (0.1, "0.1"), (1e16, "10000000000000000"), (0.1234567, "0.1234567"),
    (9007199254740993, "9007199254740993"),
])
def test_digits_writes_a_json_number_back_exactly(value, written):
    assert numbers.digits(value) == written
    assert numbers.states_value(written, value)


def test_the_wizard_uses_the_same_rule():
    from rwizard import metrics
    assert metrics.states_value is numbers.states_value
