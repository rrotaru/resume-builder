# resume-render: Design

- **Date:** 2026-09-25
- **Status:** Approved
- **Scope:** The `resume-render` skill: the checks it runs before writing anything, the HTML template, and PDF, DOCX and plain-text output. Also the resume-core changes render needs to close three gaps resume-core left open. Follow-up spec 2 of the [architecture spec](2026-09-24-resume-builder-architecture-design.md).

## Goal

Turn each tailored resume in `08-ats/` into a PDF, a DOCX and a plain-text file. An ATS must be able to parse each file, and each file must contain only what the checks passed. If any check fails, render writes nothing and lists each failing record with the command that fixes it.

## Gaps from resume-core

Each gap below was reproduced on a copy of `tests/fixtures/workspace/`.

1. **Fact fields are unchecked.** The checks verify bullets, the summary and `basics.label`, and nothing else. In `08-ats/jobs/fintech-sre/resume.json`, setting `work[0].position` to `CTO` and `education[0].studyType` to `PhD` and adding `Kubernetes` to `skills[0].keywords` passes `check_sources.py`, `check_terms.py` and `check_flags.py`. The architecture spec names four such fields (`work[].position`, `basics.name`, `certificates[].name`, `skills[].keywords`). Every other non-bullet field has the same hole: employer, dates, degree, institution, issuer, skill level and contact details.
2. **Only the schema enforces the section list.** A top-level `awards` section passes `check_sources.py` and `check_terms.py`. Only `validate.py` rejects it. A renderer that walks the JSON would print it.
3. **The checks assume a schema-valid file.** With `"work": ["Staff Engineer at Google"]`, `check_sources.py` exits with a traceback (`AttributeError: 'str' object has no attribute 'get'`) instead of a problem line. `validate.py` reports it properly as `$.work[0]: expected object, got str`.

