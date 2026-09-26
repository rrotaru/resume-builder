---
name: resume-core
description: Workspace rules, data formats and hard checks shared by every resume-builder skill. Use when another resume-builder skill says to follow resume-core, or when validating a resume workspace, checking bullet sources, checking for confidential terms, checking job-version flags, or reporting which stages are stale.
---

# resume-core

Shared conventions for resume-builder skills. Other skills refer to this folder as `../resume-core/`.
Run every script with `uv run`. Each one takes `--workspace` (default `resume-workspace`).

## Running the scripts

- Resolve every `../resume-core/...` path against the folder of the skill whose instructions you are following, not against the current directory.
- Run commands from the engineer's project directory, not from the skill folder.
- Always pass `--workspace` explicitly, preferably as an absolute path. File paths given to a script are relative to the workspace.

## Workspace

```
resume-workspace/
  config.json      decisions/ (terms, projects, metrics, profile, attestations, wizard)
  01-raw/  02-evidence/  03-profile/  04-projects/  05-terms/
  06-bullets/  07-sanitized/  08-ats/  out/
```

- Each numbered folder is a **stage**, written by exactly one skill.
- `decisions/` holds the engineer's choices. Only the wizard and checkpoints write to it; regenerating a stage never touches it. `decisions/wizard.json` is the wizard's own bookkeeping (which imported entry each profile answer was given for, and skipped questions); no stage reads it.
- Never edit another skill's stage folder.

## Writing a stage

