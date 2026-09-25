# Roadmap

Progress through the build order in the [architecture spec](superpowers/specs/2026-09-24-resume-builder-architecture-design.md#follow-up-specs). Tick a box and add its links when a piece merges.

Short names used below:

- **Arch** is the [architecture spec](superpowers/specs/2026-09-24-resume-builder-architecture-design.md).
- **Render spec** is the [resume-render spec](superpowers/specs/2026-09-25-resume-render-design.md).
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
- **Stages:** write a stage only through `stage.py begin` and `stage.py commit` (see Core "Writing a stage"). Each numbered folder has exactly one writer. Only the wizard and the checkpoints write `decisions/`.
- **Schemas:** every JSON or JSONL workspace file has a schema in `skills/resume-core/schemas/`, mapped by path in `FILE_SCHEMAS` (`rcore/validation.py`). A new JSON or JSONL file needs both. Text files (`stories.md`, `jd.txt`) and `01-raw/` have no schema by design; the validator reads only JSON and JSONL.
- **Fixtures:** [`tests/fixtures/workspace/`](../tests/fixtures/workspace/) holds a made-up engineer's saved output for most stages. A new skill's output must stay valid input for the next stage, and in CI the saved output stands in for model-driven steps.
- **Tests:** from the repository root, run `uv run skills/resume-render/scripts/render.py --install-browser` once, then `uv run --with pytest --with-requirements skills/resume-render/scripts/render.py pytest`. CI runs Python 3.10 and 3.13.
- **Reviews:** a Codex bot reviews each PR. Verify every finding before acting, since some are wrong. Never weaken or skip a check to get green.

## Checklist

- [x] **1. resume-core and resume-init.** Arch "resume-init" and "Data contracts"; [plan](superpowers/plans/2026-09-24-resume-core.md); [#1](https://github.com/rrotaru/resume-builder/pull/1).
  - Shipped the schemas, the `rcore` library, `validate.py`, `stage.py`, the three checks, `init_workspace.py`, the fixture workspace, the skill lint and CI.
- [x] **2. resume-render.** Render spec; [#2](https://github.com/rrotaru/resume-builder/pull/2).
  - Shipped `render.py` with the checks it runs before rendering and the check on its output files, the render model, the template and the PDF, DOCX and TXT writers.
  - Added to resume-core: the fact-field check (`rcore/facts.py`) and the effective profile (`rcore/profile.py`). Tailored entries lost `x-sources`.
- [ ] **3. resume-import.** Arch [resume-import](superpowers/specs/2026-09-24-resume-builder-architecture-design.md#resume-import) and "Profile" in Data contracts; Decisions row "Resume import".
  - Writes `03-profile/profile.json`. It has a schema (`resume.schema.json`, open) and a fixture.
  - Scripts: `extract_text.py` (pypdf, python-docx). JSON Resume files load directly. The input path is `config.json` `resume_path`.
  - A scanned PDF with no text: explain, and ask for DOCX, TXT or pasted text. No OCR in v1 (see Arch "Error handling").
  - **Must** map faithfully, because the fact-field check trusts the profile: never invent a title, date or degree (Render spec [What the check does not prove](superpowers/specs/2026-09-25-resume-render-design.md#what-the-check-does-not-prove)).
  - **Must** keep entries in the resume's order. `resume:` pointers and wizard overlays address entries by index.
- [ ] **4. resume-collect (checkpoint 1).** Arch [resume-collect](superpowers/specs/2026-09-24-resume-builder-architecture-design.md#resume-collect-checkpoint-1), "Evidence item" in Data contracts, Decisions rows "Data notice" and "v1 sources", and Arch [Error handling](superpowers/specs/2026-09-24-resume-builder-architecture-design.md#error-handling).
  - Writes `01-raw/<source>.jsonl` (no schema) and `02-evidence/evidence.jsonl` (`evidence.schema.json`; fixture exists).
  - Scripts: `normalize_github.py`, `normalize_gitlab.py`, `normalize_jira.py`, `ingest_git_log.py`, `ingest_reviews.py`, `link.py`.
  - Use `rcore.ids.evidence_id` and `rcore.ids.assign_evidence_ids`, which lengthen colliding IDs.
  - Record skipped rows with `stage.py commit --extra`.
  - Confirm the data notice before pulling anything, and store the time in `config.json` `data_notice_acknowledged_at`.
- [ ] **5. resume-analyze (checkpoint 2).** Arch [resume-analyze](superpowers/specs/2026-09-24-resume-builder-architecture-design.md#resume-analyze-checkpoint-2), "Project" in Data contracts, Decisions row "Metric prompts".
  - Writes `04-projects/projects.json` (`projects.schema.json`; fixture exists) and `signals.json`. **`signals.json` has no schema or fixture yet: add both.**
  - Scripts: `signals.py` and `match_projects.py`. ID continuity is a Jaccard similarity of 0.5 or more, one-to-one.
  - Use `rcore.ids.project_id` and `rcore.config.metric_prompt_count`.
  - Reads `decisions/projects.json` (`project-decisions.schema.json`). Shows orphaned decisions at checkpoint 2.
- [ ] **6. resume-sanitize and resume-wizard (checkpoint 3).** Arch [resume-sanitize](superpowers/specs/2026-09-24-resume-builder-architecture-design.md#resume-sanitize) and [resume-wizard](superpowers/specs/2026-09-24-resume-builder-architecture-design.md#resume-wizard-checkpoint-3); Core "The profile" and "Checks".
  - Sanitize scan writes `05-terms/candidates.json` (`term-candidates.schema.json`; fixture exists).
  - Sanitize apply writes `07-sanitized/`: `bullets.json`, `profile.json`, `stories.md` and `new-terms.json`. The fixture has all but `new-terms.json`.
  - **Must** (sanitize) write `07-sanitized/stories.md`. Render copies only that file and never `06-bullets/stories.md`.
  - **Must** (sanitize) leave profile fact fields (names, titles, dates) unchanged, rewriting only prose (Render spec [Confidential values](superpowers/specs/2026-09-25-resume-render-design.md#confidential-values)).
  - The wizard writes only `decisions/`: `metrics.json`, `profile.json`, `terms.json`. It skips items already answered.
  - **Must** (wizard) write profile answers under the overlay rules. Arrays of objects merge by index, and `{}` keeps an imported entry, so `"work": [{}, {"endDate": "2022-12"}]` fills the second job's end date (Core "The profile").
  - **Must** (wizard) ask for a replacement value when a fact field contains a denied term, and store it at that path in `decisions/profile.json`.
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
  - **Must** (checkpoint 4) show every allowed-term notice (`rcore.terms.allowed_notices`) and have the engineer confirm each.
  - **Must** (checkpoint 4) let the engineer accept, revert or edit each flagged job bullet, writing `decisions/attestations.json`. Render's `fix:` lines send flagged bullets to `/resume-builder:build`.

## Small follow-ups (any time)

- [ ] **Terms check and control characters.** `check_terms.py` doesn't treat control characters that aren't whitespace (such as U+0001) as separators, so `Project\u0001Falcon` passes it in a JSON file. Render's output check still catches it. The likely fix is to add them to `_SEPARATOR` in `rcore/terms.py`.
- [ ] **CI actions on Node 20.** CI warns that `actions/checkout@v4` and `astral-sh/setup-uv@v6` target Node 20. Bump both to their current major versions.
- [ ] **Playwright pin.** `render.py` pins `playwright==1.56.0` (Chromium build 1194). Bumping it also changes the browser build that `--install-browser` fetches.
