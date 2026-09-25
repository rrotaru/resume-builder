# Roadmap

Progress through the build order in the [architecture spec](superpowers/specs/2026-09-24-resume-builder-architecture-design.md#follow-up-specs). Tick a box and add its links when a piece merges.

Short names used below:

- **Arch** is the [architecture spec](superpowers/specs/2026-09-24-resume-builder-architecture-design.md).
- **Render spec** is the [resume-render spec](superpowers/specs/2026-09-25-resume-render-design.md).
- **Import spec** is the [resume-import spec](superpowers/specs/2026-09-25-resume-import-design.md).
- **Collect spec** is the [resume-collect spec](superpowers/specs/2026-09-25-resume-collect-design.md).
- **Core** is [`skills/resume-core/SKILL.md`](../skills/resume-core/SKILL.md): workspace rules, source references, the profile overlay and the checks.

## Start here

1. Take the first unchecked piece in the [checklist](#checklist). Pieces are built in order.
2. Read its section in Arch, then its bullets below. **Must** lines are promises earlier pieces rely on; breaking one breaks a check that already ships.
3. Read Core. For a finished example of each step, see the Render spec, the [resume-core plan](superpowers/plans/2026-09-24-resume-core.md) and [`skills/resume-render/`](../skills/resume-render/).
4. Follow the cycle every piece goes through:
   1. Write the spec, `docs/superpowers/specs/YYYY-MM-DD-<skill>-design.md`, and get it approved.
   2. Optionally write a plan in `docs/superpowers/plans/`.
   3. Implement it and open a PR.
5. When it merges, tick it here and update Arch wherever the piece changed a shared contract.

## Conventions

- **Skill layout:** a skill lives in `skills/<name>/` and may hold only `SKILL.md`, `scripts/`, `references/`, `templates/` and `schemas/`. It may use `../resume-core/` and nothing else outside its folder. See Arch "Portability rules". `tests/test_skill_lint.py` enforces this.
- **Scripts:** every script runs with `uv run` and starts with a PEP 723 header with `requires-python = ">=3.10"`. Check and normalization scripts use only the standard library. Other scripts import `rcore` from `../resume-core/scripts/`.
- **Stages:** write a stage only through `stage.py begin` and `stage.py commit` (see Core "Writing a stage"), or through `rcore.stages` from a script that runs its own check first, as `render.py` and `check_profile.py` do. Each numbered folder has exactly one writer. Only the wizard and the checkpoints write `decisions/`.
- **Schemas:** every JSON or JSONL workspace file has a schema in `skills/resume-core/schemas/`, mapped by path in `FILE_SCHEMAS` (`rcore/validation.py`). A new JSON or JSONL file needs both. Text files (`stories.md`, `jd.txt`, `resume.txt`) and `01-raw/` have no schema by design; the validator reads only JSON and JSONL.
- **Fixtures:** [`tests/fixtures/workspace/`](../tests/fixtures/workspace/) holds a made-up engineer's saved output for most stages. A new skill's output must stay valid input for the next stage, and in CI the saved output stands in for model-driven steps.
- **Tests:** from the repository root, run `uv run skills/resume-render/scripts/render.py --install-browser` once, then `uv run --with pytest --with-requirements skills/resume-render/scripts/render.py --with-requirements skills/resume-import/scripts/extract_text.py pytest`. CI runs Python 3.10 and 3.13. A script that reads PDF or DOCX pins the same `pypdf` and `python-docx` versions as these two, so the command stays the same (a test checks `ingest_reviews.py`). A new skill's scripts folder goes into `pytest.ini` `pythonpath`.
- **Reviews:** a Codex bot reviews each PR. Verify every finding before acting, since some are wrong. Never weaken or skip a check to get green.

## Checklist

- [x] **1. resume-core and resume-init.** Arch "resume-init" and "Data contracts"; [plan](superpowers/plans/2026-09-24-resume-core.md); [#1](https://github.com/rrotaru/resume-builder/pull/1).
  - Shipped the schemas, the `rcore` library, `validate.py`, `stage.py`, the three checks, `init_workspace.py`, the fixture workspace, the skill lint and CI.
- [x] **2. resume-render.** Render spec; [#2](https://github.com/rrotaru/resume-builder/pull/2).
  - Shipped `render.py` with the checks it runs before rendering and the check on its output files, the render model, the template and the PDF, DOCX and TXT writers.
  - Added to resume-core: the fact-field check (`rcore/facts.py`) and the effective profile (`rcore/profile.py`). Tailored entries lost `x-sources`.
- [x] **3. resume-import.** Import spec; [#4](https://github.com/rrotaru/resume-builder/pull/4).
  - Shipped `extract_text.py` (PDF, DOCX, TXT, Markdown, JSON Resume) and `check_profile.py`, the faithfulness check that commits `03-profile/`: every value appears in the entry's lines of `resume.txt`, dates are stated, open entries say they are ongoing, and entries keep the text's order. It also warns when a re-import moves a wizard answer to another entry.
  - Added to resume-core: `x-lines` in `resume.schema.json` (profile `x-sources` removed), `profile-source.schema.json` for `03-profile/source.json`, and `rcore.config.resolve_path` (relative `config.json` paths resolve against the workspace).
- [x] **4. resume-collect (checkpoint 1).** Collect spec; [#5](https://github.com/rrotaru/resume-builder/pull/5).
  - Shipped `configure.py` (data notice, time range, sources, repos, git authors, review folder, resume), `ingest_export.py`, `ingest_git_log.py`, `ingest_reviews.py`, the report-only `normalize_github.py`, `normalize_gitlab.py` and `normalize_jira.py`, and `link.py`. `link.py` normalizes every raw file, removes duplicates, assigns IDs over all items, links them, and commits `01-raw` and `02-evidence`.
  - Every `01-raw/` line is a page, `{"query", "items", ...}`, with items as fetched. `raw_ref` is `01-raw/<file>:<line>#/items/<index>`. Every collect script refuses to run until the data notice is accepted.
  - Added to resume-core: `rcore/documents.py` (the document reader, moved from resume-import), optional `config.json` `git_authors`, and JSONL lines that stay whole when a string holds U+0085, U+2028 or U+2029. The fixture gains `01-raw/`, `exports/jira.csv` and `reviews/`, and `link.py` rebuilds its `02-evidence/evidence.jsonl` byte for byte.
- [ ] **5. resume-analyze (checkpoint 2).** Arch [resume-analyze](superpowers/specs/2026-09-24-resume-builder-architecture-design.md#resume-analyze-checkpoint-2), "Project" in Data contracts, Decisions row "Metric prompts".
  - Writes `04-projects/projects.json` (`projects.schema.json`; fixture exists) and `signals.json`. **`signals.json` has no schema or fixture yet: add both.**
  - Scripts: `signals.py` and `match_projects.py`. ID continuity is a Jaccard similarity of 0.5 or more, one-to-one.
  - Use `rcore.ids.project_id` and `rcore.config.metric_prompt_count`.
  - Reads `decisions/projects.json` (`project-decisions.schema.json`). Shows orphaned decisions at checkpoint 2.
  - `02-evidence/evidence.jsonl` is sorted by `created_at`. Authored work is `pr`, `mr` or `commit` with `engineer_role: author`. Reviews are `kind: review`, `engineer_role: reviewer`, and carry no `stats` because the size is the author's. A performance review's full text is in `01-raw/reviews.jsonl` at its `raw_ref`, since `excerpt` holds 500 characters (Collect spec [Normalization](superpowers/specs/2026-09-25-resume-collect-design.md#normalization)).
  - `links` point from an item to what it references (a pull request to its ticket, a ticket to its epic). Cluster over both directions.
- [ ] **6. resume-sanitize and resume-wizard (checkpoint 3).** Arch [resume-sanitize](superpowers/specs/2026-09-24-resume-builder-architecture-design.md#resume-sanitize) and [resume-wizard](superpowers/specs/2026-09-24-resume-builder-architecture-design.md#resume-wizard-checkpoint-3); Core "The profile" and "Checks".
  - Sanitize scan writes `05-terms/candidates.json` (`term-candidates.schema.json`; fixture exists).
  - Sanitize apply writes `07-sanitized/`: `bullets.json`, `profile.json`, `stories.md` and `new-terms.json`. The fixture has all but `new-terms.json`.
  - **Must** (sanitize) write `07-sanitized/stories.md`. Render copies only that file and never `06-bullets/stories.md`.
  - **Must** (sanitize) leave profile fact fields (names, titles, dates) unchanged, rewriting only prose (Render spec [Confidential values](superpowers/specs/2026-09-25-resume-render-design.md#confidential-values)). Copy `x-lines` unchanged.
  - The wizard writes only `decisions/`: `metrics.json`, `profile.json`, `terms.json`. It skips items already answered.
  - **Must** (wizard) write profile answers under the overlay rules. Arrays of objects merge by index, and `{}` keeps an imported entry, so `"work": [{}, {"endDate": "2022-12"}]` fills the second job's end date (Core "The profile").
  - **Must** (wizard) ask for a replacement value when a fact field contains a denied term, and store it at that path in `decisions/profile.json`.
  - The wizard owns fixing answers that a re-import moved: `check_profile.py --commit` prints a `warning:` for each (Import spec [Re-import](superpowers/specs/2026-09-25-resume-import-design.md#re-import)).
- [ ] **7. resume-write.** Arch [resume-write](superpowers/specs/2026-09-24-resume-builder-architecture-design.md#resume-write), "Bullet" in Data contracts.
  - Writes `06-bullets/bullets.json` (`bullets.schema.json`; fixture exists) and `06-bullets/stories.md` (text, unsanitized).
  - Use `xyz_quantified` only when a confirmed metric exists, otherwise `xyz`. Every bullet has non-empty `sources`, and bullets for earlier roles set `work_ref` and cite `resume:` pointers.
- [ ] **8. resume-ats.** Arch [resume-ats](superpowers/specs/2026-09-24-resume-builder-architecture-design.md#resume-ats) and "Tailored resume" in Data contracts.
  - Writes `08-ats/general/` (`resume.json`, `report.json`) and `08-ats/jobs/<slug>/` (`jd.txt`, `resume.json`, `report.json`, `flags.json`).
  - `resume.json` and `flags.json` have schemas and fixtures. **`report.json` has no schema yet: add one.**
  - Scripts: `ats_lint.py`, `keywords.py`, `diff_claims.py`. To rebuild one job, run `stage.py begin 08-ats --from-current`.
  - **Must** copy fact fields exactly from the effective profile, shortening dates at most, and write no `x-sources` (Render spec [Fact fields](superpowers/specs/2026-09-25-resume-render-design.md#fact-fields)).
  - **Must** make the claim diff record every examined bullet's hash in `flags.json` `checked`, including `basics.summary` under the id `summary`. Job slugs match `^[a-z0-9][a-z0-9-]*$`.
  - A keyword that is missing but has evidence enters `skills` only after the engineer adds it to `decisions/profile.json`.
  - Run `check_sources.py` on every tailored resume before committing, since render will.
- [ ] **9. resume-build and commands.** Arch [resume-build](superpowers/specs/2026-09-24-resume-builder-architecture-design.md#resume-build), "Commands", "Plugin layout".
  - Adds `commands/` (build, init, collect, import, analyze, wizard, write, sanitize, ats and render, each only passing arguments to its skill), plus `.claude-plugin/plugin.json` and `marketplace.json`.
  - Orchestrates the whole run, offers to reuse fresh stages (`stage.py status`), and runs checkpoints 1 to 4. Interrupted runs resume from `decisions/`.
  - `03-profile` records no stage inputs, because the resume file is outside the workspace, so `stage.py status` always calls it fresh. Before reusing it, compare `03-profile/source.json` `path` and `sha256` with `config.json` `resume_path` and that file (Import spec [Pipeline](superpowers/specs/2026-09-25-resume-import-design.md#pipeline)).
  - `01-raw` records no inputs either, so `stage.py status` always calls it fresh. Build decides when to collect again, for example from `02-evidence/_stage.json` `created_at`. An unfinished collection is a `01-raw.tmp/` folder, possibly holding a `<source>.partial.jsonl`: continue it rather than running `stage.py begin 01-raw`, which deletes it (Collect spec [SKILL.md](superpowers/specs/2026-09-25-resume-collect-design.md#skillmd)).
  - **Must** (checkpoint 4) show every allowed-term notice (`rcore.terms.allowed_notices`) and have the engineer confirm each.
  - **Must** (checkpoint 4) let the engineer accept, revert or edit each flagged job bullet, writing `decisions/attestations.json`. Render's `fix:` lines send flagged bullets to `/resume-builder:build`.

## Small follow-ups (any time)

- [ ] **Terms check and control characters.** `check_terms.py` doesn't treat control characters that aren't whitespace (such as U+0001) as separators, so `Project\u0001Falcon` passes it in a JSON file. Render's output check still catches it. The likely fix is to add them to `_SEPARATOR` in `rcore/terms.py`.
- [ ] **CI actions on Node 20.** CI warns that `actions/checkout@v4` and `astral-sh/setup-uv@v6` target Node 20. Bump both to their current major versions.
- [ ] **Playwright pin.** `render.py` pins `playwright==1.56.0` (Chromium build 1194). Bumping it also changes the browser build that `--install-browser` fetches.
