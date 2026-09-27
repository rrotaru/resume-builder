# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Print checkpoint 4, the final review: what the engineer checks before render, and the items still open.

Usage: uv run final_review.py --workspace WS

In order: stages that are not fresh; new terms nobody has decided
(07-sanitized/new-terms.json); every allowed-term notice, which the engineer
confirms; the bullets, story lines and profile prose sanitize apply changed;
fact fields holding a denied term; then each version in 08-ats/ with its
length, keyword coverage, bullets left out, warnings and, for a job, the
state of each flag (flagged, accepted, edited, or changed after the claim
diff). The open items come last, each with what resolves it, then
"checkpoint 4: N open items" or "checkpoint 4: no open items".

Exit codes: 0 printed (open items or not); 1 no committed 08-ats, or an
invalid input; 2 usage error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rbuild import final, steps  # noqa: E402
from rbuild.common import BuildError, plural  # noqa: E402

STATUS_LABELS = {"covered": "covered", "missing_with_evidence": "missing with evidence",
                 "missing_without_evidence": "missing without evidence"}


def _places(where: list[str]) -> str:
    shown = ", ".join(where[:final.PLACES_SHOWN])
    more = len(where) - final.PLACES_SHOWN
    return shown + (f" and {more} more" if more > 0 else "")


def _version_lines(version: final.Version) -> list[str]:
    length = version.report["length"]
    lines = [f"{version.name}: {version.used} of {plural(version.total, 'bullet')}, {length['estimated_lines']} of "
             f"{length['line_budget']} lines ({plural(length['pages'], 'page')} for "
             f"{length['experience_months']} months of experience)"]
    counts = {status: 0 for status in STATUS_LABELS}
    for keyword in version.report["keywords"]:
        counts[keyword["status"]] += 1
    lines.append("  keywords: " + ", ".join(f"{n} {STATUS_LABELS[s]}" for s, n in counts.items()))
    lines += [f"    missing with evidence  {k['keyword']}  {_places(k['where'])}"
              for k in version.report["keywords"] if k["status"] == "missing_with_evidence"]
    lines.append("  left out: none" if not version.left_out else f"  left out: {len(version.left_out)}")
    lines += [f"    {bullet_id}  {reason}  {text}" for bullet_id, reason, text in version.left_out]
    warnings = version.report["warnings"]
    lines.append("  warnings: none" if not warnings else f"  warnings: {len(warnings)}")
    lines += [f"    {w}" for w in warnings]
    if version.flags is not None:
        opened = sum(s.is_open for s in version.flags)
        lines.append(f"  flags: {len(version.flags)}, {opened} open" if version.flags else "  flags: none")
        for state in version.flags:
            lines.append(f"    {state.bullet_id}  {state.status}  {state.text or ''}".rstrip())
            lines += [f"      {reason}" for reason in state.reasons]
    return lines


def render_lines(review: final.Review) -> list[str]:
    lines = ["checkpoint 4: final review"]
    if review.stages:
        lines.append(f"stages: {len(review.stages)} not fresh")
        lines += [f"  {stage}  {state}  {note}".rstrip() for stage, state, note in review.stages]
    else:
        lines.append("stages: fresh from 02-evidence to 08-ats")
    if review.new_terms:
        lines.append(f"new terms: {len(review.new_terms)} undecided")
        for term in review.new_terms:
            places = term.get("found_in", [])
            lines.append(f"  {term['term']!r}  {term['kind']}, proposed {term['proposed_replacement']!r}; "
                         f"{plural(len(places), 'place')}: {_places(places)}")
    else:
        lines.append("new terms: none undecided")
    lines.append(f"notices: {len(review.notices)}" if review.notices else "notices: none")
    lines += [f"  {notice}" for notice in review.notices]
    lines.append(f"sanitized bullets: {len(review.bullets)} of {review.bullet_total} changed")
    for bullet_id, was, now in review.bullets:
        lines += [f"  {bullet_id}  was: {was}", f"  {' ' * len(bullet_id)}  now: {now}"]
    lines.append(f"sanitized stories: {plural(len(review.stories), 'line')} changed")
    for number, was, now in review.stories:
        pad = " " * len(str(number))
        lines += [f"  {number}  was: {was if was is not None else '(no line)'}",
                  f"  {pad}  now: {now if now is not None else '(no line)'}"]
    if review.prose:
        lines.append(f"sanitized profile: {plural(len(review.prose), 'string')} changed")
        for pointer, was, now in review.prose:
            lines += [f"  {pointer}  was: {was}", f"  {' ' * len(pointer)}  now: {now}"]
    else:
        lines.append("sanitized profile: no prose changed")
    if review.facts:
        lines.append(f"facts holding a denied term: {len(review.facts)}")
        for fact in review.facts:
            effect = ("a keyword cannot be replaced, so resume-ats leaves it out" if fact.is_keyword else
                      "set a replacement value with the wizard")
            lines.append(f"  {fact.pointer} {fact.value!r} holds the denied term {fact.term!r}; {effect}")
    else:
        lines.append("facts holding a denied term: none")
    for version in review.versions:
        lines += _version_lines(version)
    if review.items:
        lines.append(f"open items: {len(review.items)}")
        lines += [f"  {item}" for item in review.items]
        lines.append(f"checkpoint 4: {plural(len(review.items), 'open item')}")
    else:
        lines.append("checkpoint 4: no open items")
    return lines


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    args = parser.parse_args(argv)
    try:
        review = final.review(args.workspace, steps.survey(args.workspace))
    except BuildError as exc:
        for line in exc.lines:
            print(f"error: {line}", file=sys.stderr)
        return 1
    for line in render_lines(review):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