[Gate order](#gate-order) closes gap 3, [Fact fields](#fact-fields) closes gap 1 and [Render model](#render-model) closes gap 2.

## Decisions

| Topic | Decision |
|---|---|
| Where the checks run | `render.py` runs them in-process through `rcore` before it renders, so the model cannot produce output that skips them. `--check` runs them without rendering. |
| Check order | Validation first, and nothing else runs if it fails. Then the source, terms and flags checks all run, and every failure is reported together. |
| Fact fields | Every tailored-resume field that is not a sourced bullet must be copied from the engineer's profile (the imported profile with wizard answers laid over it). Dates may be shortened. Nothing else may change. `check_sources.py` enforces this, so resume-ats gets the same rule. |
| Entry `x-sources` | Removed from the tailored-resume schema. Fact fields are verified by value, so a pointer list adds nothing, and today no check reads it. |
| Confidential fact fields | Sanitize does not rewrite fact fields. A denied term in one, such as a codename used as a project name, is replaced by a wizard answer in `decisions/profile.json` at that path. |
| Sections | Fixed list, fixed order. The renderer copies named fields into its own model and never iterates over the resume's keys. |
| Targets | Every tailored resume in `08-ats/` by default. `--target` narrows the set. `out/` always holds exactly the targets of the last render. |
| Template | One single-column HTML template, Jinja2 with autoescaping, self-contained (inline CSS, embedded font). |
| Font | Carlito (SIL OFL 1.1, same metrics as Calibri) is bundled for the PDF. The DOCX names Calibri. Layout and page count are the same on every machine. |
| PDF | Playwright Chromium with JavaScript off and every network request blocked. US Letter by default, `--paper a4` for A4. |
| Output check | After rendering, the text extracted from each PDF, DOCX and TXT must contain every heading and bullet in order and must pass the terms check. |
| Stories | Copied from `07-sanitized/stories.md`, which sanitize apply must write. `06-bullets/stories.md` is never copied because it is written before sanitizing. |
| No Chromium | Exit code 3, nothing written, when Chromium is missing or does not start. The skill offers `render.py --install-browser`, or `--no-pdf` to write DOCX and TXT only. |

## Skill layout

```
skills/resume-render/
  SKILL.md
  scripts/
    render.py              # CLI: gate, render, output check, stage commit
    rrender/               # gate.py, model.py, dates.py, txt.py, html.py, pdf.py, docx.py, outcheck.py
  templates/
    classic.html
    fonts/                 # Carlito Regular and Bold (WOFF2), OFL.txt
skills/resume-core/scripts/rcore/
  profile.py               # new: effective profile
  facts.py                 # new: fact-field rules, called from sources.check_resume
```

`render.py` declares pinned `jinja2`, `playwright`, `python-docx` and `pypdf` in its PEP 723 block. It imports `rcore` as portability rule 6 allows. The check code stays standard-library only, and so do `gate.py`, `model.py`, `dates.py`, `txt.py` and `outcheck.py`, so their tests run without the render dependencies.

## Command line

```
uv run scripts/render.py --workspace WS [--target general|<slug>]... [--paper letter|a4] [--no-pdf] [--check]
uv run scripts/render.py --install-browser [--with-deps]
```

| Exit | Meaning |
|---|---|
| 0 | Rendered, or `--check` passed |
| 1 | A check failed, or there is nothing to render. Nothing written. |
| 2 | Usage error |
| 3 | Chromium is not installed or did not start. Nothing written. |

Target `general` is `08-ats/general/resume.json`. Target `<slug>` is `08-ats/jobs/<slug>/resume.json`. Without `--target`, render takes `general` if that file exists, plus every folder in `08-ats/jobs/`. With no targets it exits 1 with `nothing to render; run /resume-builder:ats`. A job folder missing `resume.json` or `flags.json` fails the gate, so a half-built job version is never skipped silently.

## Pipeline

1. Hash every input with `stages.hash_path`.
2. Run the gate. On any failure, print it and exit 1.
3. `stages.begin(ws, "out")`, never with `from_current`. `out/` then holds only this render's targets, and each one passed the gate against the inputs recorded in `_stage.json`.
4. For each target, build the render model and write `resume.txt`, `resume.docx` and `resume.pdf` to `out.tmp/general/` or `out.tmp/jobs/<slug>/`.
5. Copy stories (see [Stories](#stories)).
6. Run the output check.
7. Hash the inputs again. If any changed, delete `out.tmp/` and exit 1 with `inputs changed during render; run render again`.
8. `stages.commit(ws, "out", inputs, extra={"targets": [...], "pdf": true, "pages": {"general": 1, ...}, "stories": true})`.

Inputs are each target's `resume.json` (and `flags.json` for jobs), plus each of these that exists: `config.json`, `decisions/terms.json`, `decisions/profile.json`, `decisions/metrics.json`, `decisions/attestations.json`, `02-evidence/evidence.jsonl`, `03-profile/profile.json` and `07-sanitized/stories.md`. `commit` rejects inputs that do not exist, so missing optional files are left out.

On any failure the previous `out/` stays as it was. `stage.py status` reports it stale if its inputs have changed since.

## Gate order

The gate runs in this order. Each line it prints is the line the standalone script would print, followed by an indented `fix:` line.

1. **Validate.** `validation.validate_paths` on each target's `resume.json` and each job's `flags.json`, and on each file the later checks read that exists (the optional inputs listed under [Pipeline](#pipeline), minus `stories.md`, which has no schema). The target files are always named, so a missing one is reported as `not found`. **If validation reports anything, the gate stops.** On a schema-invalid file the later checks can crash (gap 3), or their output hides the real problem.
2. **Render preconditions.** Each target has a non-empty `basics.name`. The schema does not require it, but a resume without a name cannot be rendered.
3. **Sources**, now including fact fields: `sources.check_file` on each target.
4. **Terms**: `terms.check_file` on each target, and on `07-sanitized/stories.md` if it exists. Allowed-term notices go to stderr as in `check_terms.py`. The skill shows each one to the engineer.
5. **Flags**: `flags.check_job` on each job target.

Steps 2 to 5 always all run, and their failures are printed together, grouped by target, so one render shows every problem.

| Failure | Fix line |
|---|---|
| Validation of a tailored resume or `flags.json` | `/resume-builder:ats` for that version |
| Validation of any other file | The command that writes it: `/resume-builder:wizard` for `decisions/`, `/resume-builder:import` for `03-profile/`, `/resume-builder:collect` for `02-evidence/` and `config.json` sources |
| Missing `basics.name` | `/resume-builder:wizard` to add the name, then `/resume-builder:ats` |
| Bullet or summary source | `/resume-builder:ats`. If the bullet itself is wrong, `/resume-builder:write` first. |
| Fact field | `/resume-builder:ats` to copy the profile value. If the profile is wrong, `/resume-builder:wizard` first. |
| Denied term in a bullet or summary | `/resume-builder:sanitize`, then `/resume-builder:ats`. For a false positive, an allowed term the engineer agrees to. |
| Denied term in a fact field | `/resume-builder:wizard` to set a replacement value at that path, then `/resume-builder:ats` |
| Flagged bullet | Accept, revert or edit it at checkpoint 4 (`/resume-builder:build` resumes there) |
| Bullet changed after the claim diff | `/resume-builder:ats --jd <file>` for that job |

## Fact fields

### Effective profile

`profile.effective_profile(workspace)` returns `03-profile/profile.json` with `decisions/profile.json` laid over it. This pins down the architecture's rule that "values in `decisions/profile.json` take precedence over imported values":

- Two objects merge key by key.
- Two arrays whose items are all objects merge by index. Wizard item *i* merges onto imported item *i*, and wizard items past the end of the imported array are added. An empty object leaves its imported item unchanged, so `"work": [{}, {"endDate": "2022-12"}]` fills in the second job's end date.
- Two other arrays (such as `keywords`) combine: imported items first, then wizard items not already present.
- In every other case the wizard's value replaces the imported one.
- A missing file counts as `{}`.

The resume-wizard spec must write fragments that follow these rules. `wizard:` source references still point into the raw `decisions/profile.json`. Only the fact-field rules and `basics.label` use the effective profile.

### Rules

Each field the tailored-resume schema allows is one of three kinds:

- Bullets: `basics.summary`, and `highlights` and `x-highlights[].text` in `work` and `projects`. The source and flags checks already cover these.
- Source metadata: `basics.x-summary-sources`, `x-highlights[].bullet_id` and `x-highlights[].sources`.
- Fact fields: everything else.

A tailored resume (any resume path except the three profile files, as today) must meet these rules:

- In `basics`, `name`, `email`, `phone` and `url` each equal the effective `basics` value when present. Each `location` key present equals the same key of the effective `basics.location`. Each `profiles` item equals some effective `basics.profiles` item in every field it has. `label` keeps its current rule, but compares against `config.json` `target_role` or the effective `basics.label`, so a wizard correction counts.
- Each entry in `work`, `projects`, `education`, `certificates` and `skills` matches one entry P in the same section of the effective profile:
  - Every fact field the entry has, P has too, with the same value.
  - A date (`startDate`, `endDate`, `date`) may be shortened: `2023-01-15` may appear as `2023-01` or `2023`. It may not be lengthened.
  - The entry has a date field exactly when P has it. Otherwise dropping `endDate` would make a past job render as "Present".
  - `keywords` holds only items from P's `keywords`, in any order.
  - Other fact fields may be left out.

All fields of one entry must match the same P, so a title cannot move from one job to another. Values compare as exact strings, including case, spacing and punctuation. For a different wording, such as `Sr.` for `Senior` or `Postgres` for `PostgreSQL`, the engineer records it through the wizard.

The fixture's tailored resumes pass these rules once `x-sources` is removed from them.

### Error lines

The closest profile entry is the one with the fewest differences, taking the lowest index on a tie. Each difference gets its own line:

```
08-ats/jobs/fintech-sre/resume.json: /work/0: position 'CTO' does not match the profile (closest entry /work/0 has 'Senior Software Engineer')
08-ats/jobs/fintech-sre/resume.json: /education/0: studyType 'PhD' does not match the profile (closest entry /education/0 has 'BS')
08-ats/jobs/fintech-sre/resume.json: /skills/0: keyword 'Kubernetes' is not in the profile (closest entry /skills/0)
08-ats/general/resume.json: /work/1: endDate is missing (closest entry /work/1 has '2022-12')
08-ats/general/resume.json: /certificates/0: the profile has no certificates entries
08-ats/general/resume.json: /basics/name: 'J. Rivera' does not match the profile ('Jordan Rivera')
```

### Confidential values

If a fact field holds a denied term, the terms check fails on it. The fix is a wizard answer at that path, for example `"projects": [{"name": "Fraud-detection platform"}]` in `decisions/profile.json`, which then becomes the effective value. Sanitize apply leaves fact fields in `07-sanitized/profile.json` unchanged for two reasons. Term replacements are written for prose ("a top-10 US bank") and read wrongly as a name. And the fact-field rules would reject a value that cannot be traced to the profile.

### What the check does not prove

It proves that a fact came from the profile. It does not prove the profile is right. `03-profile/profile.json` is the model's reading of the imported resume. resume-import must keep that reading faithful, and the engineer reviews the output at checkpoint 4. `basics.label` may still be the target role, which the engineer sets in `config.json`.

## Render model

Render never passes the tailored resume to a writer. `rrender/model.py` builds a render model by copying named fields from named sections. The HTML, DOCX and TXT writers read only that model. A section or field missing from this table never reaches the page, even if the gate were bypassed.

| Order | Heading | From | Rendered | Not rendered |
|---|---|---|---|---|
| 1 | none (header) | `basics` | `name`, `label`, `email`, `phone`, `url`; `location` `city`, `region`, `countryCode`; each `profiles` item as its `url`, or as `network: username` when it has no URL | `location.address`, `location.postalCode` |
| 2 | Summary | `basics` | `summary`, only when `x-summary-sources` is a non-empty list | |
| 3 | Experience | `work` | `position`, `name`, `location`, dates, `x-highlights[].text` | `url`, `highlights` |
| 4 | Projects | `projects` | `name`, `position`, `url`, dates, `x-highlights[].text` | `location`, `highlights` |
| 5 | Skills | `skills` | `name`, `keywords` | `level` |
| 6 | Education | `education` | `studyType`, `area`, `institution`, dates, `score` | `url` |
| 7 | Certifications | `certificates` | `name`, `issuer`, `date`, `url` | |

Source metadata (`x-summary-sources`, `bullet_id`, `sources`) is never rendered.

- Bullets come from `x-highlights[].text`, which is the text the source, terms and flags checks read. `highlights` must equal it (the source check enforces that), and render does not read `highlights`.
- A section with no entries gets no heading. Entries keep the order resume-ats chose.
- Dates: `2023-01` and `2023-01-15` render as `Jan 2023`, and `2019` as `2019`. Ranges read `Jan 2023 – Present` in PDF and DOCX, and `Jan 2023 - Present` in TXT. A `work`, `projects` or `education` entry with a start date and no end date renders as ongoing ("Present"), matching the profile's meaning.
- Only `http://`, `https://` and `mailto:` URLs become links. Any other scheme renders as plain text. Link text is always the visible URL, because an ATS reads text and ignores link targets.
- Render writes no text the reader cannot see: no keywords in PDF or DOCX metadata, no hidden or white text, nothing in page headers or footers. Metadata holds only the title (`<name> resume`) and the author (`<name>`).
- A test lists every property in `tailored-resume.schema.json` and fails if one is in neither the rendered nor the not-rendered column. A new schema field therefore needs a rendering decision before it ships.

## Output formats

### HTML and PDF

- `templates/classic.html` uses Jinja2 with autoescaping and `StrictUndefined`. The layout is one column with no tables, images, icons or CSS columns, all of which break ATS parsing. Section headings are `h2` elements holding the fixed texts above. Bullets are `ul`/`li`.
- The CSS turns off ligatures and automatic hyphenation (`font-variant-ligatures: none; hyphens: manual`) and aligns text left, so the PDF text layer holds whole, exact words. Bullets and entry headers use `break-inside: avoid`, and headings stay with the line after them.
- The page is self-contained: CSS inline, Carlito embedded as `data:` URIs. Render loads it with `page.set_content`, with JavaScript disabled and every request aborted through `page.route`. A resume cannot make the renderer fetch anything.
- `page.pdf` prints at US Letter or A4 with 0.6 in margins. pypdf reads the page count back. Render reports it and warns above two pages. resume-ats owns the length rule.

### DOCX

python-docx writes the same order and text as the render model. The name is a bold paragraph at the top of the body, not in a page header. Section headings use the built-in `Heading 1` style and bullets use `List Bullet`. There are no tables, text boxes, headers or footers. Text is Calibri 10.5 pt. Core properties hold only the title and author.

### Plain text

UTF-8 with LF line endings, one line per bullet and no wrapping. Headings are in capitals. The renderer's own punctuation is ASCII: ` - ` in date ranges, ` | ` between contact items and `- ` before bullets. Content keeps its own characters. The output is deterministic, so tests compare it byte for byte with a saved copy. For the fixture's general resume (`tests/fixtures/render/general.txt`):

```
Jordan Rivera
Senior Backend Engineer
jordan.rivera@example.com | https://github.com/jrivera | Denver, CO

EXPERIENCE

Senior Software Engineer, Northwind Payments
Jan 2023 - Present
- Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency cache in Go
- Mentored two new engineers through on-call onboarding

Software Engineer, Tailspin Toys
Jun 2019 - Dec 2022
- Migrated the order service from PHP to Go, serving 2M requests per day

PROJECTS

ledger-lint
Apr 2021 - Present | https://github.com/jrivera/ledger-lint
- Built ledger-lint, an open-source linter for double-entry ledger files with 300 GitHub stars

SKILLS

Backend: Go, Python, Redis, PostgreSQL

EDUCATION

BS, Computer Science, State University
2019

CERTIFICATIONS

AWS Certified Solutions Architect - Associate, Amazon Web Services
May 2024
```

## Output check

Before committing, render checks each target's three files:

1. It extracts the text of the PDF with pypdf and of the DOCX with python-docx, and reads the TXT. The comparison ignores whitespace and case, so line wrapping in the PDF and capital headings in the TXT do not matter.
2. The name, every heading and every bullet in the render model must appear in each text, in model order. A miss means the PDF text layer or the DOCX lost text an ATS needs. Render fails and names the target, file and missing text.
3. `terms.scan_text` runs on each extracted text. This catches text the renderer adds itself (headings, month names, "Present"), and anything a writer bug introduces.

## Stories

resume-write writes `stories.md` into `06-bullets/`, before sanitize apply, so it can hold codenames. The fixture's evidence, for one, mentions `Project Falcon`. Render copies `07-sanitized/stories.md` to `out/stories.md` after the terms check passes on it. This requires sanitize apply to write `07-sanitized/stories.md`. If that file does not exist, render skips stories and says so. It never falls back to `06-bullets/stories.md`. Stories cite no per-sentence sources, so they get the terms check but no source check. The engineer reviews them at checkpoint 4.

## Chromium

Before rendering, `render.py` launches Chromium once (skipped with `--no-pdf` or `--check`). If Playwright cannot find it, or it does not start, render exits 3 before writing anything. The skill tells the engineer that installing downloads about 150 MB into Playwright's cache outside the workspace, then offers two choices:

- `render.py --install-browser` runs `python -m playwright install chromium` in the script's own environment, so the browser build matches the pinned Playwright version. `--with-deps` also installs the Linux system libraries (CI uses it).
- `render.py --no-pdf` writes DOCX and TXT only, and records `"pdf": false` in `_stage.json` `extra`. The output check then covers those two files.

Playwright honors `PLAYWRIGHT_BROWSERS_PATH`. If Chromium is installed but fails to launch, render prints Playwright's error with a hint to try `--with-deps`. The pinned Playwright is 1.56.0 (Chromium build 1194); moving the pin also moves the browser build `--install-browser` fetches.

## SKILL.md

1. Run `stage.py status`. If `08-ats` is missing, stop and suggest `/resume-builder:ats`. If it is stale, tell the engineer and offer to rebuild it first. Render does not block on staleness, because the gate decides.
2. Run `render.py`. On exit 1, show every failing line with its `fix:` line and stop. Never edit a stage folder or `decisions/` to make a check pass.
3. On exit 3, offer to install Chromium or render without PDF, as described above.
4. Show every allowed-term notice and ask the engineer to confirm that each allowed term is a different word.
5. Report the files written, the page count of each PDF, and whether stories were copied.

## Changes to resume-core and the architecture spec

The render implementation plan makes these changes, with tests:

1. Adds `rcore/profile.py` and `rcore/facts.py`. `sources.check_resume` applies the fact-field rules to tailored resumes, and compares `basics.label` against the effective label.
2. `sources.check_file` validates a resume against its schema before checking it. An invalid resume gives the line `<file>: does not match its schema; run validate.py` instead of a traceback, so `check_sources.py` is safe to run on its own.
3. Removes `x-sources` from `basics` and every entry type in `tailored-resume.schema.json`, and from the fixture's tailored resumes.
4. Adds a `projects` entry, a `certificates` entry (a wizard answer) and a `basics.profiles` item to the fixture profile and tailored resumes, plus `07-sanitized/stories.md` and an unsanitized `06-bullets/stories.md`, so the render tests cover every section and the stories rule.
5. resume-core `SKILL.md` adds fact fields to the `check_sources.py` row of its checks table.
6. In the architecture spec:
   - The known-limits sentence about free strings points to this spec.
   - `07-sanitized/` gains `stories.md`.
   - Sanitize apply leaves profile fact fields unchanged.
   - Wizard fragments follow the overlay rules.
   - The resume-render section points to this spec.

## Error handling

| Case | Behavior |
|---|---|
| Validation fails | Validation lines with fixes. Later checks do not run. Nothing written. |
| Source, terms or flags check fails | Every failure from the three checks, grouped by target, each with its fix. Nothing written. |
| Nothing to render | Exit 1 with a pointer to `/resume-builder:ats`. |
| Chromium missing | Exit 3. Nothing written. The skill offers to install or to use `--no-pdf`. |
| Output check fails | `out.tmp/` deleted. Lines name the target, file, and missing text or denied term. |
| Inputs change during render | `out.tmp/` deleted. Run render again. |

The previous `out/` survives every failure.

## Testing

- **resume-core unit tests** (standard library only):
  - Overlay rules: object merge, index merge with `{}`, appended entries, keyword union, scalar override, missing file.
  - Rejected fact fields: `CTO`, `PhD`, `Kubernetes`, a changed employer, a start date moved earlier, a title moved from another job, a dropped `endDate`, a date finer than the profile's, a certificate when the profile has none.
  - Accepted fact fields: a shortened date, reordered entries, a reordered subset of keywords.
  - A wizard value beats the imported one, and the imported value then fails.
  - Profile files stay exempt.
  - A schema-invalid resume gives a problem line, not a traceback.
- **Render model:**
  - An unknown section and an unknown field, injected past validation, appear in none of the three outputs.
  - A summary without sources is not rendered.
  - A `javascript:` URL renders as plain text.
  - `<`, `>` and `&` in a bullet appear as literal text in the PDF.
  - The schema drift test.
- **Gate:**
  - An `awards` section produces only the validation line, exit 1, and an untouched `out/`.
  - Failures from the source, terms and flags checks all print in one run.
  - `--check` writes nothing.
- **Rendering** (needs Chromium):
  - For the fixture's general and job resumes, the PDF text holds the headings in order and every bullet.
  - The DOCX opens, uses `Heading 1` and `List Bullet`, and keeps the same order.
  - The TXT equals the saved copy.
  - A resume with an `https://` URL causes no network request (counted in the route handler).
  - Page counts appear in `_stage.json`.
- **No Chromium:** with `PLAYWRIGHT_BROWSERS_PATH` pointing at an empty folder, render exits 3 and writes nothing, and `--no-pdf` writes DOCX and TXT.
- **CI** runs `render.py --install-browser --with-deps`, then `uv run --with pytest --with-requirements skills/resume-render/scripts/render.py pytest`, which takes the render dependencies from `render.py`'s inline metadata. Chromium tests carry a `chromium` marker. Without the dependencies or Chromium, the render tests skip locally and fail in CI (`CI` is set).

## Out of scope for v1

- Other templates, configurable section order, and headings in languages other than English.
- Enforcing resume length. resume-ats owns that.
- Keeping the filled HTML as an output.
