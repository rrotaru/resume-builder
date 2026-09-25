# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pypdf==6.19.0",
#     "python-docx==1.2.0",
# ]
# ///
"""Read the performance review files into 01-raw.tmp/reviews.jsonl.

Usage:
  uv run ingest_reviews.py --workspace WS

Reads every PDF, DOCX, TXT and Markdown file under config.json reviews_dir
(configure.py reviews PATH), recursively, skipping hidden files. Each review is
dated by the first YYYY-MM-DD in its file name, or else by its modification
date. A file without text (a scanned PDF), a password-protected or unreadable
file, and a file of another type are reported and skipped. Run stage.py begin
01-raw first.

Exit codes: 0 done; 1 error (no or invalid config.json, data notice not
accepted, no reviews folder, 01-raw.tmp/ missing); 2 usage error; 3 no file
yielded text.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import config, documents  # noqa: E402
from rcollect import reviews  # noqa: E402
from rcollect.common import CollectError, load_config, plural, require_raw_tmp, write_pages  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    args = parser.parse_args(argv)
    workspace = args.workspace
    try:
        cfg = load_config(workspace)
        if not cfg["reviews_dir"]:
            raise CollectError("no reviews folder; run configure.py reviews PATH")
        root = config.resolve_path(workspace, cfg["reviews_dir"])
        if not root.is_dir():
            raise CollectError(f"{root}: not a folder")
        tmp = require_raw_tmp(workspace)
    except CollectError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    supported, unsupported = reviews.review_files(root)
    pages, lines = [], []
    for path in supported:
        name = path.relative_to(root).as_posix()
        try:
            item = reviews.read_review(root, path)
        except documents.ExtractError as exc:
            lines.append(f"skipped {name}: {exc}")
            continue
        except OSError as exc:
            lines.append(f"skipped {name}: cannot be read ({exc.strerror})")
            continue
        pages.append({"items": [item]})
        how = "from the file name" if item["date_from"] == "name" else "the file's modification date"
        lines.append(f"{name}: {item['date']} ({how})")
    for path in unsupported:
        lines.append(f"skipped {path.relative_to(root).as_posix()}: unsupported format; "
                     "save it as PDF, DOCX, TXT or Markdown")
    write_pages(tmp / "reviews.jsonl", pages)
    for line in lines:
        print(line)
    print(f"wrote {plural(len(pages), 'review')} from {root} to {tmp.name}/reviews.jsonl")
    if not pages:
        print("no review text found: ask for a DOCX or TXT copy of each review, or for its text pasted")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
