---
name: resume-core
description: Workspace rules, data formats and hard checks shared by every resume-builder skill. Use when another resume-builder skill says to follow resume-core, or when validating a resume workspace, checking bullet sources, checking for confidential terms, checking job-version flags, or reporting which stages are stale.
---

# resume-core

Shared conventions for resume-builder skills. Other skills refer to this folder as `../resume-core/`.
Run every script with `uv run`. Each one takes `--workspace` (default `resume-workspace`).

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
2. Write every output file into that folder.
3. `uv run ../resume-core/scripts/stage.py --workspace WS commit <stage> --inputs <each file or folder you read>`
   records input hashes, validates the folder, and swaps it into place.
4. If commit prints errors, fix the named records and commit again. The previous output stays in place until a commit succeeds. Never skip or weaken a check.

`stage.py --workspace WS status` prints each stage as `missing`, `fresh` or `stale`. Before reading a stale stage, tell the engineer and offer to rebuild it.

## Source references

Every bullet's `sources` list holds one or more of:

| Reference | Resolves against |
|---|---|
| `ev_<8 or 12 hex>` | `02-evidence/evidence.jsonl` |
| `metric:<id>` | `decisions/metrics.json` |
| `resume:<JSON Pointer>` | `03-profile/profile.json`, e.g. `resume:/work/1/highlights/0` |
| `wizard:<JSON Pointer>` | `decisions/profile.json`, e.g. `wizard:/basics/email` |

## Checks

| Script | Fails when |
|---|---|
| `validate.py [PATH ...]` | a file does not match its schema in `schemas/`, or an array has duplicate `id`s |
| `check_sources.py FILE ...` | a bullet has no sources or cites one that does not resolve; a resume's `highlights` differ from its `x-highlights` texts |
| `check_terms.py FILE ...` | text contains a term from `decisions/terms.json` whose `replacement` is not null |
| `check_flags.py JOB ...` | a flagged rewrite in `08-ats/jobs/<JOB>/flags.json` has no matching attestation for its current text |

Each prints one line per problem (file, record and rule) and exits 1 on failure.

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
