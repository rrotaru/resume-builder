"""Flags check: every bullet in a job version passed the claim diff, or was attested.

08-ats/jobs/<slug>/flags.json is {"checked": {bullet_id: text_sha256}, "flags": [...]}.
"checked" records the hash of every bullet the claim diff examined, flagged or not,
so a bullet rewritten after the diff is caught even if it was never flagged.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from . import ids, schema, wsio

ATTESTATIONS = "decisions/attestations.json"
_SLUG = re.compile(r"[a-z0-9][a-z0-9-]*")


def _load(workspace: Path, rel: str, schema_name: str) -> tuple[object, list[str]]:
    data, error = wsio.load(workspace, rel)
    if error:
        return None, [error]
    problems = schema.validate(data, schema.load_schema(schema_name))
    return data, [f"{rel}: {p}" for p in problems]


def check_job(workspace: Path, job: str) -> list[str]:
    """Check 08-ats/jobs/<job>. job must be one plain path segment (^[a-z0-9][a-z0-9-]*$)."""
    if not _SLUG.fullmatch(job):
        return [f"{job}: job slug must be a single plain name"]
    workspace = Path(workspace)
    label = f"08-ats/jobs/{job}"
    resume_rel, flags_rel = f"{label}/resume.json", f"{label}/flags.json"
    if not (workspace / resume_rel).is_file():
        return [f"{resume_rel}: not found"]
    if not (workspace / flags_rel).is_file():
        return [f"{flags_rel}: not found; run the claim diff for this job"]

    errors: list[str] = []
    resume, problems = _load(workspace, resume_rel, "tailored-resume")
    errors += problems
    data, problems = _load(workspace, flags_rel, "flags")
    errors += problems
    attestations: object = []
    if (workspace / ATTESTATIONS).is_file():
        attestations, problems = _load(workspace, ATTESTATIONS, "attestations")
        errors += problems
    if errors:
        return errors

    highlights = [h for _, h in wsio.resume_highlights(resume)]
    counts = Counter(h["bullet_id"] for h in highlights)
    errors += [f"{label}: {b} appears more than once in resume.json"
               for b, n in counts.items() if n > 1]
    texts = {h["bullet_id"]: h["text"] for h in highlights}
    attested = {(a["job_slug"], a["bullet_id"], a["text_sha256"]) for a in attestations}
    flagged = {f["bullet_id"]: f for f in data["flags"]}
    checked = data["checked"]

    for bullet in sorted(set(flagged) | set(checked)):
        if bullet not in texts:
            kind = "flag" if bullet in flagged else "checked entry"
            errors.append(f"{label}: {kind} for {bullet}, which is not in resume.json; "
                          "re-run the claim diff")

    for bullet, text in texts.items():
        current = ids.text_sha256(text)
        if (job, bullet, current) in attested:
            continue
        flag = flagged.get(bullet)
        if flag is not None and flag["text_sha256"] == current:
            reasons = "; ".join(flag["reasons"])
            errors.append(f"{label}: {bullet} is flagged ({reasons}); accept, revert or edit it")
        elif flag is None and checked.get(bullet) == current:
            continue
        else:
            errors.append(f"{label}: {bullet} changed after the claim diff; re-run the claim diff")
    return errors
