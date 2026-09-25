# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Group the evidence into linked clusters and compute their signals, starting 04-projects.

Usage:
  uv run signals.py --workspace WS

Reads 02-evidence/evidence.jsonl, the raw records it points to in 01-raw/ and
config.json. Begins 04-projects (a fresh 04-projects.tmp/, which discards a
draft in progress) and writes 04-projects.tmp/signals.json: each cluster of
linked items with its signals (authored and reviewed work, dates, repositories,
contributors, epics, performance-review mentions), and each performance review.
Prints the clusters for grouping.

Exit codes: 0 written; 1 error (no or invalid config.json, evidence missing,
invalid or empty); nothing is written on error; 2 usage error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import schema, stages, wsio  # noqa: E402
from ranalyze import clusters, report  # noqa: E402
from ranalyze.common import (EVIDENCE, STAGE, TMP, AnalyzeError, evidence_hash, load_config,  # noqa: E402
                             load_evidence)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    workspace = parser.parse_args(argv).workspace
    try:
        cfg = load_config(workspace)
        evidence = load_evidence(workspace)
        if not evidence:
            raise AnalyzeError(f"{EVIDENCE} has no items; run /resume-builder:collect first")
        data, warnings = clusters.compute(workspace, cfg, evidence, evidence_hash(workspace))
        errors = schema.validate(data, schema.load_schema("signals"))
        if errors:
            raise AnalyzeError([f"signals.json would not be valid: {e}" for e in errors])
    except AnalyzeError as exc:
        for line in exc.lines:
            print(f"error: {line}", file=sys.stderr)
        print(f"{STAGE} not begun", file=sys.stderr)
        return 1
    tmp = stages.begin(workspace, STAGE)
    wsio.write_json(tmp / "signals.json", data)
    for line in warnings:
        print(f"warning: {line}")
    for line in report.signals(data, len(evidence)):
        print(line)
    print(f"wrote {TMP}/signals.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
