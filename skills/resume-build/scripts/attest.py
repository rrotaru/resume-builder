# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Record the engineer's checkpoint 4 answer to a flagged job bullet in decisions/attestations.json.

Usage:
  uv run attest.py --workspace WS accept SLUG BULLET     # keep the rewrite as resume-ats wrote it
  uv run attest.py --workspace WS edit SLUG BULLET       # keep the engineer's edit, still flagged
  uv run attest.py --workspace WS withdraw SLUG BULLET   # remove the attestation for the current text
  uv run attest.py --workspace WS list

This is the only writer of decisions/attestations.json. SLUG is a committed
job version in 08-ats/jobs/, BULLET a bullet_id of its resume.json, or
"summary" for basics.summary. accept and edit record the flag's text_sha256
only while the flag holds the hash of the bullet's current text: a bullet
that is not flagged has nothing to attest, and one changed after the claim
diff is committed again with resume-ats first (ats.py --commit). Revert or
edit a bullet with resume-ats's ats.py --revise SLUG. Attestations for other
texts are kept, so one for an unchanged text survives a redraft. The file is
validated and replaced atomically.

Exit codes: 0 recorded, withdrawn, listed, or nothing to change; 1 rejected
(decisions/attestations.json unchanged); 2 usage error.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import schema, stages, wsio  # noqa: E402
from rbuild import jobs  # noqa: E402
from rbuild.common import ATTESTATIONS, BuildError  # noqa: E402

UNCHANGED = f"{ATTESTATIONS} unchanged"
RECHECK = "commit 08-ats again first: stage.py begin 08-ats --from-current, then ats.py --commit (resume-ats)"


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("accept", "accept a flagged rewrite as resume-ats wrote it"),
                       ("edit", "accept the engineer's edit of a flagged bullet that is still flagged"),
                       ("withdraw", "remove the attestation for a bullet's current text")):
        command = sub.add_parser(name, help=text)
        command.add_argument("slug", metavar="SLUG")
        command.add_argument("bullet", metavar="BULLET")
    sub.add_parser("list", help="print every attestation and whether it applies now")
    return parser.parse_args(argv)


def _save(workspace: Path, records: list[dict]) -> None:
    errors = schema.validate(records, schema.load_schema("attestations"))
    if errors:
        raise BuildError([f"{ATTESTATIONS}: {e}" for e in errors])
    target = Path(workspace) / ATTESTATIONS
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=target.parent, prefix=".attestations.", suffix=".tmp")
    os.close(handle)
    try:
        wsio.write_json(Path(name), records)
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _current(job: jobs.Job, bullet: str) -> tuple[str, str]:
    """The bullet's current text and its hash. Raises BuildError."""
    text = job.texts.get(bullet)
    if text is None:
        what = "basics.summary" if bullet == jobs.SUMMARY else f"bullet {bullet}"
        raise BuildError(f"{jobs.folder(job.slug)}/resume.json has no {what}")
    return text, job.text_hash(bullet)


def _flagged(job: jobs.Job, bullet: str) -> tuple[str, dict]:
    """The bullet's current text and its flag, which must hold that text's hash. Raises BuildError."""
    text, digest = _current(job, bullet)
    flag = job.flag(bullet)
    if flag is not None and flag["text_sha256"] == digest:
        return text, flag
    if flag is None and job.flags["checked"].get(bullet) == digest:
        raise BuildError(f"{bullet} is not flagged in {job.slug}: nothing to attest")
    raise BuildError(f"{bullet} in {job.slug} changed after the claim diff; {RECHECK}")


def _notes(workspace: Path) -> list[str]:
    found = []
    if stages.status(workspace).get("08-ats") == "stale":
        found.append("warning: 08-ats is stale; rebuild it (progress.py names the step) and check its flags again")
    if (Path(workspace) / "08-ats.tmp").is_dir():
        found.append("note: 08-ats.tmp/ holds a draft; this attests the committed text, which still applies after "
                     "the draft's commit only if the text is unchanged")
    return found


def _open_line(job: jobs.Job, records: list[dict]) -> str:
    opened = sum(s.is_open for s in jobs.flag_states(job, records))
    return f"{job.slug}: no open flags" if not opened else \
        f"{job.slug}: {opened} open (final_review.py lists them)"


def _attest(workspace: Path, action: str, slug: str, bullet: str) -> list[str]:
    records = jobs.load_attestations(workspace)
    job = jobs.load_job(workspace, slug)
    text, flag = _flagged(job, bullet)
    record = {"job_slug": slug, "bullet_id": bullet, "text_sha256": flag["text_sha256"], "action": action}
    existing = jobs.attested(records, slug, bullet, flag["text_sha256"])
    if existing is not None and existing["action"] == action:
        return _notes(workspace) + [f"{slug} {bullet} is attested already ({action}); nothing recorded",
                                    _open_line(job, records)]
    if existing is not None:
        updated = [record if r is existing else r for r in records]
        verb = f"changed from {existing['action']} to {action}"
    else:
        updated = records + [record]
        verb = action
    _save(workspace, updated)
    return _notes(workspace) + [f"recorded: {slug} {bullet} {verb} for its current text: {text}",
                                _open_line(job, updated)]


def _withdraw(workspace: Path, slug: str, bullet: str) -> list[str]:
    records = jobs.load_attestations(workspace)
    job = jobs.load_job(workspace, slug)
    _, digest = _current(job, bullet)
    kept = [r for r in records if (r["job_slug"], r["bullet_id"], r["text_sha256"]) != (slug, bullet, digest)]
    if len(kept) == len(records):
        raise BuildError(f"no attestation for the current text of {bullet} in {slug}: nothing to withdraw")
    _save(workspace, kept)
    return [f"withdrew the attestation of {slug} {bullet}", _open_line(job, kept)]


def _list(workspace: Path) -> list[str]:
    records = jobs.load_attestations(workspace)
    current = {}
    for slug in jobs.committed_versions(workspace):
        if slug != jobs.GENERAL:
            job = jobs.load_job(workspace, slug)
            current.update({(slug, b): job.text_hash(b) for b in job.texts})
    lines = []
    for n, r in enumerate(records, start=1):
        applies = current.get((r["job_slug"], r["bullet_id"])) == r["text_sha256"]
        state = "applies to the committed text" if applies else \
            "no committed text has this hash (kept: it applies again if the text returns)"
        lines.append(f"{n}. {r['job_slug']} {r['bullet_id']} {r['action']} {r['text_sha256'][:12]}: {state}")
    return lines or ["no attestations"]


def main(argv=None) -> int:
    args = _parse(argv)
    workspace = args.workspace
    try:
        if args.command == "list":
            lines = _list(workspace)
        elif args.command == "withdraw":
            lines = _withdraw(workspace, args.slug, args.bullet)
        else:
            lines = _attest(workspace, args.command, args.slug, args.bullet)
    except BuildError as exc:
        for line in exc.lines:
            print(f"error: {line}", file=sys.stderr)
        print(UNCHANGED, file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
