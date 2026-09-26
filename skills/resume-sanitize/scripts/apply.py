# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Replace the engineer's denied terms in bullets, stories and profile prose, and commit 07-sanitized.

Usage:
  uv run apply.py --workspace WS            # begin 07-sanitized, write the sanitized files, print new terms
  uv run apply.py --workspace WS --commit   # check 07-sanitized.tmp/new-terms.json and commit 07-sanitized

Reads 06-bullets/bullets.json, 06-bullets/stories.md, 03-profile/profile.json,
decisions/terms.json, and (for warnings and new terms) decisions/profile.json
and 05-terms/candidates.json. Every denied match (the terms check's rules,
allowed terms exempting) is replaced by its replacement, capitalized at the
start of a sentence. Only prose changes in the profile (summary, description,
highlights, reference); fact fields and x-lines are copied unchanged. The
result must pass the terms check. Without --commit it begins a fresh
07-sanitized.tmp/, writes bullets.json, profile.json and stories.md, and prints
what changed, fact fields that still hold a denied term, and likely new terms.
The model then writes 07-sanitized.tmp/new-terms.json. With --commit the script
recomputes the files, checks they are unchanged and that new-terms.json lists
every undecided term it must, fills in found_in and commits 07-sanitized.

Exit codes: 0 written, or committed with --commit; 1 error (bullets or stories
missing, an invalid input, an unusable decisions/terms.json, a denied term left
after replacing, a new-terms problem, inputs changed since apply.py ran, a
failed commit); nothing is committed on error; 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import facts, stages, terms, wsio  # noqa: E402
from rcore.profile import overlay  # noqa: E402
from rsanitize import proposals, report  # noqa: E402
from rsanitize.common import (APPLY_STAGE, APPLY_TMP, BULLETS, CANDIDATES, PROFILE, STORIES, TERMS,  # noqa: E402
                              WIZARD_PROFILE, SanitizeError, decided_keys, load, load_terms, patterns_for,
                              plural)
from rsanitize.replace import prose, replace, sanitize_profile  # noqa: E402
from rsanitize.texts import line_of, output_texts  # noqa: E402

NEW_TERMS = f"{APPLY_TMP}/new-terms.json"
FIX_LEFTOVER = ("fix: reword the text at its source: a bullet or story with /resume-builder:write, the profile "
                "with /resume-builder:import; or, if the engineer agrees, allow the word with /resume-builder:wizard")


@dataclass
class Inputs:
    bullets: list[dict]
    stories: str
    profile: dict | None
    wizard: dict | None
    entries: list[dict]
    candidates: list[dict]


@dataclass
class Sanitized:
    bullets: list[dict]
    stories: str
    profile: dict
    counts: Counter = field(default_factory=Counter)
    story_lines: list[int] = field(default_factory=list)
    profile_changes: dict[str, str] = field(default_factory=dict)

    def files(self) -> dict[str, str]:
        """The text of each file apply writes, as it is written."""
        def dump(data) -> str:
            return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        return {"bullets.json": dump(self.bullets), "profile.json": dump(self.profile), "stories.md": self.stories}


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("--commit", action="store_true",
                        help="check 07-sanitized.tmp/new-terms.json and commit 07-sanitized")
    return parser.parse_args(argv)


def _unusable(entries: list[dict]) -> list[str]:
    """Why decisions/terms.json cannot be applied.

    One term with two replacements, or a replacement that holds a denied term.
    """
    problems, seen = [], {}
    for entry in entries:
        if entry["replacement"] is None:
            continue
        key = terms.key(entry["term"])
        first = seen.setdefault(key, entry)
        if first is not entry and first["replacement"] != entry["replacement"]:
            problems.append(f"{TERMS}: '{first['term']}' and '{entry['term']}' are the same term with different "
                            f"replacements ('{first['replacement']}' and '{entry['replacement']}')")
    return problems + terms.replacement_conflicts(entries)


def _inputs(workspace: Path) -> Inputs:
    bullets = load(workspace, BULLETS, f"{BULLETS} not found; run /resume-builder:write first")
    stories = load(workspace, STORIES, f"{STORIES} not found; run /resume-builder:write first")
    profile = load(workspace, PROFILE)
    wizard = load(workspace, WIZARD_PROFILE)
    entries = load_terms(workspace)
    candidates = load(workspace, CANDIDATES) or []
    problems = _unusable(entries)
    if problems:
        raise SanitizeError(problems + ["change these decisions with /resume-builder:wizard"])
    return Inputs(bullets, stories, profile, wizard, entries, candidates)


def _sanitize(inputs: Inputs) -> Sanitized:
    patterns = patterns_for(inputs.entries)
    replacements: dict[str, str] = {}
    for entry in inputs.entries:
        if entry["replacement"] is not None:
            replacements.setdefault(entry["term"], entry["replacement"])
    counts: Counter = Counter()
    bullets = []
    for bullet in inputs.bullets:
        done = replace(bullet["text"], patterns, replacements)
        counts.update(done.counts)
        bullets.append({**bullet, "text": done.text})
    story = replace(inputs.stories, patterns, replacements)
    counts.update(story.counts)
    profile, changes, profile_counts = sanitize_profile(inputs.profile or {}, patterns, replacements)
    counts.update(profile_counts)
    lines = sorted({line_of(story.text, start) for start in story.starts})
    return Sanitized(bullets, story.text, profile, counts, lines, changes)


