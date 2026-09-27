"""The length estimate against real renders: a resume estimated within its budget prints within it.

Needs render.py's dependencies and Chromium (see tests/resume_render/test_render.py); skipped without them,
except in CI.
"""
import copy
import os
import random

import pytest

if not os.environ.get("CI"):
    for module in ("jinja2", "playwright", "pypdf"):
        pytest.importorskip(module, reason="needs render.py's dependencies")

from rats import lint  # noqa: E402
from rrender import html, model, pdf  # noqa: E402

WORDS = ("cut p99 checkout latency 40% for a top-10 US bank by building Redis-backed idempotency cache in Go "
         "migrated order service from PHP serving 2M requests per day and reduced on-call pages by 30% designed "
         "shipped Kafka event pipeline processing billions of ledger events with exactly-once delivery "
         "internationalization infrastructure observability PostgreSQL Kubernetes").split()


def sentence(rng, length):
    words = []
    while len(" ".join(words)) < length:
        words.append(rng.choice(WORDS))
    return " ".join(words)[:length].rstrip()


def resume_near(target, seed):
    """A generated resume whose estimate is target lines or just under."""
    rng = random.Random(seed)
    resume = {"basics": {"name": "Jordan Rivera", "label": "Senior Backend Engineer",
                         "email": "jordan.rivera@example.com", "location": {"city": "Denver", "region": "CO"},
                         "profiles": [{"network": "GitHub", "username": "jrivera", "url": "https://github.com/jrivera"}],
                         "summary": sentence(rng, rng.choice([120, 250])),
                         "x-summary-sources": ["resume:/basics/summary"]},
              "work": [], "projects": [{"name": "ledger-lint", "url": "https://github.com/jrivera/ledger-lint",
                                        "startDate": "2021-04", "x-highlights": []}],
              "education": [{"institution": "State University", "studyType": "BS", "area": "Computer Science",
                             "endDate": "2019"}],
              "certificates": [{"name": "AWS Certified Solutions Architect - Associate",
                                "issuer": "Amazon Web Services", "date": "2024-05"}],
              "skills": [{"name": "Backend", "keywords": ["Go", "Python", "Redis", "PostgreSQL", "Kafka"]}]}
    n = 0
    while True:
        before = copy.deepcopy(resume)
        if not resume["work"] or rng.random() < 0.2:
            resume["work"].append({"name": f"Company {len(resume['work'])}", "position": "Senior Software Engineer",
                                   "startDate": "2019-06", "endDate": "2022-12", "x-highlights": []})
        entry = rng.choice(resume["work"] + resume["projects"])
        entry["x-highlights"].append({"bullet_id": f"b_{n}", "text": sentence(rng, rng.randint(40, 210)),
                                      "sources": []})
        n += 1
        if lint.estimate(resume) > target:
            return before


@pytest.fixture(scope="module")
def chromium():
    try:
        with pdf.Chromium() as browser:
            yield browser
    except (pdf.ChromiumMissing, pdf.ChromiumFailed) as exc:
        if os.environ.get("CI"):
            pytest.fail(f"Chromium is not available in CI: {exc}")
        pytest.skip("Chromium is not installed; run render.py --install-browser")


@pytest.mark.chromium
@pytest.mark.parametrize("target, pages", [(44, 1), (48, 1), (50, 1), (94, 2), (100, 2)])
def test_a_resume_within_its_budget_prints_within_it(chromium, target, pages):
    for seed in range(2):
        resume = resume_near(target, seed)
        assert target - 3 <= lint.estimate(resume) <= target
        page = html.render(model.build(resume))
        for paper in ("letter", "a4"):
            printed, _ = chromium.print_pdf(page, paper)
            assert pdf.finish(printed, "t", "a")[1] <= pages, (target, seed, paper)


@pytest.mark.chromium
def test_the_estimate_is_not_far_above_the_real_height(chromium):
    """At most about 15% above: a resume estimated at 64 lines does not fit one Letter page (about 51.7 lines)."""
    for seed in range(3):
        page = html.render(model.build(resume_near(64, seed)))
        printed, _ = chromium.print_pdf(page, "letter")
        assert pdf.finish(printed, "t", "a")[1] == 2, seed
