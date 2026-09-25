# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pypdf==6.19.0",
#     "python-docx==1.2.0",
# ]
# ///
"""Start a resume import: extract the resume's text, or load a JSON Resume, into 03-profile.tmp/.

Usage:
  uv run extract_text.py --workspace WS [--resume PATH]

Without --resume the file is config.json resume_path (a relative path there is
relative to the workspace). With --resume, a successful run stores the file's
absolute path in config.json.

PDF, DOCX, TXT and Markdown: writes 03-profile.tmp/resume.txt and source.json,
then prints the text with line numbers for mapping into profile.json.
JSON Resume: writes 03-profile.tmp/profile.json and source.json.
Either way, check_profile.py --commit checks and commits the stage.

Exit codes: 0 done; 1 error (no resume path, missing, unsupported or unreadable
file, invalid JSON Resume, no config.json); 2 usage error; 3 no text found (for
example a scanned PDF).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import config, schema, stages, wsio  # noqa: E402
from rimport import check, extract, jsonresume  # noqa: E402

FAILED, NO_TEXT = 1, 3
STAGE = "03-profile"


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("--resume", type=Path, help="the resume file; stored in config.json on success")
    return parser.parse_args(argv)


def _error(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return FAILED


def _save_resume_path(workspace: Path, cfg: dict, path: Path) -> None:
    """Store path as config.json resume_path, writing a valid file or nothing."""
    if cfg.get("resume_path") == str(path):
        return
    updated = {**cfg, "resume_path": str(path)}
    errors = schema.validate(updated, schema.load_schema("config"))
    if errors:
        print(f"warning: config.json is not valid ({errors[0]}); resume_path not saved", file=sys.stderr)
        return
    target = workspace / "config.json"
    tmp = target.with_name("config.json.tmp")
    wsio.write_json(tmp, updated)
    os.replace(tmp, target)
    print(f"config.json resume_path set to {path}")


def _previous_source(workspace: Path) -> dict | None:
    data, error = wsio.load(workspace, f"{STAGE}/source.json")
    return data if error is None and isinstance(data, dict) else None


def main(argv=None) -> int:
    args = _parse(argv)
    workspace = args.workspace
    if not (workspace / "config.json").is_file():
        return _error(f"{workspace / 'config.json'} not found; run /resume-builder:init first")
    cfg, error = wsio.load(workspace, "config.json")
    if error or not isinstance(cfg, dict):
        return _error(error or "config.json must hold a JSON object")

    if args.resume is not None:
        path = args.resume.expanduser().resolve()
    elif cfg.get("resume_path"):
        path = config.resolve_path(workspace, cfg["resume_path"])
    else:
        return _error("no resume file: config.json resume_path is not set; pass --resume PATH")
    if not path.is_file():
        return _error(f"{path}: not found")

    try:
        fmt = extract.format_of(path)
        data = path.read_bytes()
        digest = check.sha256(data)
        if fmt == "json":
            profile, notes, errors = jsonresume.load(data)
            if errors:
                for line in errors:
                    print(f"error: {path}: {line}", file=sys.stderr)
                return FAILED
            extracted = None
        else:
            extracted = extract.extract(data, fmt, str(path))
    except extract.NoText as exc:
        print(f"error: {exc}", file=sys.stderr)
        return NO_TEXT
    except extract.ExtractError as exc:
        return _error(str(exc))
    except OSError as exc:
        return _error(f"{path}: cannot be read ({exc.strerror})")

    previous = _previous_source(workspace)
    tmp = stages.begin(workspace, STAGE)
    source = {"path": str(path), "format": fmt, "sha256": digest, "text_sha256": None}
    if extracted is None:
        wsio.write_json(tmp / "profile.json", profile)
        print(f"loaded JSON Resume {path} into {tmp.name}/profile.json: {check.describe_sections(profile)}")
        for note in notes:
            print(f"note: {note}")
    else:
        text_bytes = extracted.text.encode("utf-8")
        (tmp / "resume.txt").write_bytes(text_bytes)
        source["text_sha256"] = check.sha256(text_bytes)
        pages = f", {extracted.pages} page{'s' if extracted.pages != 1 else ''}" if extracted.pages else ""
        lines = extracted.text.splitlines()
        print(f"extracted {path} ({fmt}{pages}): {len(lines)} lines in {tmp.name}/resume.txt")
    wsio.write_json(tmp / "source.json", source)
    if previous and previous.get("path") == str(path) and previous.get("sha256") == digest:
        print(f"note: {path} is unchanged since the last import")
    if args.resume is not None:
        _save_resume_path(workspace, cfg, path)
    if extracted is None:
        print("next: run check_profile.py --commit")
    else:
        print(f"next: map the numbered lines below into {tmp.name}/profile.json, "
              "then run check_profile.py --commit")
        print(f"--- {tmp.name}/resume.txt ---")
        for number, line in enumerate(lines, start=1):
            print(f"{number:>4}  {line}".rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
