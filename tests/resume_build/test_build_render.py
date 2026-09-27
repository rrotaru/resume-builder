"""After checkpoint 4, render leaves every step fresh and nothing to do.

Needs render.py's dependencies (python-docx for --no-pdf). They skip when
missing, except in CI (CI set), where they fail.
"""
import os

import pytest

if not os.environ.get("CI"):
    for module in ("jinja2", "docx", "pypdf"):
        pytest.importorskip(module, reason="needs render.py's dependencies (see module docstring)")

import progress  # noqa: E402
import render  # noqa: E402
from build_samples import build_once, copy_of, fix_time, next_line, run, survey, ws_arg  # noqa: E402
from rbuild import steps  # noqa: E402


@pytest.fixture(autouse=True)
def _time(monkeypatch):
    fix_time(monkeypatch)


@pytest.fixture(scope="module")
def built_root(tmp_path_factory):
    return build_once(tmp_path_factory)


@pytest.fixture
def built(built_root, tmp_path, monkeypatch):
    return copy_of(built_root, tmp_path, monkeypatch)


def test_render_after_the_review_leaves_nothing_to_do(built, capsys):
    assert run(render, built, "--no-pdf") == 0
    found = survey(built)
    assert (found["render"].state, found["render"].note) == ("fresh", "general, fintech-sre (DOCX and TXT)")
    assert next_line(built) == steps.NOTHING
    capsys.readouterr()
    assert progress.main(ws_arg(built)) == 0
    assert capsys.readouterr().out.endswith(f"11. render   fresh    general, fintech-sre (DOCX and TXT)\n"
                                            f"next: {steps.NOTHING}\n")