1. `uv run ../resume-core/scripts/stage.py --workspace WS begin <stage>` creates an empty `<stage>.tmp/` and prints its path.
   To change only part of a stage (for example one job's folder in `08-ats/jobs/`), add `--from-current`:
   the tmp folder then starts as a copy of the committed `<stage>/` (without `_stage.json`), so the parts you do not rewrite are kept.
2. Write every output file into that folder.
3. `uv run ../resume-core/scripts/stage.py --workspace WS commit <stage> --inputs <each file or folder you read>`
   records input hashes, validates the folder, and swaps it into place.
   Inputs must be workspace-relative (no absolute paths, no `..`, not the workspace root such as `.` or an empty path).
   To record facts about the run, such as skipped rows, add `--extra '{"skipped_rows": 3}'` (a JSON object, stored as `extra` in `_stage.json`).
4. If commit prints errors, fix the named records and commit again. The previous output stays in place until a commit succeeds. Never skip or weaken a check.

`stage.py --workspace WS status` prints each stage as `missing`, `fresh` or `stale`. Before reading a stale stage, tell the engineer and offer to rebuild it.
If a commit was interrupted mid-swap, the next `begin`, `commit` or `status` restores the previous output from `<stage>.old/`.

## Source references

Every bullet's `sources` list holds one or more of:

| Reference | Resolves against |
|---|---|
| `ev_<8 or 12 hex>` | `02-evidence/evidence.jsonl` |
| `metric:<id>` | `decisions/metrics.json` |
| `resume:<JSON Pointer>` | `03-profile/profile.json`, e.g. `resume:/work/1/highlights/0` |
| `wizard:<JSON Pointer>` | `decisions/profile.json`, e.g. `wizard:/basics/email` |

A `resume:` or `wizard:` pointer must start with `/` and point to a single string or number, not to an object, array, boolean or null.

A bullet in `06-bullets/bullets.json` (and `07-sanitized/bullets.json`) names its place on the resume. `work_ref` is the index, in the effective profile's `work` (see [The profile](#the-profile)), of the job it goes under: for a project bullet, a job whose dates overlap the project's months. A bullet about a profile `projects` entry has `work_ref` null and cites a `resume:/projects/<i>/…` pointer. A project bullet with `work_ref` null and no such pointer falls in no job, and has no place until the engineer adds the job with the wizard. resume-write's `write.py --commit` checks this, and that a bullet cites only its own project's evidence, performance reviews, its project's metrics and the profile.

## Tailored resumes and job flags

- `08-ats/general/resume.json` and `08-ats/jobs/<slug>/resume.json` follow `schemas/tailored-resume.schema.json`. Only the sections `basics`, `work`, `projects`, `education`, `certificates` and `skills` are allowed. Every `work` and `projects` entry has `x-highlights` (`{bullet_id, text, sources}`, possibly empty) and `highlights` holding the same texts in order. Other sections carry no `highlights`. A `basics.summary` needs a non-empty `basics.x-summary-sources`. Every object accepts only the fields listed in the schema: `work` and `projects` entries have no `summary` or `description` (claims go in sourced highlights), and entries carry no `x-sources`. `basics.label`, if present, must equal `config.json` `target_role` or the profile's `basics.label`.
- Every other field that is not a bullet is a **fact field** (name, contact details, employer, title, dates, degree, institution, certificate, skill name, level and keywords) and must be copied from the profile, as described below. Never write or reword a fact field in a tailored resume; if the profile is wrong, the engineer corrects it through the wizard.
- `08-ats/jobs/<slug>/flags.json` is `{"checked": {"<bullet_id>": "<text_sha256>"}, "flags": [...]}`. The claim diff records in `checked` the hash of every bullet it examined, flagged or not, and lists unsupported claims in `flags`.

## The profile

`03-profile/profile.json` is resume-import's faithful reading of the engineer's resume. For a PDF, DOCX, TXT or Markdown resume, `03-profile/resume.txt` holds the extracted text and each entry carries `x-lines` (`{"first": n, "last": m}`, the lines it was read from). resume-import's `check_profile.py` proves that every value appears in `resume.txt` and that entries keep its order, so an index such as `/work/1` means the same job across imports of the same file. `03-profile/source.json` records the imported file.

The profile is `03-profile/profile.json` with `decisions/profile.json` laid over it (`rcore.profile.effective_profile`):

- Two objects merge key by key.
- Two arrays of objects merge by index: wizard item *i* merges onto imported item *i*, items past the end are added, and `{}` leaves an imported item unchanged. So `"work": [{}, {"endDate": "2022-12"}]` fills in the second job's end date.
- Two other arrays (such as `keywords`) combine: imported items, then wizard items not already present.
- Otherwise the wizard's value replaces the imported one.

A tailored resume's fact fields must match it:

- Each `basics` field equals the profile's value; each `location` key equals the profile's; each `profiles` item equals some profile item in every field it has.
- Each entry in `work`, `projects`, `education`, `certificates` and `skills` matches one profile entry of the same section: every fact field it has, that entry has with the same value (exact text); `keywords` holds only that entry's keywords, in any order; other fields may be left out.
- A date may be shortened (`2023-01-15` as `2023-01` or `2023`), never lengthened, and an entry has a date field exactly when its profile entry does, so a past job cannot lose its `endDate`.

A confidential term in a fact field (for example a codename used as a project name) is fixed with a wizard answer at that path in `decisions/profile.json`, never by rewording the tailored resume. A keyword cannot be replaced that way (keywords combine), so a keyword holding a denied term is left out of the tailored resume.

Only resume-wizard's `answer.py` writes `decisions/profile.json`, `decisions/terms.json` and `decisions/metrics.json`. It writes profile answers under the rules above (facts only, `{}` padding, an index at most one past the end) and anchors each one to the imported entry it was given for, so a re-import that moves the entry becomes a wizard question.

## Checks

| Script | Fails when |
|---|---|
| `validate.py [PATH ...]` | a file does not match its schema in `schemas/`, or an array has duplicate `id`s |
| `check_sources.py FILE ...` | a bullet (or a resume's `summary`) has no sources or cites one that does not resolve; a resume's `highlights` differ from its `x-highlights` texts; `education`, `certificates` or `skills` carry `highlights`; a tailored resume's `basics.label` is neither the target role nor the profile's label, or one of its fact fields is not copied from the profile |
| `check_terms.py FILE ...` | text contains a term from `decisions/terms.json` whose `replacement` is not null, or `decisions/terms.json` is missing or invalid |
| `check_flags.py JOB ...` | a bullet in `08-ats/jobs/<JOB>/resume.json` is flagged with no matching attestation, or changed after the claim diff, or a flag names a bullet that is gone |

Each prints one line per problem (file, record and rule) and exits 1 on failure. `validate.py` and `check_sources.py` normalize each path first (`./`, `//`, `.` and `..` segments, or an absolute path inside the workspace), and report a path outside the workspace as an error. `check_sources.py` applies the tailored-resume checks to every resume object except the profile files (`03-profile/profile.json`, `07-sanitized/profile.json`, `decisions/profile.json`). A missing, non-UTF-8 or invalid-JSON file is reported as a problem line, not a crash, and so is a resume that does not match its schema (`<file>: does not match its schema; run validate.py`). Run `validate.py` first to see why.

The terms check is strict: it matches after Unicode NFKC normalization, removal of invisible characters (format characters such as zero-width spaces and soft hyphens, variation selectors, Hangul fillers, tag characters and the Braille blank) and case folding; the words of a term may be joined by any run of spaces, line breaks, underscores, dashes, minus signs, full stops, slashes, backslashes, middle dots, bullets or similar slash and dot lookalikes, or by nothing; and for terms of 5 or more letters a plural `s`/`es` still matches. So `Project-Falcon`, `Project.Falcon`, `ProjectFalcon` and `Falcons` are all caught.

An allowed term (`replacement: null`) exempts a denied match only when the allowed term, matched literally (same words, same spacing, case-insensitive, whole word, no plural), covers the whole match. For example, with `Check Point` denied and `checkpoint` allowed, "Added a checkpoint" passes and "Worked at Check Point" still fails.

To resolve a false positive, either add the flagged word to `decisions/terms.json` as an allowed term (`replacement: null`), with the engineer's agreement, or reword the text. Never weaken or bypass the check itself.

Allowed terms match literally, so plural forms are not covered: add each one as its own allowed term (for example `checkpoints` beside `checkpoint`). An allowed term may not equal or contain a denied term as a whole word (with `Contoso` denied, `Contoso Bank` cannot be allowed); `decisions/terms.json` is then invalid and the terms check fails.

An allowed term that only looks like a denied term, such as `ContosoBank` or `contoso-banks` beside denied `Contoso Bank`, or `checkpoint` beside denied `Check Point`, is valid, but `check_terms.py` prints a notice for it on stderr (`notice: allowed term '<a>' looks like denied term '<d>'; ...`). Notices never change the exit code. Skills must show every notice to the engineer at checkpoint 4 and have them confirm that the allowed term is a different word; `terms.allowed_notices()` returns the same list.

## Python helpers for other skills' scripts

Scripts in other skills may import the shared library:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import ids, stages, wsio  # noqa: E402
```

`ids.evidence_id(source, native_key)`, `ids.assign_evidence_ids(keys)`, `ids.project_id(evidence_ids)`,
`ids.text_sha256(text)`, `config.metric_prompt_count(n, percent, minimum, maximum)`,
`config.resolve_path(workspace, value)` (a relative path in `config.json` is relative to the workspace),
`profile.effective_profile(workspace)`, `profile.overlay(imported, wizard)`,
`profile.SECTIONS` and the other JSON Resume field lists, `profile.PROSE_FIELDS` (`summary`, `description`, `highlights`, `reference`),
`profile.identity(section, entry)` / `describe` / `merged_arrays(doc)` (which entry an array item is), `profile.is_date(value)`,
`facts.fact_values(profile)` (the fact fields a tailored resume may copy, as pointer and value),
`terms.find(text, patterns)` (denied matches as spans of the original text), `terms.terms_in(text, patterns)`,
`terms.key(term)` (two spellings of one term share a key), `terms.read_entries(workspace)`,
`terms.replacement_conflicts(entries)` (a replacement that holds a denied term),
`wsio.read_json / write_json / read_jsonl / write_jsonl / resolve_pointer`,
`documents.extract(data, fmt, name)` (the normalized text of a PDF, DOCX, TXT or Markdown file's bytes),
`numbers.numbers(text)` (numbers written with digits, as written and as values), `numbers.states_value(text, value)`
(a metric's statement or a bullet states the value), `numbers.unsupported(text, sources)` (numbers no source states),
`raw.RawReader(workspace).text(raw_ref)` (the text of the raw record at an evidence item's `raw_ref`, such as a performance review's full text).

`rcore` imports only the standard library. `documents` imports `pypdf` or `python-docx` only when it reads a PDF or DOCX, so a script that reads those formats pins them in its PEP 723 block, at the versions `render.py` pins.
