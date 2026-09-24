import pytest

from rcore import config
from rcore.schema import load_schema, validate


@pytest.mark.parametrize("count, expected", [
    (0, 0), (1, 1), (2, 2), (3, 3), (5, 3), (10, 3), (11, 4), (20, 6), (26, 8), (40, 8), (100, 8),
])
def test_metric_prompt_count_defaults(count, expected):
    assert config.metric_prompt_count(count) == expected


def test_metric_prompt_count_custom_settings():
    assert config.metric_prompt_count(10, percent=0.5, minimum=1, maximum=20) == 5
    assert config.metric_prompt_count(10, percent=0.0, minimum=0, maximum=8) == 0


def test_default_config_matches_schema():
    cfg = config.default_config("Staff Engineer")
    assert cfg["target_role"] == "Staff Engineer"
    assert cfg["metric_prompts"] == {"percent": 0.30, "min": 3, "max": 8}
    assert validate(cfg, load_schema("config")) == []


def test_default_config_returns_independent_copies():
    a = config.default_config()
    a["metric_prompts"]["max"] = 99
    assert config.default_config()["metric_prompts"]["max"] == 8
