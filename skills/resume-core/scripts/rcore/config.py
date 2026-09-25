"""Workspace configuration defaults and the top-N metric prompt rule."""
from __future__ import annotations

import math

DEFAULT_METRIC_PROMPTS = {"percent": 0.30, "min": 3, "max": 8}


def default_config(target_role: str = "") -> dict:
    return {
        "schema_version": 1,
        "target_role": target_role,
        "time_range": {"start": None, "end": None},
        "sources": [],
        "local_repos": [],
        "reviews_dir": None,
        "resume_path": None,
        "metric_prompts": dict(DEFAULT_METRIC_PROMPTS),
        "data_notice_acknowledged_at": None,
    }


def metric_prompt_count(project_count: int, percent: float = 0.30,
                        minimum: int = 3, maximum: int = 8) -> int:
    """N = min(project_count, clamp(ceil(percent * project_count), minimum, maximum)).

    Raises ValueError if minimum is greater than maximum.
    """
    if minimum > maximum:
        raise ValueError(f"metric prompts: minimum {minimum} is greater than maximum {maximum}")
    if project_count <= 0:
        return 0
    n = math.ceil(round(percent * project_count, 9))
    return min(project_count, max(minimum, min(maximum, n)))