def _leftovers(result: Sanitized, patterns: terms.Patterns) -> list[str]:
    """Denied terms the terms check still finds in the sanitized text (bullets, stories, profile prose)."""
    found = [f"{b['id']}: contains denylisted term {term!r}"
             for b in result.bullets for term in terms.terms_in(b["text"], patterns)]
    found += terms.scan_text(result.stories, patterns, "stories.md")
    found += [f"resume:{pointer}: contains denylisted term {term!r}"
              for pointer, container, key in prose(result.profile)
              for term in terms.terms_in(container[key], patterns)]
    return found


def _fact_warnings(inputs: Inputs, patterns: terms.Patterns) -> list[str]:
    effective = overlay(inputs.profile or {}, inputs.wizard or {})
    warnings = []
    for pointer, value in facts.fact_values(effective):
        for term in terms.terms_in(value, patterns):
            if "/keywords/" in pointer:
                warnings.append(f"{pointer} {value!r} holds the denied term {term!r}; a keyword cannot be "
                                "replaced, so resume-ats leaves it out")
            else:
                warnings.append(f"{pointer} {value!r} holds the denied term {term!r}; set a replacement value "
                                "with /resume-builder:wizard")
    return warnings


def _error(lines, what: str, fix: str | None = None) -> int:
    for line in lines:
        print(f"error: {line}", file=sys.stderr)
    if fix:
        print(f"  {fix}", file=sys.stderr)
    print(what, file=sys.stderr)
    return 1


def _prepare(workspace: Path, what: str):
    """(inputs, sanitized) or an exit code."""
    try:
        inputs = _inputs(workspace)
    except SanitizeError as exc:
        return _error(exc.lines, what)
    result = _sanitize(inputs)
    leftovers = _leftovers(result, patterns_for(inputs.entries))
    if leftovers:
        return _error([f"{line} after replacing" for line in leftovers], what, FIX_LEFTOVER)
    return inputs, result


def _begin(workspace: Path) -> int:
    prepared = _prepare(workspace, f"{APPLY_STAGE} not begun")
    if isinstance(prepared, int):
        return prepared
    inputs, result = prepared
    tmp = stages.begin(workspace, APPLY_STAGE)
    for name, text in result.files().items():
        (tmp / name).write_text(text, encoding="utf-8")
    print(report.replacements(result.counts))
    for line in report.changes(inputs.bullets, result.bullets, result.stories, result.story_lines,
                               result.profile_changes, BULLETS, STORIES, PROFILE):
        print(line)
    for line in _fact_warnings(inputs, patterns_for(inputs.entries)):
        print(f"warning: {line}")
    for line in terms.allowed_notices(inputs.entries):
        print(line)
    texts = output_texts(result.bullets, result.stories, result.profile)
    must = proposals.must_list(inputs.candidates, texts, inputs.entries)
    skip = decided_keys(inputs.entries) | {terms.key(c["term"]) for c in inputs.candidates}
    likely = report.likely_terms(texts, skip)
    print(f"likely new terms not in decisions/terms.json: {len(must) + len(likely)}")
    for candidate, found in must:
        print(f"  must list  {candidate['term']!r} (a {CANDIDATES} candidate not yet decided)  "
              f"{proposals.describe_places(found)}")
    for line in report.likely_lines(likely):
        print(line)
    print(f"began {APPLY_TMP}/: read the sanitized bullets and stories, write {NEW_TERMS}, "
          "then run apply.py --commit")
    return 0


def _commit(workspace: Path) -> int:
    what = f"{APPLY_STAGE} not committed"
    tmp = workspace / APPLY_TMP
    if not tmp.is_dir():
        return _error([f"{APPLY_TMP}/ not found; run apply.py first"], what)
    prepared = _prepare(workspace, what)
    if isinstance(prepared, int):
        return prepared
    inputs, result = prepared
    for name, text in result.files().items():
        path = tmp / name
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            return _error([f"{APPLY_TMP}/{name} differs from what the inputs give now: the inputs changed since "
                           "apply.py ran; run apply.py again and review the new text"], what)
    draft, error = wsio.load(workspace, NEW_TERMS)
    if error:
        return _error([f"{error}; write the new terms first, [] when there are none (see SKILL.md)"], what)
    texts = output_texts(result.bullets, result.stories, result.profile)
    checked = proposals.check(draft, NEW_TERMS, texts, inputs.entries, new_terms=True, candidates=inputs.candidates)
    if checked.problems:
        for line in checked.problems:
            print(line)
        print(f"  {proposals.FIX_NEW_TERMS}")
        print(f"new terms check failed: {plural(len(checked.problems), 'problem')}; {what}", file=sys.stderr)
        return 1
    wsio.write_json(workspace / NEW_TERMS, checked.records)
    inputs_used = [BULLETS, STORIES, TERMS] + [rel for rel in (PROFILE, CANDIDATES) if (workspace / rel).exists()]
    changed = sum(1 for b, a in zip(inputs.bullets, result.bullets) if a["text"] != b["text"])
    extra = {"bullets": len(result.bullets), "changed_bullets": changed,
             "replacements": sum(result.counts.values()), "new_terms": len(checked.records)}
    errors = stages.commit(workspace, APPLY_STAGE, inputs_used, extra=extra)
    if errors:
        return _error(errors, f"commit of {APPLY_STAGE} failed; previous output left in place")
    for record in checked.records:
        print(f"  new term  {record['term']!r} ({record['kind']}) -> {record['proposed_replacement']!r}  "
              f"{proposals.describe_places(record['found_in'])}")
    print(f"committed {APPLY_STAGE}: {changed} of {plural(len(result.bullets), 'bullet')} changed, "
          f"{plural(extra['replacements'], 'replacement')}, {plural(len(checked.records), 'new term')}")
    return 0


def main(argv=None) -> int:
    args = _parse(argv)
    return _commit(args.workspace) if args.commit else _begin(args.workspace)


if __name__ == "__main__":
    sys.exit(main())
