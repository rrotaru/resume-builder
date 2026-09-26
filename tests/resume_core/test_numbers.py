"""rcore.numbers: numbers written with digits, states_value and unsupported."""
import pytest

from rcore import numbers


def test_numbers_as_written_and_their_values():
    assert numbers.numbers("Cut p99 latency 40% for 1,200 users, 2.5x faster, in Q3,") == [
        ("99", 99.0), ("40", 40.0), ("1,200", 1200.0), ("2.5", 2.5), ("3", 3.0)]
    assert numbers.numbers("two engineers") == []


@pytest.mark.parametrize("text, value, stated", [
    ("p99 checkout latency reduced 40%", 40, True),
    ("cut costs by $1,200,000 a year", 1200000, True),
    ("error rate fell 3.5 points", -3.5, True),
    ("latency cut 40%", 4, False),
    ("2.50 times faster", 2.5, True),
])
def test_states_value(text, value, stated):
    assert numbers.states_value(text, value) is stated


def test_unsupported_lists_each_missing_number_once_in_order():
    sources = ["Reduce p99 latency.", "40"]
    assert numbers.unsupported("Cut p99 latency 40% in 250 ms, then 250 ms again, for 3 teams", sources) == [
        "250", "3"]
    assert numbers.unsupported("Mentored two engineers", []) == []
    assert numbers.unsupported("Served 1,200 users", ["1200 users"]) == []


def test_the_wizard_uses_the_same_rule():
    from rwizard import metrics
    assert metrics.states_value is numbers.states_value
