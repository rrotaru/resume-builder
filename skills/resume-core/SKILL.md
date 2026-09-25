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
  config.json      decisions/ (terms, projects, metrics, profile, attestations)
  01-raw/  02-evidence/  03-profile/  04-projects/  05-terms/
  06-bullets/  07-sanitized/  08-ats/  out/
```

- Each numbered folder is a **stage**, written by exactly one skill.
- `decisions/` holds the engineer's choices. Only the wizard and checkpoints write to it; regenerating a stage never touches it.
- Never edit another skill's stage folder.

## Writing a stage

1. `uv run ../resume-core/scripts/stage.py --workspace WS begin <stage>` creates an empty `<stage>.tmp/` and prints its path.
   To change only part of a stage (for example one job's folder in `08-ats/jobs/`), add `--from-current`:
   the tmp folder then starts as a copy of the committed `<stage>/` (without `_stage.json`), so the parts you do not rewrite are kept.
2. Write every output file into that folder.
3. `uv run ../resume-core/scripts/stage.py --workspace WS commit <stage> --inputs <each file or folder you read>`
   records input hashes, validates the folder, and swaps it into place.
   Inputs must be workspace-relative (no absolute paths, no `..`).
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

## Tailored resumes and job flags

- `08-ats/general/resume.json` and `08-ats/jobs/<slug>/resume.json` follow `schemas/tailored-resume.schema.json`. Only the sections `basics`, `work`, `projects`, `education`, `certificates` and `skills` are allowed. Every `work` and `projects` entry has `x-highlights` (`{bullet_id, text, sources}`, possibly empty) and `highlights` holding the same texts in order. Other sections carry no `highlights`. A `basics.summary` needs a non-empty `basics.x-summary-sources`.
- `08-ats/jobs/<slug>/flags.json` is `{"checked": {"<bullet_id>": "<text_sha256>"}, "flags": [...]}`. The claim diff records in `checked` the hash of every bullet it examined, flagged or not, and lists unsupported claims in `flags`.

## Checks

| Script | Fails when |
|---|---|
| `validate.py [PATH ...]` | a file does not match its schema in `schemas/`, or an array has duplicate `id`s |
| `check_sources.py FILE ...` | a bullet (or a resume's `summary`) has no sources or cites one that does not resolve; a resume's `highlights` differ from its `x-highlights` texts; `education`, `certificates` or `skills` carry `highlights` |
| `check_terms.py FILE ...` | text contains a term from `decisions/terms.json` whose `replacement` is not null, or `decisions/terms.json` is missing or invalid |
| `check_flags.py JOB ...` | a bullet in `08-ats/jobs/<JOB>/resume.json` is flagged with no matching attestation, or changed after the claim diff, or a flag names a bullet that is gone |

Each prints one line per problem (file, record and rule) and exits 1 on failure. A missing, non-UTF-8 or invalid-JSON file is reported as a problem line, not a crash.

The terms check is strict: it matches after Unicode NFKC normalization, removal of zero-width characters and case folding; the words of a term may be joined by spaces, hyphens, underscores, line breaks or nothing; and a plural `s`/`es` still matches. So `Project-Falcon`, `ProjectFalcon` and `Falcons` are all caught.

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
`wsio.read_json / write_json / read_jsonl / write_jsonl / resolve_pointer`.
