"""Source check: every bullet cites at least one source, and every source resolves."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import validation, wsio

LABEL_ERROR = "basics.label must match the target role in config.json or the imported profile's label"


@dataclass
class KnownSources:
    evidence_ids: set[str] = field(default_factory=set)
    metric_ids: set[str] = field(default_factory=set)
    profile: dict = field(default_factory=dict)
    wizard: dict = field(default_factory=dict)
    target_role: str | None = None  # config.json target_role
    errors: list[str] = field(default_factory=list)  # files present but unreadable


def _ids(records) -> set[str]:
    if not isinstance(records, list):
        return set()
    return {r["id"] for r in records if isinstance(r, dict) and isinstance(r.get("id"), str)}


def load_known(workspace: Path) -> KnownSources:
    """Collect everything a bullet may cite.

    Missing files contribute nothing. A file that exists but cannot be read
    contributes nothing and adds a line to known.errors.
    """
    workspace = Path(workspace)
    known = KnownSources()

    def read(rel: str, fmt: str = "json"):
        if not (workspace / rel).is_file():
            return None
        data, error = wsio.load(workspace, rel, fmt)
        if error:
            known.errors.append(error)
        return data

    known.evidence_ids = _ids(read("02-evidence/evidence.jsonl", "jsonl"))
    known.metric_ids = _ids(read("decisions/metrics.json"))
    profile = read("03-profile/profile.json")
    known.profile = profile if isinstance(profile, dict) else {}
    wizard = read("decisions/profile.json")
    known.wizard = wizard if isinstance(wizard, dict) else {}
    config = read("config.json")
    role = config.get("target_role") if isinstance(config, dict) else None
    known.target_role = role if isinstance(role, str) else None
    return known


def _allowed_labels(known: KnownSources) -> set[str]:
    basics = known.profile.get("basics")
    labels = {known.target_role, basics.get("label") if isinstance(basics, dict) else None}
    return {label for label in labels if isinstance(label, str)}


def _is_tailored(rel: str) -> bool:
    return validation.schema_for(rel) == ("tailored-resume", "json")


def _pointer_error(doc: dict, pointer: str, filename: str) -> str | None:
    """A pointer source must resolve to a single string or number."""
    try:
        value = wsio.resolve_pointer(doc, pointer)
    except KeyError:
        return f"does not resolve in {filename}"
    if not pointer.startswith("/") or isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return f"must point to a single value in {filename}"
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


def check_resume(resume: dict, known: KnownSources, label: str,
                 tailored: bool | None = None) -> list[str]:
    """Check a resume document.

    - In work and projects, highlights must equal the x-highlights texts, in order.
    - education, certificates and skills entries may not carry highlights
      (they would render with no sources).
    - Each x-highlight, and basics.summary if present (as bullet "summary",
      citing basics.x-summary-sources), must cite sources that resolve.
    - In a tailored resume, basics.label (if present) must equal config.json
      target_role or 03-profile/profile.json basics.label. tailored defaults
      to whether label is a tailored resume path (08-ats/.../resume.json).
    """
    if tailored is None:
        tailored = _is_tailored(label)
    errors = []
    for section in ("work", "projects"):
        for i, entry in enumerate(resume.get(section, [])):
            texts = [h.get("text") for h in entry.get("x-highlights", [])]
            if entry.get("highlights", []) != texts:
                errors.append(f"{label}: /{section}/{i}: highlights do not match x-highlights")
    for section in ("education", "certificates", "skills"):
        for i, entry in enumerate(resume.get(section, [])):
            if isinstance(entry, dict) and "highlights" in entry:
                errors.append(f"{label}: /{section}/{i}: highlights are only allowed in work and projects")
    bullets = []
    basics = resume.get("basics", {})
    if tailored and isinstance(basics, dict) and "label" in basics:
        value = basics["label"]
        if not isinstance(value, str) or value not in _allowed_labels(known):
            errors.append(f"{label}: {LABEL_ERROR}")
    if isinstance(basics, dict) and "summary" in basics:
        bullets.append({"id": "summary", "sources": basics.get("x-summary-sources")})
    bullets += [
        {"id": h.get("bullet_id"), "sources": h.get("sources")}
        for _, h in wsio.resume_highlights(resume)
    ]
    return errors + check_bullets(bullets, known, label)


def check_file(workspace: Path, rel: str, known: KnownSources | None = None) -> list[str]:
    """Check a bullets file (JSON array) or a tailored resume (JSON object).

    When known is not given it is loaded here, and any problems reading the
    source files are reported first.
    """
    errors: list[str] = []
    if known is None:
        known = load_known(workspace)
        errors += known.errors
    data, error = wsio.load(workspace, rel)
    if error:
        return errors + [error]
    if isinstance(data, list):
        return errors + check_bullets(data, known, rel)
    if isinstance(data, dict):
        return errors + check_resume(data, known, rel)
    return errors + [f"{rel}: expected a bullets array or a resume object"]
