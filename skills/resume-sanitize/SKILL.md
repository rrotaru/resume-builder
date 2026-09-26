---
name: resume-sanitize
description: Keep confidential names off the engineer's resume in a resume-builder workspace. The scan (before the wizard) finds likely codenames, customer names, internal URLs and financial figures in the projects, their evidence, performance reviews and the imported profile, and proposes a generalization for each in 05-terms/candidates.json. Apply (after resume-write) replaces every term the engineer denied in bullets, stories and profile prose, writes 07-sanitized/, and lists terms nobody has decided yet in new-terms.json. Use when the engineer asks to sanitize or check their resume for confidential terms, or when resume-build reaches the sanitize scan or sanitize apply step.
---

# resume-sanitize

Follow `../resume-core/SKILL.md` for workspace conventions.

- Resolve `scripts/...` and `../resume-core/...` against this skill's own folder, not against the current directory.
- Run commands from the engineer's project directory, not from the skill folder.
- Always pass `--workspace` explicitly, preferably as an absolute path.

The engineer decides every term in the wizard (`decisions/terms.json`): a replacement denies it, `null` allows it. Render refuses any output that still holds a denied term. The scan proposes terms before the wizard asks; apply replaces the denied ones after resume-write. Scripts find, place and replace terms exactly. You judge which names are sensitive and word the generalizations.

## Which half

Run the half the engineer or resume-build names. Otherwise run **apply** when `06-bullets` exists, and the **scan** when it does not.

## Scan

1. Run `uv run ../resume-core/scripts/stage.py --workspace WS status`.
   - If `04-projects` is `missing`, stop and suggest `/resume-builder:analyze`. If it is `stale`, tell the engineer and offer to analyze again first.
   - If `05-terms.tmp/candidates.json` exists, a scan was interrupted. Do not run `scan.py` without `--commit`, which would discard it: go to step 4.
2. Run `uv run scripts/scan.py --workspace WS`. It prints the projects and the likely terms that `decisions/terms.json` does not decide yet, each with where it appears: `pj_…` a project, `ev_…` an evidence item or performance review, `resume:/…` the imported profile. Likely terms are hints: codename phrases, URLs and hosts, emails, money, and capitalized names.
3. Read the printed projects and likely terms. Where a name needs context, read the item's `title` and `excerpt` in `02-evidence/evidence.jsonl`, or the profile at that pointer.
4. Write `05-terms.tmp/candidates.json`, a JSON list:
   ```json
   [{"term": "Project Falcon", "kind": "codename", "proposed_replacement": "real-time fraud-detection platform"},
    {"term": "Contoso Bank", "kind": "customer", "proposed_replacement": "a top-10 US bank"}]
   ```
   - A candidate is something the employer may not want published: an internal codename or project name, a customer or partner, an unreleased product, an internal URL, host or tool, or a financial figure such as revenue, a budget or a deal size. Public technology (`Redis`, `Kubernetes`), the engineer's own name and contact details, public employers, schools and public open-source projects are not candidates.
   - Copy each term exactly as the text spells it, and list it once. Prefer the full name (`Contoso Bank`); add a shorter form (`Contoso`) only when the text also uses it on its own.
   - `kind`: `codename`, `customer`, `product`, `url`, `financial` or `other`.
   - `proposed_replacement`: a true generalization that reads well where the term stood in a sentence, such as `a top-10 US bank` or `real-time fraud-detection platform`. Never name another company or product, never add a number the text does not state, and never use a candidate or denied term in it.
   - Do not write `found_in`: the script fills it in.
5. Run `uv run scripts/scan.py --workspace WS --commit`. On exit 1, fix the file as each line and its `fix:` line say, and run it again. A `note:` means a candidate is decided already and the wizard will not ask about it.
6. Report the candidates and their proposed replacements, and say that the wizard asks the engineer about each one.

## Apply

1. Run `uv run ../resume-core/scripts/stage.py --workspace WS status`.
   - If `06-bullets` is `missing`, stop and suggest `/resume-builder:write`. If it is `stale`, tell the engineer and offer to write again first.
   - If `07-sanitized.tmp/new-terms.json` exists, apply was interrupted: go to step 4.
2. Run `uv run scripts/apply.py --workspace WS`. It replaces every denied term in the bullets, `stories.md` and the profile's prose, writes them to `07-sanitized.tmp/`, and prints each changed bullet and story line.
   - **Exit 1:** show every line. A replacement that contains a denied term, or one term with two replacements, is fixed in the wizard (`/resume-builder:wizard`). A denied term that could not be replaced is fixed by rewording the bullet or story (`/resume-builder:write`), or by an allowed term the engineer agrees to.
3. Read every bullet in `07-sanitized.tmp/bullets.json` and the whole of `07-sanitized.tmp/stories.md`. Look for names step 4 of the scan would count as candidates that `decisions/terms.json` does not decide.
4. Write `07-sanitized.tmp/new-terms.json` in the same form as the candidates. List every term apply printed as `must list` (a candidate the engineer has not decided), and any other undecided sensitive name you found. Write `[]` when there are none.
5. Run `uv run scripts/apply.py --workspace WS --commit`. On exit 1, fix `new-terms.json` as each line says. If it says the inputs changed, go back to step 2.
6. Report to the engineer:
   - the replacements, and every changed bullet and story line (mechanical replacement can read awkwardly; the engineer fixes that by rewording the replacement in the wizard or the bullet in resume-write);
   - every `warning:` line: a fact field such as a project name that holds a denied term needs a replacement value from the wizard, and a keyword that holds one is left out of the resume;
   - every `notice:` line: an allowed term that looks like a denied term, which the engineer confirms is a different word;
   - the new terms, which the engineer decides in the wizard before apply runs again.

Never edit `decisions/`, `06-bullets/` or `07-sanitized/` by hand, and never weaken or skip the terms check.

## What the scripts guarantee

- The scan reads each project's name, summary and rank reasons, the title and excerpt of each project's evidence and of every performance review, each review's full text, and every string of the imported profile. `found_in` lists every place a candidate appears, by the terms check's matching rules.
- A candidate appears in the scanned text, is listed once, and its replacement holds no candidate or denied term.
- Apply replaces every denied match the terms check would find, including other spellings (`Project-Falcon`, `ProjectFalcon`, plurals), unless an allowed term covers it. At the start of a sentence, heading or list item the replacement is capitalized.
- Only prose changes in the profile (`summary`, `description`, `highlights`, `reference`). Names, titles, employers, dates, URLs, skills and `x-lines` are copied unchanged, because the fact-field check requires them to match the profile.
- The sanitized bullets, stories and profile prose pass the terms check. Every undecided candidate that still appears is in `new-terms.json`.

## Output

```
05-terms/
  candidates.json  # proposed terms: term, kind, proposed_replacement, found_in
07-sanitized/
  bullets.json     # 06-bullets/bullets.json with denied terms replaced in each text
  stories.md       # 06-bullets/stories.md with denied terms replaced; render copies only this file
  profile.json     # 03-profile/profile.json with denied terms replaced in its prose only
  new-terms.json   # undecided terms in the sanitized text, for checkpoint 4
```
