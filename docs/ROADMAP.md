# Roadmap

Progress through the build order in the [architecture spec](superpowers/specs/2026-09-24-resume-builder-architecture-design.md#follow-up-specs). Tick a box and add its links when a piece merges.

Short names used below:

- **Arch** is the [architecture spec](superpowers/specs/2026-09-24-resume-builder-architecture-design.md).
- **Render spec** is the [resume-render spec](superpowers/specs/2026-09-25-resume-render-design.md).
- **Import spec** is the [resume-import spec](superpowers/specs/2026-09-25-resume-import-design.md).
- **Collect spec** is the [resume-collect spec](superpowers/specs/2026-09-25-resume-collect-design.md).
- **Analyze spec** is the [resume-analyze spec](superpowers/specs/2026-09-25-resume-analyze-design.md).
- **Sanitize spec** is the [resume-sanitize spec](superpowers/specs/2026-09-25-resume-sanitize-design.md).
- **Wizard spec** is the [resume-wizard spec](superpowers/specs/2026-09-25-resume-wizard-design.md).
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
- **Tests:** from the repository root, run `uv run skills/resume-render/scripts/render.py --install-browser` once, then `uv run --with pytest --with-requirements skills/resume-render/scripts/render.py --with-requirements skills/resume-import/scripts/extract_text.py pytest`. CI runs Python 3.10 and 3.13. If the system Python's own packages break `pypdf` (a `pyo3_runtime.PanicException` from `cryptography`), install a uv-managed Python (`uv python install 3.13`) and add `UV_MANAGED_PYTHON=1` and `--python 3.13` to both commands. A script that reads PDF or DOCX pins the same `pypdf` and `python-docx` versions as these two, so the command stays the same (a test checks `ingest_reviews.py`). A new skill's scripts folder goes into `pytest.ini` `pythonpath`.
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
- [x] **5. resume-analyze (checkpoint 2).** Analyze spec; [#6](https://github.com/rrotaru/resume-builder/pull/6).
  - Shipped `signals.py`, `match_projects.py` and `decide.py`.
    - `signals.py` begins `04-projects` and writes `signals.json`. It clusters evidence over links read both ways. Performance reviews count as mentions and never join clusters. It reads people and epic creators from the raw records.
    - `match_projects.py` checks the model's `groups.json` and carries IDs forward from the last run's groups (Jaccard ≥ 0.5, one-to-one, best first). It applies `decisions/projects.json` in order, sets dates, ranks and metric prompts, and commits `04-projects` with `--commit`.
    - `decide.py` is checkpoint 2's only writer of `decisions/projects.json`.
  - `04-projects/` holds `signals.json`, `groups.json` and `projects.json`. `groups.json` is the model's grouping before decisions, with IDs. `projects.json` is the result after decisions, and the only file later stages read. An orphaned decision (its project is not in this run) is shown with the closest project and blocks the commit (exit 3) until it is re-linked or discarded.
  - Added to resume-core: `signals.schema.json` and `project-groups.schema.json`, and the `set_rank` action (with `rank`) and an optional `rename` `summary` in `project-decisions.schema.json`. The fixture gains `04-projects/signals.json` and `groups.json`. The scripts rebuild them and `projects.json` byte for byte.
- [x] **6. resume-sanitize and resume-wizard (checkpoint 3).** Sanitize spec and Wizard spec; [#7](https://github.com/rrotaru/resume-builder/pull/7).
  - Shipped resume-sanitize's `scan.py` and `apply.py`, each with `--commit` for its second step.
    - `scan.py` begins `05-terms` and prints the likely terms that `decisions/terms.json` does not decide yet, each with its places. It reads each project's name, summary and rank reasons, the title and excerpt of each project's evidence and of every performance review, each review's full text in `01-raw/`, and every string of `03-profile/profile.json`. The model writes `candidates.json`. `scan.py --commit` checks it, fills in `found_in` (`pj_…`, `ev_…`, `resume:<pointer>`) and commits.
    - `apply.py` replaces each denied match with its replacement in bullets, `stories.md` and the profile's prose. It uses the terms check's rules through `rcore.terms.find`, lets allowed terms exempt a match, and capitalizes a replacement at a sentence start. It writes `07-sanitized/` and checks the result with the terms check. The model writes `new-terms.json`. `apply.py --commit` requires it to list every undecided candidate still in the text, then commits.
  - Shipped resume-wizard's `questions.py` and `answer.py`. `questions.py` lists, in order: moved answers, metrics whose project is gone, undecided terms (from `05-terms/candidates.json` and `07-sanitized/new-terms.json`), fact fields that hold a denied term, missing profile fields, and `metric_prompt` projects without a metric. `answer.py` records one checked answer per command, and every file is left unchanged on error.
  - Added to resume-core:
    - `rcore.terms` `find`, `terms_in`, `key`, `read_entries` and `replacement_conflicts`.
    - `rcore.profile` gains the JSON Resume vocabulary, `PROSE_FIELDS`, `identity`, `describe`, `merged_arrays` and `is_date`. resume-import now imports these from `rcore.profile`.
    - `rcore.facts.fact_values`.
    - `wizard-state.schema.json` for `decisions/wizard.json` (created by `init_workspace.py`), and optional `evidence_ids` in `metrics.schema.json`.
  - The fixture gains `found_in` in `candidates.json`, `07-sanitized/new-terms.json` (`[]`) and `decisions/wizard.json`. `07-sanitized/bullets.json` `b_1` is now the mechanical replacement. Both sanitize halves rebuild the saved files byte for byte, and the fixture has no open wizard questions.
- [ ] **7. resume-write.** Arch [resume-write](superpowers/specs/2026-09-24-resume-builder-architecture-design.md#resume-write), "Bullet" in Data contracts.
  - Writes `06-bullets/bullets.json` (`bullets.schema.json`; fixture exists) and `06-bullets/stories.md` (text, unsanitized).
  - Use `xyz_quantified` only when a confirmed metric exists, otherwise `xyz`. Every bullet has non-empty `sources`, and bullets for earlier roles set `work_ref` and cite `resume:` pointers.
  - Read `04-projects/projects.json`, never `groups.json`. Performance reviews are never in a project's `evidence_ids`, so cite them directly (`ev_…`) where they support a bullet. `start` and `end` are the months of the project's evidence, not job dates. A part split off by the engineer has an empty `summary` until it is renamed.
  - **Must** write `06-bullets/stories.md` as well as `bullets.json`: sanitize apply refuses to run without it.
  - Write codenames and customer names as the evidence spells them. Sanitize apply replaces them mechanically, with the replacement as the engineer decided it, and capitalizes only at a sentence start. So `for Contoso Bank` becomes `for a top-10 US bank`, but `the Contoso Bank team` becomes `the a top-10 US bank team`. The engineer reviews every changed line at checkpoint 4.
  - A metric's `statement` states its `value`, and `evidence_ids` is its project's evidence when it was recorded. Cite `metric:<id>` only for a metric whose `project_id` is the bullet's project.
- [ ] **8. resume-ats.** Arch [resume-ats](superpowers/specs/2026-09-24-resume-builder-architecture-design.md#resume-ats) and "Tailored resume" in Data contracts.
  - Writes `08-ats/general/` (`resume.json`, `report.json`) and `08-ats/jobs/<slug>/` (`jd.txt`, `resume.json`, `report.json`, `flags.json`).
  - `resume.json` and `flags.json` have schemas and fixtures. **`report.json` has no schema yet: add one.**
  - Scripts: `ats_lint.py`, `keywords.py`, `diff_claims.py`. To rebuild one job, run `stage.py begin 08-ats --from-current`.
  - **Must** copy fact fields exactly from the effective profile, shortening dates at most, and write no `x-sources` (Render spec [Fact fields](superpowers/specs/2026-09-25-resume-render-design.md#fact-fields)).
  - Read bullets from `07-sanitized/bullets.json`, never `06-bullets/`. A keyword that holds a denied term cannot be replaced (keywords combine in the overlay), so leave it out. sanitize apply and `questions.py` print a note for each one.
  - The engineer adds a keyword to `decisions/profile.json` with the wizard, `answer.py add /skills/N/keywords KEYWORD`. Nothing else writes that file.
  - **Must** make the claim diff record every examined bullet's hash in `flags.json` `checked`, including `basics.summary` under the id `summary`. Job slugs match `^[a-z0-9][a-z0-9-]*$`.
  - A keyword that is missing but has evidence enters `skills` only after the engineer adds it to `decisions/profile.json`.
  - Run `check_sources.py` on every tailored resume before committing, since render will.
- [ ] **9. resume-build and commands.** Arch [resume-build](superpowers/specs/2026-09-24-resume-builder-architecture-design.md#resume-build), "Commands", "Plugin layout".
  - Adds `commands/` (build, init, collect, import, analyze, wizard, write, sanitize, ats and render, each only passing arguments to its skill), plus `.claude-plugin/plugin.json` and `marketplace.json`.
  - Orchestrates the whole run, offers to reuse fresh stages (`stage.py status`), and runs checkpoints 1 to 4. Interrupted runs resume from `decisions/`.
  - `03-profile` records no stage inputs, because the resume file is outside the workspace, so `stage.py status` always calls it fresh. Before reusing it, compare `03-profile/source.json` `path` and `sha256` with `config.json` `resume_path` and that file (Import spec [Pipeline](superpowers/specs/2026-09-25-resume-import-design.md#pipeline)).
  - `01-raw` records no inputs either, so `stage.py status` always calls it fresh. Build decides when to collect again, for example from `02-evidence/_stage.json` `created_at`. An unfinished collection is a `01-raw.tmp/` folder, possibly holding a `<source>.partial.jsonl`: continue it rather than running `stage.py begin 01-raw`, which deletes it (Collect spec [SKILL.md](superpowers/specs/2026-09-25-resume-collect-design.md#skillmd)).
  - **Must** (checkpoint 2) record the engineer's project choices only with resume-analyze's `decide.py`, never by editing `decisions/projects.json` or regrouping `groups.json`. Its evidence snapshots are what orphan suggestions use (Analyze spec [Project decisions](superpowers/specs/2026-09-25-resume-analyze-design.md#project-decisions)).
  - Checkpoint 2 left unfinished is a `04-projects.tmp/` holding `groups.json`: continue it with `match_projects.py`. `signals.py` begins a fresh `04-projects.tmp/` and discards the draft. When the evidence has not changed, reuse the committed grouping with `stage.py begin 04-projects --from-current` and `match_projects.py`. `match_projects.py --commit` exits 3 while a decision is orphaned.
  - `04-projects` records `01-raw`, `02-evidence/evidence.jsonl`, `config.json` and `decisions/projects.json` as inputs, so a decision recorded after the commit makes it stale.
  - **Must** (checkpoint 4) show every allowed-term notice (`rcore.terms.allowed_notices`) and have the engineer confirm each.
  - Checkpoint 3 is the wizard. Run `questions.py` until it prints `wizard: no open questions`. Deciding a term can open a `fact:` question, so run it again after each round.
  - Checkpoint 4 decides the new terms in `07-sanitized/new-terms.json` by running the wizard, which asks about them, then sanitize apply again (`07-sanitized` records `decisions/terms.json`, so it is stale). The engineer also reviews every changed bullet and story line that apply printed, and its `warning:` lines.
  - Sanitize halves resume like analyze. `scan.py` and `apply.py` without `--commit` begin a fresh `.tmp/`, which discards a draft. An interrupted scan is a `05-terms.tmp/candidates.json`: continue it with `scan.py --commit`. An interrupted apply is a `07-sanitized.tmp/new-terms.json`: continue it with `apply.py --commit`, which exits 1 if the inputs changed since.
  - `05-terms` records `04-projects/projects.json`, `02-evidence/evidence.jsonl`, `01-raw` and `03-profile/profile.json`, and never `decisions/terms.json`, so deciding terms leaves it fresh. No stage records `decisions/wizard.json`.
  - **Must** (checkpoint 4) let the engineer accept, revert or edit each flagged job bullet, writing `decisions/attestations.json`. Render's `fix:` lines send flagged bullets to `/resume-builder:build`.

## Small follow-ups (any time)

- [ ] **Terms check and control characters.** `check_terms.py` doesn't treat control characters that aren't whitespace (such as U+0001) as separators, so `Project\u0001Falcon` passes it in a JSON file. Render's output check still catches it. The likely fix is to add them to `_SEPARATOR` in `rcore/terms.py`.
- [ ] **CI actions on Node 20.** CI warns that `actions/checkout@v4` and `astral-sh/setup-uv@v6` target Node 20. Bump both to their current major versions.
- [ ] **Merge-aware ID matching.** When the model itself groups the projects of a merge decision together, the group takes the ID of the project it overlaps most. If that is a project named in `merge_with`, the merge and the other decisions about the merged project are orphaned, and the engineer re-links or discards them (Analyze spec [Orphans](superpowers/specs/2026-09-25-resume-analyze-design.md#orphans)). `match_projects.py` could instead match such a group against the merged projects together, so the merged project keeps its ID.
- [ ] **Wizard skips after a re-import.** A skip inside an entry (`profile:/work/1/startDate`) lapses when the imported entry there changes. It is asked again rather than moved with its entry. Moving skips the way `answer.py move` moves answers would avoid asking twice.
- [ ] **Sanitize detector quality.** The likely-term detectors are regular-expression hints: capitalized runs, codename phrases, URLs, emails and money. Add them to the model-quality evals (Arch "Testing") with a small set of made-up evidence holding real-looking customer names, to measure what the model still misses.
- [ ] **Playwright pin.** `render.py` pins `playwright==1.56.0` (Chromium build 1194). Bumping it also changes the browser build that `--install-browser` fetches.
