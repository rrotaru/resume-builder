"""rats.claims: what a rewrite says that the texts it rests on do not."""
import pytest

from ats_samples import B1_JOB, B1_SANITIZED, JOB_KEYWORDS, build, fix_month
from conftest import FIXTURE_WORKSPACE
from rats import claims
from rcore import ids, wsio

INTRODUCES = "introduces '{}', which no cited source mentions"
NUMBER = "states the number '{}', which no cited source states"
KNOWN = ["Built an idempotency cache in Go for checkout", "PAY-42: Add Redis cache", "Cut p99 latency 40%"]


@pytest.mark.parametrize("word, start, technical", [
    ("PostgreSQL", False, True), ("gRPC", False, True), ("SLO", True, True), ("iOS", False, True),
    ("EC2", False, True), ("k8s", False, True), ("p99", False, True), ("C++", False, True), ("C#", False, True),
    ("Node.js", False, True), ("order_service", False, True), ("Kafka", False, True), ("Kafka", True, False),
    ("40ms", False, False), ("2M", False, False), ("10x", False, False), ("latency", False, False),
    ("e.g", False, False), ("Built", True, False),
])
def test_technical(word, start, technical):
    assert claims.technical(word, start) is technical


def test_an_unchanged_or_supported_rewrite_has_nothing_to_flag():
    assert claims.diff("Built an idempotency cache in Go for checkout", KNOWN) == []
    assert claims.diff("Cut p99 latency 40% with a Redis cache in Go", KNOWN) == []
    assert claims.diff("Cut p99 latency 40% with a Redis-backed cache", KNOWN) == []  # hyphens split words


def test_technical_terms_not_in_the_known_texts():
    assert claims.diff("Built a Kafka pipeline on k8s with gRPC and C++; Kafka again", KNOWN) == [
        INTRODUCES.format("Kafka"), INTRODUCES.format("k8s"), INTRODUCES.format("gRPC"), INTRODUCES.format("C++")]
    assert claims.diff("Kafka pipeline for checkout", KNOWN) == []  # a sentence's first word is not checked
    assert claims.diff("Built it. Kafka came later: Terraform too", KNOWN) == [INTRODUCES.format("Terraform")]


def test_keywords_are_flagged_as_phrases_and_hide_the_terms_inside_them():
    text = "Cut p99 latency 40% in Go, raising checkout SLO compliance"
    assert claims.diff(text, KNOWN, ["SLO compliance", "Go", "Kubernetes"]) == [
        INTRODUCES.format("SLO compliance")]
    assert claims.diff(text, KNOWN) == [INTRODUCES.format("SLO")]  # without the keyword, the term
    assert claims.diff("Cut p99 latency 40% with incident response drills", KNOWN, ["incident response"]) == [
        INTRODUCES.format("incident response")]


def test_numbers():
    assert claims.diff("Cut p99 latency 40% across 12 regions and 12 teams", KNOWN) == [NUMBER.format("12")]
    assert claims.diff("Cut p99 latency 1,200 ms", ["1200 ms"]) == [INTRODUCES.format("p99")]
    # A number inside a flagged term is not reported again.
    assert claims.diff("Moved checkout to EC2", KNOWN) == [INTRODUCES.format("EC2")]
    assert claims.diff("Cut latency 45ms", KNOWN) == [NUMBER.format("45")]
    assert claims.diff("Cut latency 40ms", KNOWN) == []  # 40 is known; units are not compared


@pytest.mark.parametrize("text, project, reason", [
    ("Led the checkout cache work", None, "claims 'Led', which no cited source supports"),
    ("Led the checkout cache work", {"role": "core", "scope": "team"},
     "claims 'Led', which neither its sources nor its project's role and scope support"),
    ("Built a cross-functional cache", {"role": "core", "scope": "team"},
     "claims 'cross-functional', which neither its sources nor its project's role and scope support"),
    ("Built a company-wide cache", {"role": "lead", "scope": "org"},
     "claims 'company-wide', which neither its sources nor its project's role and scope support"),
])
def test_scope_words(text, project, reason):
    assert claims.diff(text, ["Built a cache"], project=project) == [reason]


