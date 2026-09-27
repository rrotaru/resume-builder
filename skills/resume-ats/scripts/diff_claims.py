# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Run the claim diff on the draft versions in 08-ats.tmp/, writing each job's flags.json.

Usage: uv run diff_claims.py --workspace WS [VERSION ...]

VERSION is general or a job slug; without one, every version in the draft.
Each bullet text and the summary is compared with what it rests on: the
bullet's original text in 07-sanitized/bullets.json, its sources' texts (with
denied terms replaced) and its entry's name, position and location. A
keyword of the version, a technical term, a number or a scope word none of
them states is flagged. A job's flags.json records every examined text's
hash in "checked" and the flagged ones in "flags", for checkpoint 4; ats.py
--commit writes it again. The general resume may have no claim.

Exit codes: 0 diffed (a job's flags are allowed); 1 a claim in the general resume, or no draft or version;
2 usage error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import wsio  # noqa: E402
from rats import check, claims, material, report  # noqa: E402
from rats.common import FLAGS, KEYWORDS, AtsError, load_inputs, plural  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("versions", nargs="*", metavar="VERSION")
    args = parser.parse_args(argv)
    try:
        versions = check.chosen(args.workspace, args.versions)
        inputs = load_inputs(args.workspace)
        found = material.build(args.workspace, inputs)
    except AtsError as exc:
        for line in exc.lines:
            print(f"error: {line}", file=sys.stderr)
        return 1
    failed = False
    for target in versions:
        resume, problems = check.resume(args.workspace, target)
        if resume is None:
            failed = True
            for line in problems:
                print(f"error: {line}")
            continue
        keywords, keyword_problems = [], []
        if (args.workspace / target.draft(KEYWORDS)).is_file():
            keywords, keyword_problems = check.keywords(args.workspace, target, inputs.target_role)
        if keyword_problems or not keywords:
            print(f"note: {target.name}: no usable keywords.json, so keywords are not compared; "
                  "the commit compares them")
        if target.is_job:
            flags = claims.flags(resume, found, keywords)
            wsio.write_json(args.workspace / target.draft(FLAGS), flags)
            print(f"{target.name}: {len(flags['checked'])} examined, {len(flags['flags'])} flagged; wrote "
                  f"{target.draft(FLAGS)}")
            for line in report.flag_lines(flags):
                print(line)
            continue
        found_claims = [(pointer, bullet_id, reason) for pointer, bullet_id, _, reasons
                        in claims.examined(resume, found, keywords) for reason in reasons]
        print(f"{target.name}: {plural(len(found_claims), 'claim')} its sources do not support")
        for pointer, bullet_id, reason in found_claims:
            print(f"  {pointer} ({bullet_id}): {reason}")
        if found_claims:
            failed = True
            print("  the general resume may have none: reword only within what each bullet's sources say, or use "
                  "the bullet's own text")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
