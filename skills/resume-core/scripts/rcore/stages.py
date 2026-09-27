"""Stage lifecycle: begin into <stage>.tmp/, commit safely, report freshness."""
from __future__ import annotations

import hashlib
import posixpath
import re
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


def _recover(workspace: Path, stage: str) -> None:
    """Undo an interrupted swap: if <stage>/ is missing but <stage>.old/ exists, restore it."""
    final, old = Path(workspace) / stage, Path(workspace) / f"{stage}.old"
    if not final.exists() and old.is_dir():
        old.rename(final)


def begin(workspace: Path, stage: str, from_current: bool = False) -> Path:
    """Create a fresh <stage>.tmp/ (discarding any leftover) and return its path.

    With from_current, the tmp folder starts as a copy of the committed
    <stage>/ without its _stage.json, so a skill can replace part of a stage
    (for example one job's folder) and keep the rest.
    """
    _check(stage)
    _recover(workspace, stage)
    tmp = tmp_dir(workspace, stage)
    if tmp.exists():
        shutil.rmtree(tmp)
    current = Path(workspace) / stage
    if from_current and current.is_dir():
        shutil.copytree(current, tmp, ignore=lambda d, names: [META] if Path(d) == current else [])
    else:
        tmp.mkdir(parents=True)
    return tmp


def _outside_workspace(workspace: Path, rel: str) -> bool:
    """True if rel is absolute, climbs out with "..", or names the workspace root itself."""
    parts = re.split(r"[\\/]", rel)
    if rel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel) is not None or ".." in parts:
        return True
    if all(part in ("", ".") for part in parts):
        return True
    return (workspace / rel).resolve() == workspace.resolve()


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


def _normalize_input(rel: str) -> str:
    """Canonical workspace-relative spelling, so ./04-projects records as 04-projects."""
    return posixpath.normpath(rel.replace("\\", "/"))


def commit(workspace: Path, stage: str, inputs: list[str], extra: dict | None = None) -> list[str]:
    """Record input hashes, validate <stage>.tmp/, and swap it into place safely.

    inputs are workspace-relative paths. Returns a list of errors. On any
    error the previous <stage>/ is untouched. If the swap is interrupted,
    the next begin, commit or status restores the previous <stage>/.
    """
    _check(stage)
    workspace = Path(workspace)
    _recover(workspace, stage)
    tmp = tmp_dir(workspace, stage)
    if not tmp.is_dir():
        return [f"{tmp.name}: not found; run begin first"]
    outside = [rel for rel in inputs if _outside_workspace(workspace, rel)]
    if outside:
        return [f"input must be workspace-relative: {rel}" for rel in outside]
    inputs = [_normalize_input(rel) for rel in inputs]
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


def stale_inputs(workspace: Path) -> dict[str, list[tuple[str, str]]]:
    """For each committed stage, the recorded inputs that make it stale.

    Each is (input, why): "stale" when the input lives in a stage that is
    itself stale, "missing" when it is gone, "changed" when its hash differs.
    A fresh stage maps to []; a stage without _stage.json is left out.
    Restores any stage left as <stage>.old/ by an interrupted commit first.
    """
    workspace = Path(workspace)
    result: dict[str, list[tuple[str, str]]] = {}
    for stage in STAGES:
        _recover(workspace, stage)
        meta_path = workspace / stage / META
        if not meta_path.is_file():
            continue
        reasons = []
        for rel, digest in wsio.read_json(meta_path)["inputs"].items():
            upstream = _normalize_input(rel).split("/", 1)[0]
            path = workspace / rel
            if result.get(upstream):
                reasons.append((rel, "stale"))
            elif not path.exists():
                reasons.append((rel, "missing"))
            elif hash_path(path) != digest:
                reasons.append((rel, "changed"))
        result[stage] = reasons
    return result


def status(workspace: Path) -> dict[str, str]:
    """Map each stage to 'missing', 'fresh' or 'stale'.

    A stage is stale if an input's hash changed, an input is gone, or an
    input lives in a stage that is itself stale (stale_inputs says which).
    Restores any stage left as <stage>.old/ by an interrupted commit first.
    """
    reasons = stale_inputs(workspace)
    return {stage: "missing" if stage not in reasons else "stale" if reasons[stage] else "fresh"
            for stage in STAGES}
