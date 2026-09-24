"""Source check: every bullet cites at least one source, and every source resolves."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import wsio


@dataclass
class KnownSources:
    evidence_ids: set[str] = field(default_factory=set)
    metric_ids: set[str] = field(default_factory=set)
    profile: dict = field(default_factory=dict)
    wizard: dict = field(default_factory=dict)


def load_known(workspace: Path) -> KnownSources:
    """Collect everything a bullet may cite. Missing files contribute nothing."""
    workspace = Path(workspace)
    known = KnownSources()
    evidence = workspace / "02-evidence" / "evidence.jsonl"
    if evidence.is_file():
        known.evidence_ids = {r["id"] for r in wsio.read_jsonl(evidence)}
    metrics = workspace / "decisions" / "metrics.json"
    if metrics.is_file():
        known.metric_ids = {m["id"] for m in wsio.read_json(metrics)}
    profile = workspace / "03-profile" / "profile.json"
    if profile.is_file():
        known.profile = wsio.read_json(profile)
    wizard = workspace / "decisions" / "profile.json"
    if wizard.is_file():
        known.wizard = wsio.read_json(wizard)
    return known


def _pointer_error(doc: dict, pointer: str, filename: str) -> str | None:
    try:
        wsio.resolve_pointer(doc, pointer)
    except KeyError:
        return f"does not resolve in {filename}"
    return None


def source_error(ref: str, known: KnownSources) -> str | None:
    """Return why a source reference is invalid, or None if it resolves."""
    if ref.startswith("ev_"):
        return None if ref in known.evidence_ids else "unknown evidence id"
    if ref.startswith("metric:"):
        return None if ref[len("metric:"):] in known.metric_ids else "unknown metric id"
    if ref.startswith("resume:"):
        return _pointer_error(known.profile, ref[len("resume:"):], "03-profile/profile.json")
    if ref.startswith("wizard:"):
        return _pointer_error(known.wizard, ref[len("wizard:"):], "decisions/profile.json")
    return "unrecognized source reference"


def check_bullets(bullets: list[dict], known: KnownSources, label: str) -> list[str]:
    errors = []
    for bullet in bullets:
        where = f"{label}: bullet {bullet.get('id')}"
        refs = bullet.get("sources") or []
        if not refs:
            errors.append(f"{where}: has no sources")
        for ref in refs:
            reason = source_error(ref, known)
            if reason:
                errors.append(f"{where}: {ref}: {reason}")
    return errors


def check_resume(resume: dict, known: KnownSources, label: str) -> list[str]:
    """Check a tailored resume: highlights mirror x-highlights, and each is sourced."""
    errors = []
    for section in ("work", "projects"):
        for i, entry in enumerate(resume.get(section, [])):
            texts = [h.get("text") for h in entry.get("x-highlights", [])]
            if entry.get("highlights", []) != texts:
                errors.append(f"{label}: /{section}/{i}: highlights do not match x-highlights")
    bullets = [
        {"id": h.get("bullet_id"), "sources": h.get("sources")}
        for _, h in wsio.resume_highlights(resume)
    ]
    return errors + check_bullets(bullets, known, label)


def check_file(workspace: Path, rel: str, known: KnownSources | None = None) -> list[str]:
    """Check a bullets file (JSON array) or a tailored resume (JSON object)."""
    known = load_known(workspace) if known is None else known
    data = wsio.read_json(Path(workspace) / rel)
    if isinstance(data, list):
        return check_bullets(data, known, rel)
    return check_resume(data, known, rel)
