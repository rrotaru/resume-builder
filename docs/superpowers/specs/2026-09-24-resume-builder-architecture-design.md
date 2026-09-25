# Resume Builder: Architecture Design

- **Date:** 2026-09-24
- **Status:** Approved
- **Scope:** Overall architecture: packaging, workspace layout, stage contracts, checkpoints, error handling and testing. Each subsystem gets its own follow-up spec (see [Follow-up specs](#follow-up-specs)).

## Goal

A plugin of agent skills that helps a software engineer build a resume from evidence of their work. It collects what they were assigned and shipped from source control and work tracking, reads performance feedback and an existing resume, identifies their most impactful projects and their role on each, and produces an ATS-friendly resume (PDF, DOCX, TXT) whose every claim traces back to a source.

## Decisions

| Topic | Decision |
|---|---|
| Packaging | Claude Code plugin. Skills follow the open Agent Skills format and use no Claude Code-only features, so other harnesses can load them. |
| Run model | Each run produces a new resume from scratch. Any stage can run on its own against earlier stages' output without re-collecting. Engineer decisions persist across runs. IDs are stable so incremental collection can be added later. |
| Confidentiality | Dedicated sanitize skill. The engineer approves generalizations, which are stored in `decisions/terms.json`. A script-enforced hard check at render blocks any denylisted term. |
| Data notice | Before collection, a one-time notice that work data (including performance reviews) is sent to the model provider. The engineer confirms before anything is pulled. |
| Claim provenance | Strict. Every bullet cites evidence IDs, confirmed metrics, the imported resume, or wizard answers. Render blocks unsourced bullets. The model may suggest metric *types* but never invents values. |
| Metric prompts | Only for the top N projects. `N = min(project_count, clamp(ceil(0.30 × project_count), 3, 8))`. Percent, floor and cap are configurable. Other projects use the non-numeric XYZ form. |
| v1 sources | GitHub, GitLab (connector or file export), local git repos (`git log`), Jira (connector or CSV/JSON export), and a folder of exported performance reviews (PDF/DOCX/TXT). |
| Resume import | PDF, DOCX, TXT, Markdown, JSON Resume. |
| Outputs | PDF (HTML template printed by Playwright/Chromium), DOCX (`python-docx`), plain text, and `stories.md` (STAR narratives per top project). |
| Tailoring | General resume: evidence-bound selection, ordering and rewording. Per-job versions (`--jd`): free rewriting, with a script flagging claims not supported by sources. Each flag must be accepted, reverted or edited before render. |
| Python | Every script runs via `uv run` with PEP 723 inline dependencies. Normalization and check scripts use only the standard library. Python ≥ 3.10. |
| Checkpoints | Four in the full workflow: confirm sources, review projects, wizard, final review. |
| Workspace | Folder of JSON/JSONL files, one folder per stage, plus a `decisions/` folder that regeneration never touches. |

## Plugin layout

```
resume-builder/
  .claude-plugin/
    plugin.json
    marketplace.json
  commands/                  # thin wrappers: build, init, collect, import, analyze,
                             # wizard, write, sanitize, ats, render
  skills/
    resume-core/             # workspace conventions, schemas, checks (shared)
      SKILL.md
      schemas/               # JSON Schema per stage file and decisions file
      scripts/               # validate.py, stage.py, check_sources.py, check_terms.py,
                             # check_flags.py, init_workspace.py
        rcore/               # shared stdlib-only library (ids, schema, stages, checks)
    resume-init/
    resume-collect/
      scripts/               # normalize_github.py, normalize_gitlab.py, normalize_jira.py,
                             # ingest_git_log.py, ingest_reviews.py, link.py
    resume-import/
      scripts/               # extract_text.py
    resume-analyze/
      scripts/               # signals.py, match_projects.py
    resume-sanitize/
    resume-wizard/
    resume-write/
    resume-ats/
      scripts/               # ats_lint.py, keywords.py, diff_claims.py
    resume-render/
      scripts/               # render.py
      templates/             # classic.html (v1: one single-column ATS-safe template)
    resume-build/            # full workflow orchestrator
  tests/
```

### Commands

Namespaced as `/resume-builder:<name>`. Each command file only passes arguments (`--workspace <path>`, `--jd <file>`, and so on) to the matching skill. All logic lives in skills, so other harnesses lose only the shortcuts. `/resume-builder:build` runs the full workflow.

### Portability rules

1. A skill uses only its own `SKILL.md`, `scripts/`, `references/`, `templates/`, and `../resume-core/`.
2. No hooks, subagents, `${CLAUDE_PLUGIN_ROOT}`, or other harness-specific constructs inside skills.
3. Skills read and write only inside the workspace (default `./resume-workspace`, overridable with `--workspace`).
4. Skills are installed as a set, because they share `resume-core` by relative path.
5. Each skill writes its stage through `resume-core/scripts/stage.py` (begin, then commit), which validates the files before swapping them into place. Validation does not depend on the harness.
6. Scripts in other skills may import the shared `rcore` library from `../resume-core/scripts/`.

A lint script in `tests/` enforces rules 1–2.

## Workspace

```
resume-workspace/
  config.json            # sources, usernames, time range, target role, top-N settings
  decisions/             # engineer-owned; never overwritten by regeneration
    terms.json
    projects.json
    metrics.json
    profile.json
    attestations.json
  01-raw/                # resume-collect: connector output as fetched, one JSONL per source
  02-evidence/           # resume-collect: normalized evidence.jsonl
  03-profile/            # resume-import: profile.json (JSON Resume)
  04-projects/           # resume-analyze: projects.json, signals.json
  05-terms/              # resume-sanitize scan: candidates.json
  06-bullets/            # resume-write: bullets.json, stories.md
  07-sanitized/          # resume-sanitize apply: bullets.json, profile.json, new-terms.json
  08-ats/
    general/             # resume.json, report.json
    jobs/<slug>/         # jd.txt, resume.json, report.json, flags.json
  out/
    general/             # resume.pdf, resume.docx, resume.txt
    jobs/<slug>/
    stories.md
```

**Ownership.** Each numbered folder is written by exactly one skill. `resume-wizard` writes only to `decisions/`. Checkpoints write engineer choices to `decisions/`.

**Stage metadata.** Every stage folder contains `_stage.json`:

```json
{"stage": "04-projects", "schema_version": 1, "created_at": "...",
 "inputs": {"02-evidence/evidence.jsonl": "sha256:...", "decisions/projects.json": "sha256:..."}}
```

A stage is **stale** when any recorded input hash no longer matches, an input is gone, or an input lives in a stage that is itself stale. `resume-build` uses this to offer reuse or rebuild. A standalone command warns before consuming stale inputs.

**Safe writes.** A stage writes to `<stage>.tmp/`, validates, then renames into place (the previous output is renamed to `<stage>.old/` and deleted after the swap). On failure the previous stage output remains intact. If a swap is interrupted, leaving `<stage>.old/` but no `<stage>/`, the next `begin`, `commit` or `status` renames `<stage>.old/` back. `stage.py begin <stage> --from-current` starts the tmp folder as a copy of the committed `<stage>/` (without `_stage.json`), so a skill can replace one part of a stage, such as one job's folder in `08-ats/jobs/`, and keep the rest. `stage.py commit` accepts only workspace-relative inputs (no absolute paths, no `..`, and not the workspace root itself: empty, `.` or any path resolving to it) and takes `--extra '<JSON object>'`, stored as `extra` in `_stage.json` (for example a skipped-row count).

**Privacy.** If the workspace is inside a git repository, `resume-init` adds it to the repository's `info/exclude` (special gitignore characters escaped). If the workspace is inside a repository but could not be excluded (it is the repository root, or git failed), it warns the engineer not to commit it.

## Data contracts

All files are JSON or JSONL and validated against `resume-core/schemas`.

### Evidence item (`02-evidence/evidence.jsonl`)

```json
{"id": "ev_3f9a1c2e", "source": "github", "kind": "pr",
 "native_key": "acme/payments#412", "url": "...", "title": "...",
 "excerpt": "first ~500 chars of body", "engineer_role": "author",
 "created_at": "...", "closed_at": "...", "state": "merged",
 "stats": {"additions": 812, "deletions": 140, "files": 23},
 "labels": [], "links": ["ev_77b0d4aa"], "raw_ref": "01-raw/github.jsonl:42"}
```

- `source`: `github | gitlab | git | jira | review`
- `kind`: `pr | mr | commit | review | issue | ticket | epic | perf_review`
- `engineer_role`: `author | reviewer | assignee | reporter | subject`
- `id` = `ev_` + first 8 hex chars of sha256(`source` + `:` + `native_key`), which is stable across re-collection. Collisions are detected and extended to 12 characters.
- `links`: related evidence. Examples: a PR to a Jira key (found in branch name, title or body), a ticket to its epic.

### Profile (`03-profile/profile.json`)

[JSON Resume](https://jsonresume.org/schema) with an added `x-sources` array on each entry (for example `["resume:/work/2"]`). Values in `decisions/profile.json` take precedence over imported values.

### Project (`04-projects/projects.json`)

```json
{"id": "pj_a1b2c3d4", "internal_name": "...", "summary": "...",
 "evidence_ids": ["ev_..."], "role": "lead", "scope": "cross-team",
 "start": "2025-02", "end": "2025-09", "rank": 1,
 "rank_reasons": ["..."], "metric_prompt": true}
```

- `role`: `lead | core | supporting`
- `scope`: `team | cross-team | org | company`
- **ID continuity.** A new project inherits a previous project's ID when their evidence sets have Jaccard similarity ≥ 0.5 (best match wins, one-to-one). New projects get fresh IDs. Decisions referencing an unmatched ID are shown as *orphaned* at checkpoint 2, to re-link or discard.

### Bullet (`06-bullets/bullets.json`, `07-sanitized/bullets.json`)

```json
{"id": "b_12", "project_id": "pj_a1b2c3d4", "work_ref": null,
 "text": "...", "form": "xyz_quantified",
 "sources": ["ev_3f9a1c2e", "metric:m_3"]}
```

- `form`: `xyz_quantified | xyz`
- Each `sources` entry is `ev_<id>`, `metric:<id>`, `resume:<json-pointer>` (into `03-profile/profile.json`), or `wizard:<json-pointer>` (into `decisions/profile.json`). A pointer must start with `/` and resolve to a single string or number, never an object, array, boolean or null.
- Bullets for earlier roles set `work_ref` (index into profile `work`) and cite `resume:` sources.

### Decisions

| File | Record |
|---|---|
| `terms.json` | `{term, replacement \| null, kind: codename\|customer\|product\|url\|financial\|other}`. `null` means allowed as-is. |
| `projects.json` | `{project_id, action: exclude\|merge\|split\|rename\|set_role\|set_scope, ...}` |
| `metrics.json` | `{id, project_id, value, unit, statement}` |
| `profile.json` | JSON Resume fragments supplied by the wizard |
| `attestations.json` | `{job_slug, bullet_id, text_sha256, action: accept\|edit}` |

An attestation applies only while the bullet's text hash matches, so any later edit to the bullet invalidates it.

### Tailored resume (`08-ats/.../resume.json`)

JSON Resume restricted to a closed list of sections, validated by `tailored-resume.schema.json` (profile files keep the open `resume.schema.json`):

- Top level: only `basics`, `work`, `projects`, `education`, `certificates` and `skills`. Any other section (for example `volunteer` or `awards`) fails validation.
- Each `work` and `projects` entry has an `x-highlights` array of `{bullet_id, text, sources}` (it may be empty), and `highlights` holds the same texts in the same order (JSON Resume highlights are plain strings, so the sourcing lives alongside them).
- `education`, `certificates` and `skills` entries carry no `highlights`.
- If `basics.summary` is present, `basics.x-summary-sources` must be present and non-empty; the source check treats the summary as a bullet with id `summary`.
- Every object is closed to an allowlist of fields (`additionalProperties: false`), so no unsourced claim can ride along in a field the checks do not read:
  - `basics`: `name`, `label`, `email`, `phone`, `url`, `location`, `profiles`, `summary`, `x-summary-sources`, `x-sources`; `location`: `address`, `postalCode`, `city`, `countryCode`, `region`; each `profiles` item: `network`, `username`, `url`.
  - `work` and `projects` entries: `name`, `position`, `url`, `location`, `startDate`, `endDate`, `highlights`, `x-highlights`, `x-sources`. There is no `summary` or `description`: claims belong in sourced highlights.
  - `education` entries: `institution`, `url`, `area`, `studyType`, `startDate`, `endDate`, `score`, `x-sources`.
  - `certificates` entries: `name`, `date`, `issuer`, `url`, `x-sources`.
  - `skills` entries: `name`, `level`, `keywords`, `x-sources`.
- `basics.label`, when present, must equal `config.json` `target_role` or `03-profile/profile.json` `basics.label`. The source check enforces this for tailored resumes and reports `<file>: basics.label must match the target role in config.json or the imported profile's label`.

This is the only input to rendering. `report.json` holds ATS lint results and keyword coverage.

`flags.json` (job versions only) is the claim diff's result:

```json
{"checked": {"b_1": "<text_sha256>", "b_2": "<text_sha256>"},
 "flags": [{"bullet_id": "b_1", "text": "...", "text_sha256": "...", "reasons": ["..."]}]}
```

`checked` holds the hash of every bullet the claim diff examined, flagged or not; `flags` lists rewrites whose claims are not supported by their sources. `check_flags.py` passes a bullet in the job's `resume.json` only if its current text hash is attested for that job, or it is unflagged and `checked` holds its current hash. A flagged bullet whose hash matches the flag must be accepted, reverted or edited. Any other bullet changed after the claim diff, which must be re-run. A flag or `checked` entry for a bullet no longer in `resume.json`, or a `bullet_id` used twice in one resume, is an error.

## Skills

The pattern: scripts handle anything that must be exact (parsing, IDs, checks); the model handles anything that needs judgment (grouping, role, wording).

### resume-init
Checks for `uv` and walks the engineer through installing it if missing. uv supplies Python ≥ 3.10 from each script's `requires-python`, so Python itself needs no separate check. Creates the workspace and default `config.json`. Chromium is installed lazily at first render.

### resume-collect (checkpoint 1)
- **Model:** identifies available connectors resembling GitHub, GitLab or Jira. Confirms with the engineer: sources, time range, usernames per system, local repo paths, review export folder, existing resume path, and the data notice. Pulls PRs/MRs, reviews, issues, tickets and epics via connectors into `01-raw/<source>.jsonl` as fetched.
- **Scripts:** `normalize_*.py` convert raw connector output *or* file exports into evidence. `ingest_git_log.py` reads local repos. `ingest_reviews.py` extracts text from review files. `link.py` connects items and removes duplicates.
- A source without a connector falls back to asking for an export path.

### resume-import
`extract_text.py` extracts text from PDF (`pypdf`), DOCX (`python-docx`), TXT or MD. JSON Resume is loaded directly. The model maps text into `03-profile/profile.json` with `x-sources`.

### resume-analyze (checkpoint 2)
- **Script:** `signals.py` computes per linked cluster: authored vs. reviewed counts, duration, repo and contributor counts, epic creation, first commit, and performance-review mentions.
- **Model:** groups evidence into projects, assigns role and scope from signals, ranks them, applies `decisions/projects.json`, and sets `metric_prompt` for the top N.
- **Script:** `match_projects.py` carries IDs forward from the previous run.
- **Checkpoint 2:** the engineer reviews grouping, role, scope and ranking (merge, split, rename, exclude, correct), and resolves orphaned decisions.

### resume-sanitize
- **Scan** (before the wizard): finds candidate sensitive terms in projects, evidence excerpts and the profile, and proposes generalizations into `05-terms/candidates.json`.
- **Apply** (after write): applies `decisions/terms.json` to bullets and profile, writing `07-sanitized/`. Newly detected terms go to `new-terms.json` for checkpoint 4.
- **Terms check** (`check_terms.py`, used here and by render) matches strictly. Terms and text are both normalized: Unicode NFKC, every format character (category `Cf`, which includes zero-width characters and the soft hyphen), the rest of the Default_Ignorable_Code_Point set (U+034F, U+115F–1160, U+17B4–17B5, U+180B–180F, U+3164, U+FE00–FE0F, U+FFA0, U+1BCA0–1BCA3, U+1D173–1D17A, U+E0000–E0FFF) and the Braille blank U+2800 removed, then case-folded. A term's words may be separated by any run of whitespace, `_`, dash punctuation (category `Pd`), U+2212 minus, `.`, `/`, `\`, U+00B7 middle dot, U+2215, U+2044, U+2027, U+2043, U+02D7, U+30FB or U+2022, or by nothing, so `Project Falcon` also matches `Project-Falcon`, `Project—Falcon`, `Project.Falcon`, `ProjectFalcon` and a term broken across a line. For terms of 5 or more characters (not counting separators) an optional plural `s`/`es` still matches (`Falcons`), but a longer word does not (`Falconry`); shorter terms get no plural, so `Rat` does not flag `rates`. Text files are scanned as one string and each match is reported with the line where it starts, counting lines as `str.splitlines()` does. The check fails closed: a missing or invalid `decisions/terms.json` is an error.
- **Allowed terms win.** An allowed term (`replacement: null`) exempts a denied match when the allowed term matches a span of the normalized text that fully contains the denied match. Allowed terms match literally: normalized and case-insensitive, whole-word, with no separator flexibility and no plural. So with `Check Point` denied and `checkpoint` allowed, "Added a checkpoint" passes and "Worked at Check Point" is still flagged. The engineer resolves a false positive by adding an allowed term or by rewording; the check itself is never weakened. Because allowed terms match literally, the engineer adds plural forms (`checkpoints`) as separate allowed terms. An allowed term may not equal a denied term or contain one as a whole word (both normalized, separator runs as single spaces): with `Contoso` denied, allowing `Contoso Bank` is an error in `decisions/terms.json`, so an allowed term can fix a false positive but never leak a denied name.
- **Known limits:** homoglyphs (for example a Cyrillic `о` in `Cоntoso`) are not detected by the terms check. The engineer's review at checkpoint 4 is the backstop. An allowed term that joins a denied term's words or adds a plural (`ContosoBank` or `contoso-banks` allowed beside denied `Contoso Bank`) exempts every literal use of itself, so it could let the denied name through; `check_terms.py` prints a notice for each such pair and the engineer confirms at checkpoint 4 that it is a different word. Besides that, `work[].position`, `basics.name`, `certificates[].name` and `skills[].keywords` are free strings that the source check does not verify; the resume-ats and resume-render specs must constrain them (`position` must match the imported profile or the wizard answers).

### resume-wizard (checkpoint 3)
A single session for: metric values for `metric_prompt` projects, missing profile fields (contact details, dates, education), and term approvals from `05-terms/candidates.json`. Writes only to `decisions/`. Skips items already answered in earlier runs.

### resume-write
Writes XYZ bullets per project: `xyz_quantified` when a confirmed metric exists, otherwise `xyz`. Writes STAR stories for top-N projects to `06-bullets/stories.md` using the same sources. Earlier roles' bullets come from the imported resume. Every bullet has a non-empty `sources`.

### resume-ats
- **General:** selects and orders bullets and projects, normalizes section headings and date formats, and enforces length (1 page under about 8 years of experience, else 2). Keywords come from the target role in `config.json`. Wording changes must stay supported by the cited sources.
- **Per job (`--jd <file>`):** free rewriting against the posting. `diff_claims.py` compares each rewrite with its original bullet and sources, records every examined bullet's text hash in `flags.json` `checked`, and flags any skill, technology, number or scope not present in them. To rebuild one job, begin `08-ats` with `--from-current` and replace only that job's folder. `keywords.py` reports posting terms: covered, missing with evidence, missing without evidence.
- `ats_lint.py` handles the checks that don't need judgment (headings, dates, no tables or columns in the template).

### resume-render
1. Runs `check_terms.py`, `check_sources.py`, and (for job versions) `check_flags.py`. Any failure means no output, and a list of failing records with the command that fixes each.
2. Fills `templates/classic.html` and prints the PDF via Playwright/Chromium. Builds the DOCX via `python-docx` with the same section order, and the TXT. Renders only the tailored resume's sections (`basics`, `work`, `projects`, `education`, `certificates`, `skills`); `highlights` render only for `work` and `projects`, and the summary only when it is sourced.
3. Copies `stories.md` to `out/`.

If Chromium is unavailable, offers to install it. DOCX and TXT still render without it.

### resume-build
Orchestrates the full run and offers to reuse any fresh stage:

```
init → collect [CP1] → import → analyze [CP2] → sanitize scan
     → wizard [CP3] → write → sanitize apply → ats (general + each --jd)
     → [CP4: bullets, ATS reports, job flags, new terms] → render
```

Every checkpoint persists its choices to `decisions/`, so an interrupted run resumes where it stopped.

## Error handling

| Case | Behavior |
|---|---|
| Stage fails midway | `<stage>.tmp/` discarded; previous output intact. An interrupted swap is undone by the next `begin`, `commit` or `status`. |
| Validation fails | Names file, record ID and rule. Skills never skip or weaken a check. |
| No connector for a source | Ask for an export path or skip. Recorded in `config.json`. |
| Connector fails partway | Keep fetched pages in `01-raw/<source>.partial.jsonl` with a cursor. Offer retry, continue without the source, or pause. |
| Username yields no results | Show the query used, ask for an alternate username or email, never guess. |
| Malformed export rows | Report the first 10 bad rows with line numbers, process the rest, record the skipped count in `_stage.json`. |
| Scanned PDF without text | Explain, and ask for DOCX, TXT or pasted text. No OCR in v1. |
| Stale stages | List them and offer to rebuild in dependency order. |
| Orphaned project decisions | Presented at checkpoint 2 to re-link or discard. |
| Render check fails | No output files. Failing records listed with the fixing command. |

## Testing

- **Script unit tests** (pytest via `uv run`): each normalizer against sample GitHub, GitLab and Jira data (connector-shaped and export-shaped, made-up content); ID stability; linking and de-duplication; `signals.py`; `match_projects.py`; each check with deliberately broken inputs (missing source, leftover term, edited attested bullet).
- **Contract tests:** every fixture validates against `resume-core/schemas`, and each stage's fixture output is valid input for the next stage.
- **Render tests:** render a fixture `resume.json` to PDF, extract its text with `pypdf`, and assert section order and bullet text survive (checks ATS readability). Assert the DOCX opens. Compare TXT against a saved copy.
- **End-to-end fixture:** `tests/fixtures/workspace/` holds a made-up engineer. CI runs all script-only steps (normalize → signals → checks → render), with saved outputs standing in for model-driven stages.
- **Skill lint:** validates `SKILL.md` front matter and enforces the portability rules.
- **Model-quality evals:** a small evaluation set for grouping, role assignment and bullet wording, run manually or on a schedule. Not in CI, since model output varies.

## Out of scope for v1

- Incremental collection. The design keeps stable IDs so it can be added later.
- Other sources: Bitbucket, Linear, Asana, Azure DevOps, HRIS/performance platform connectors.
- LinkedIn data export import.
- OCR of scanned PDFs.
- More than one resume template.
- Cover letters. `stories.md` is the only narrative output.
- Non-English resumes.

## Follow-up specs

Each gets its own spec → plan → implementation cycle, in this order. Render comes early so the pipeline produces a real document from fixtures as soon as possible.

1. **resume-core** and **resume-init:** schemas, the `rcore` library, `validate.py`, `stage.py`, the three checks, workspace creation, fixture workspace, skill lint, CI.
2. **resume-render:** template, PDF/DOCX/TXT output, render tests.
3. **resume-import:** text extraction and profile mapping.
4. **resume-collect:** connector discovery, normalizers, git log, reviews, linking.
5. **resume-analyze:** signals, grouping, role and scope, ranking, ID continuity.
6. **resume-sanitize** and **resume-wizard.**
7. **resume-write:** XYZ bullets and STAR stories.
8. **resume-ats:** lint, keywords, per-job tailoring and claim diffing.
9. **resume-build** and **commands:** orchestration, staleness, checkpoints; plugin manifest and marketplace.
