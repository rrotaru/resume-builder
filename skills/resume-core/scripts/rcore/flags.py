"""Flags check: every flagged rewrite in a job version was accepted or edited."""
from __future__ import annotations

from pathlib import Path

from . import ids, wsio


def check_job(workspace: Path, job: str) -> list[str]:
    workspace = Path(workspace)
    job_dir = workspace / "08-ats" / "jobs" / job
    label = f"08-ats/jobs/{job}"
    if not (job_dir / "resume.json").is_file():
        return [f"{label}/resume.json: not found"]
    if not (job_dir / "flags.json").is_file():
        return [f"{label}/flags.json: not found; run the claim diff for this job"]

    texts = {h["bullet_id"]: h["text"]
             for _, h in wsio.resume_highlights(wsio.read_json(job_dir / "resume.json"))}
    attestations_path = workspace / "decisions" / "attestations.json"
    attested = {
        (a["job_slug"], a["bullet_id"], a["text_sha256"])
        for a in (wsio.read_json(attestations_path) if attestations_path.is_file() else [])
    }

    errors = []
    for flag in wsio.read_json(job_dir / "flags.json"):
        bullet = flag["bullet_id"]
        if bullet not in texts:
            errors.append(f"{label}: flag for {bullet}, which is not in resume.json; re-run the claim diff")
            continue
        current = ids.text_sha256(texts[bullet])
        if (job, bullet, current) in attested:
            continue
        if current != flag["text_sha256"]:
            errors.append(f"{label}: {bullet} changed since it was flagged; re-run the claim diff")
        else:
            reasons = "; ".join(flag["reasons"])
            errors.append(f"{label}: {bullet} is flagged ({reasons}); accept, revert or edit it")
    return errors