@pytest.mark.parametrize("text, project", [
    ("Led the checkout cache work", {"role": "lead", "scope": "team"}),
    ("Built a cross-team cache", {"role": "core", "scope": "org"}),
    ("Built an org-wide cache", {"role": "core", "scope": "company"}),
    ("Built a global cache", {"role": "core", "scope": "company"}),
])
def test_scope_words_the_project_supports(text, project):
    assert claims.diff(text, ["Built a cache"], project=project) == []


def test_scope_words_a_source_supports_through_its_group():
    assert claims.diff("Spearheaded the cache", ["Jordan led the cache work."]) == []
    assert claims.diff("Built a company-wide cache", ["rolled out globally"]) == []


def test_reasons_come_in_text_order_each_once():
    assert claims.diff("Built Kafka for 12 teams, company-wide, on Kafka", ["Built"]) == [
        INTRODUCES.format("Kafka"), NUMBER.format("12"), "claims 'company-wide', which no cited source supports"]


def test_known_texts_include_sanitized_sources_and_the_entry(monkeypatch):
    fix_month(monkeypatch)
    found = build(FIXTURE_WORKSPACE)
    entry = {"name": "Northwind Payments", "position": "Senior Software Engineer", "startDate": "2023-01"}
    highlight = {"bullet_id": "b_1", "text": "x", "sources": ["ev_191cc8ce", "ev_99a74656", "metric:m_1"]}
    known = found.known(highlight, entry)
    assert known[0] == B1_SANITIZED
    assert "Adds a Redis-backed idempotency cache in front of the a top-10 US bank checkout path." in known
    assert "Northwind Payments" in known
    project = found.project_of(highlight)
    # The customer's generalization and the employer are known; the codename's replacement too.
    assert claims.diff("Cut checkout latency for a top-10 US bank at Northwind Payments", known,
                       project=project) == []
    assert claims.diff("Led a cross-team fix for the real-time fraud-detection platform", known,
                       project=project) == []  # role lead, scope cross-team


def test_the_fixture_job_flags_b_1_only(monkeypatch):
    fix_month(monkeypatch)
    found = build(FIXTURE_WORKSPACE)
    resume = wsio.read_json(FIXTURE_WORKSPACE / "08-ats" / "jobs" / "fintech-sre" / "resume.json")
    flags = claims.flags(resume, found, JOB_KEYWORDS)
    assert flags == wsio.read_json(FIXTURE_WORKSPACE / "08-ats" / "jobs" / "fintech-sre" / "flags.json")
    assert flags["flags"] == [{"bullet_id": "b_1", "text": B1_JOB, "text_sha256": ids.text_sha256(B1_JOB),
                               "reasons": [INTRODUCES.format("SLO compliance")]}]


def test_checked_holds_every_bullet_and_the_summary(monkeypatch):
    fix_month(monkeypatch)
    found = build(FIXTURE_WORKSPACE)
    resume = wsio.read_json(FIXTURE_WORKSPACE / "08-ats" / "jobs" / "fintech-sre" / "resume.json")
    resume["basics"]["summary"] = "Backend engineer who cut p99 checkout latency 40% with Kafka"
    resume["basics"]["x-summary-sources"] = ["metric:m_1"]
    flags = claims.flags(resume, found, JOB_KEYWORDS)
    assert list(flags["checked"]) == ["summary", "b_1", "b_2", "b_3", "b_4"]
    assert flags["checked"]["summary"] == ids.text_sha256(resume["basics"]["summary"])
    assert [(f["bullet_id"], f["reasons"]) for f in flags["flags"]] == [
        ("summary", [INTRODUCES.format("Kafka")]), ("b_1", [INTRODUCES.format("SLO compliance")])]
