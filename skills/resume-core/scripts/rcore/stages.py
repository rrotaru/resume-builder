"""Stage lifecycle: begin into <stage>.tmp/, commit atomically, report freshness."""
from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import validation, wsio

STAGES = ("01-raw", "02-evidence", "03-profile", "04-projects", "05-terms",
          "06-bullets", "07-sanitized", "08-ats", "out")
META = "_stage.json"
SCHEMA_VERSION = 1


def _check(stage: str) -> None:
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}; expected one of {', '.join(STAGES)}")


def tmp_dir(workspace: Path, stage: str) -> Path:
    return Path(workspace) / f"{stage}.tmp"


def begin(workspace: Path, stage: str) -> Path:
    """Create an empty <stage>.tmp/ (discarding any leftover) and return its path."""
    _check(stage)
    tmp = tmp_dir(workspace, stage)
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    return tmp


def hash_path(path: Path) -> str:
    """sha256 of a file's bytes, or of a directory's relative paths and file bytes.

    Directory hashes ignore _stage.json so re-committing identical content
    does not mark downstream stages stale.
    """
    path = Path(path)
    if path.is_file():
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    digest = hashlib.sha256()
    for file in sorted(p for p in path.rglob("*") if p.is_file() and p.name != META):
        digest.update(file.relative_to(path).as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(file.read_bytes()).digest())
    return "sha256:" + digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def commit(workspace: Path, stage: str, inputs: list[str], extra: dict | None = None) -> list[str]:
    """Record input hashes, validate <stage>.tmp/, and swap it into place.

    Returns a list of errors. On any error the previous <stage>/ is untouched.
    """
    _check(stage)
    workspace = Path(workspace)
    tmp = tmp_dir(workspace, stage)
    if not tmp.is_dir():
        return [f"{tmp.name}: not found; run begin first"]
    missing = [rel for rel in inputs if not (workspace / rel).exists()]
    if missing:
        return [f"input not found: {rel}" for rel in missing]

    meta = {
        "stage": stage,
        "schema_version": SCHEMA_VERSION,
        "created_at": _now(),
        "inputs": {rel: hash_path(workspace / rel) for rel in sorted(inputs)},
    }
    if extra:
        meta["extra"] = extra
    wsio.write_json(tmp / META, meta)

    errors = validation.validate_paths(workspace, [tmp.name])
    if errors:
        return errors

    final, old = workspace / stage, workspace / f"{stage}.old"
    if old.exists():
        shutil.rmtree(old)
    if final.exists():
        final.rename(old)
    tmp.rename(final)
    if old.exists():
        shutil.rmtree(old)
    return []


def status(workspace: Path) -> dict[str, str]:
    """Map each stage to 'missing', 'fresh' or 'stale'.

    A stage is stale if an input's hash changed, an input is gone, or an
    input lives in a stage that is itself stale.
    """
    workspace = Path(workspace)
    result: dict[str, str] = {}
    for stage in STAGES:
        meta_path = workspace / stage / META
        if not meta_path.is_file():
            result[stage] = "missing"
            continue
        state = "fresh"
        for rel, digest in wsio.read_json(meta_path)["inputs"].items():
            upstream = rel.split("/", 1)[0]
            path = workspace / rel
            if result.get(upstream) == "stale" or not path.exists() or hash_path(path) != digest:
                state = "stale"
                break
        result[stage] = state
    return result
