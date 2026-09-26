# resume-write: Design

- **Date:** 2026-09-26
- **Status:** Approved
- **Scope:** The `resume-write` skill: XYZ bullets for the engineer's projects, jobs and profile projects (`06-bullets/bullets.json`), STAR stories for the top projects (`06-bullets/stories.md`), and the script that checks both and commits `06-bullets`. Also the resume-core changes write needs. Follow-up spec 7 of the [architecture spec](2026-09-24-resume-builder-architecture-design.md).

## Goal

Write every claim the resume can make, each backed by its sources. resume-write turns the projects of checkpoint 2, the metrics of checkpoint 3, the performance reviews and the imported resume into bullets, and the top projects into STAR stories. resume-ats later selects, orders and rewords these bullets, so write produces the whole pool: every project, every metric the engineer confirmed, and every highlight of the old resume. A script checks what the model writes: that each bullet cites sources that say what it says, including its numbers, and names the place on the resume it belongs to.

## Gaps

The architecture spec and the roadmap leave these open:

1. **Script and model.** Wording needs the model. Nothing says what a script checks, where the model's draft lives, or who commits `06-bullets`.
2. **Where a bullet goes.** resume-ats must put each bullet under a job or a profile project, because a tailored resume has no other place for one. `work_ref` is defined only for earlier roles. A project bullet names no job (the fixture's `b_1`), and a bullet about a project from the old resume names nothing (`b_4`).
3. **What a bullet may cite.** Nothing ties a bullet's evidence to its project. The sanitize scan reads only the evidence of projects and the performance reviews, because "resume-write cites a project's evidence and performance reviews" ([resume-sanitize spec](2026-09-25-resume-sanitize-design.md#texts)). A bullet citing other evidence could carry a name nobody was asked about, and one citing an excluded project's evidence would bring that project back.
4. **Numbers.** "The model may suggest metric types but never invents values." Nothing checks the numbers in a bullet.
5. **The two forms.** "`xyz_quantified` when a confirmed metric exists" does not tie the form to a cited metric, or the bullet's text to the metric's value.
6. **Completeness.** Nothing says every project gets a bullet, every confirmed metric is used, or the old resume's highlights survive. resume-ats can only select from what write wrote.
7. **Stories.** "STAR stories for top-N projects" has no format, no rule for which projects, and no source check. The render spec checks stories for terms only.
8. **Bullet IDs.** Flags and attestations name bullets by ID. Nothing says how IDs are assigned, or whether a bullet keeps its ID when write runs again.
9. **Stage inputs.** The wizard relies on `06-bullets` going stale when a metric changes ([resume-wizard spec](2026-09-25-resume-wizard-design.md#metrics)). Nothing lists what `06-bullets` records.

## Decisions

| Topic | Decision |
|---|---|
| Script and model | `write.py` begins `06-bullets` and prints what to write about. The model writes `06-bullets.tmp/bullets.json` and `stories.md`. `write.py --commit` checks both, assigns IDs and commits, like `scan.py` and `match_projects.py` (gap 1). |
| Placement | `work_ref` names the job a bullet goes under, an index into the effective profile's `work`. A project bullet's job must overlap the project's months, and is null only when no job does. A bullet about a profile `projects` entry cites a pointer into it and has no `work_ref`. Every bullet without a project has a place (gap 2). |
| Evidence | A bullet cites `ev_…` only for its project's evidence or a performance review. A project bullet cites at least one item of its project (gap 3). |
| Numbers | Every number written in a bullet or a story appears in its sources: evidence titles and excerpts, a review's full text, a metric's value or statement, the value at a `resume:` or `wizard:` pointer (gap 4). |
| Forms | `xyz_quantified` exactly when the bullet cites a metric. A metric is cited only by a bullet of its project, and the bullet states the metric's value, as the metric's statement does (gap 5). |
| Completeness | Every project has a bullet, every metric of a current project is cited, every highlight of the imported resume's `work` and `projects` entries is cited, and so is the description of a profile project without highlights (gap 6). |
| Stories | `stories.md` holds one story for each project with `metric_prompt`, in rank order, headed by its `internal_name`, with one line each for Situation, Task, Action and Result. Its numbers must appear in the project's evidence, the performance reviews or the project's metrics (gap 7). |
| IDs | The script assigns IDs. A bullet whose text equals a bullet of the last committed run keeps that bullet's ID; others get `b_<n>` numbers past the highest used (gap 8). |
| Revising | `write.py --from-current` begins with a copy of the committed bullets and stories, so the model revises them instead of starting over, and text the engineer reviewed stays the same. |
| Inputs | `06-bullets` records `04-projects/projects.json`, `02-evidence/evidence.jsonl` and, when they exist, `01-raw`, `03-profile/profile.json`, `decisions/profile.json` and `decisions/metrics.json`. Never `decisions/terms.json`: write spells names as the evidence does, so deciding a term leaves it fresh (gap 9). |

## Skill layout

```
skills/resume-write/
  SKILL.md
  scripts/
    write.py               # CLI: begin 06-bullets and print what to write about; --commit checks, assigns IDs, commits
    rwrite/
      common.py            # errors, workspace files, reading and validating inputs
      material.py          # jobs, profile projects, project months and the jobs they overlap, source texts
      bullets.py           # checks of bullets.json; IDs
      stories.py           # checks of stories.md
      report.py            # what write.py prints
skills/resume-core/scripts/rcore/
  numbers.py               # new: numbers in a text, unsupported, states_value (moved from resume-wizard)
  raw.py                   # new: RawReader, a record's text at raw_ref (moved from resume-sanitize)
```

Every script uses only the standard library and imports `rcore` as portability rule 6 allows.

## Command line

```
uv run scripts/write.py --workspace WS [--from-current]
uv run scripts/write.py --workspace WS --commit
```

| Exit | Meaning |
|---|---|
| 0 | `06-bullets.tmp/` begun and the material printed; with `--commit`, bullets and stories checked and `06-bullets` committed |
| 1 | Error: `04-projects/projects.json` or `02-evidence/evidence.jsonl` missing, an invalid input, a bullet or story problem, no `06-bullets.tmp/` for `--commit`, no committed `06-bullets` for `--from-current`, or a failed commit. Nothing committed. |
| 2 | Usage error |

## Pipeline

1. `write.py` reads and validates `04-projects/projects.json` and `02-evidence/evidence.jsonl`, and when they exist `03-profile/profile.json`, `decisions/profile.json` and `decisions/metrics.json`. A missing projects or evidence file names the command that writes it, and an invalid input the command that fixes it. It reads each performance review's full text in `01-raw/` for the [number check](#numbers).
2. It begins `06-bullets` (a fresh `06-bullets.tmp/`, or with `--from-current` a copy of the committed `06-bullets/`) and prints the [material](#what-writepy-prints): the jobs and projects of the profile with their highlights, each project with its job, metrics and evidence, and the performance reviews.
3. The model reads the material and each performance review's full text in `01-raw/` at its `raw_ref`, and writes `06-bullets.tmp/bullets.json` and `06-bullets.tmp/stories.md`.
4. `write.py --commit` reads the inputs again, checks the [bullets](#bullets) and the [stories](#stories), assigns [IDs](#ids), writes `bullets.json` back and commits `06-bullets` with its [inputs](#inputs) and `extra` `{"bullets": 4, "quantified": 1, "stories": 1}`.

`write.py` without `--commit` always begins a fresh `06-bullets.tmp/`, which discards a draft. When `06-bullets.tmp/bullets.json` exists, a write is in progress: continue it with `write.py --commit`.

## Placement

A tailored resume holds bullets only in its `work` and `projects` entries, and each entry must match an entry of the effective profile ([render spec](2026-09-25-resume-render-design.md#fact-fields)). So every bullet names one place in the effective profile (`rcore.profile.effective_profile`):

| Bullet | `project_id` | `work_ref` | Place |
|---|---|---|---|
| About a project | the project | a job whose dates overlap the project's months | `work[work_ref]` |
| About a project that is a profile project | the project | null, and a pointer into `/projects/<i>` | `projects[i]` |
| About a project no job overlaps | the project | null | none: a `warning:` |
| From a job's resume lines or a performance review | null | the job | `work[work_ref]` |
| About a profile project | null | null, and a pointer into `/projects/<i>` | `projects[i]` |

A pointer is a `resume:` or `wizard:` source. Its place is the entry it points into: `/work/1/highlights/0` is in `work[1]`, `/projects/0/description` in `projects[0]`.

- `work_ref` is an index of the effective profile's `work`, which is the imported `work` with any job the wizard added after it.
- A pointer into `/work/<i>` requires `work_ref` `i`. A pointer into `/projects/<i>` requires `work_ref` null and no pointer into `/work`, and all such pointers of one bullet name the same `i`. Pointers into other sections (`/basics/summary`, `/awards/0/title`) place nothing.
- A job's dates are its `startDate` and `endDate` as months: `2019` starts at `2019-01` and ends at `2019-12`, `2023-01-15` is `2023-01`. A missing `startDate` is open, and a missing `endDate` means the job is ongoing. A job *overlaps* a project when neither ends before the other starts, comparing the project's `start` and `end` months.
- A project bullet's `work_ref` must be a job that overlaps the project. When the project overlaps several jobs (a job change during the project), any of them will do. `work_ref` may be null only when the bullet cites a `/projects/<i>` pointer or no job overlaps the project. For such a project `write.py` prints `warning: pj_… 'Ledger export' (2025-02 to 2025-05) falls in no job of the profile; resume-ats cannot place its bullets until the job is added with /resume-builder:wizard`.
- A bullet without a project must have a place.

Earlier roles are the jobs no project overlaps. Their bullets come from the imported resume and cite it, as the architecture spec says, and the rules above give them `work_ref`.

## Bullets

The model writes `06-bullets.tmp/bullets.json`, a list in `bullets.schema.json` form, without IDs:

```json
[{"project_id": "pj_da2a2b53", "work_ref": 0,
  "text": "Cut p99 checkout latency 40% for Contoso Bank by building a Redis-backed idempotency cache for Project Falcon in Go",
  "form": "xyz_quantified", "sources": ["ev_191cc8ce", "ev_99a74656", "metric:m_1"]},
 {"project_id": null, "work_ref": 1,
  "text": "Migrated the order service from PHP to Go, serving 2M requests per day",
  "form": "xyz", "sources": ["resume:/work/1/highlights/0"]}]
```

The order is the model's: resume-ats chooses the final order. An `id` the model writes is ignored.

### Checks

`write.py --commit` stops with one line per problem and a `fix:` line when:

- `bullets.json` is missing, not JSON, or does not match `bullets.schema.json` with `id` optional;
- a text holds a line break (as `str.splitlines` counts them) or begins or ends with a space, or two bullets have the same text;
- a bullet has no sources, lists one twice, or cites one that does not resolve (`rcore.sources.source_error`: an unknown evidence or metric ID, or a pointer that is not a single string or number), or a pointer into an `x-` field such as `x-lines`, which is not resume text;
- `project_id` is not a project in `04-projects/projects.json`;
- an `ev_` source is neither a performance review nor an item of the bullet's project, or a project bullet cites none of its project's items;
- a `metric:` source belongs to another project, or the bullet has no project;
- `form` is `xyz_quantified` without a `metric:` source, or `xyz` with one;
- the text does not state the value of a metric it cites (`rcore.numbers.states_value`, the rule the wizard applies to the metric's statement);
- a number in the text appears in none of the bullet's sources (see [Numbers](#numbers));
- a [placement](#placement) rule fails;
- a project has no bullet; a metric whose project is a current project is cited by no bullet; a `highlights` item of an imported `work` or `projects` entry is cited by no bullet; a profile project with a `description` and no `highlights` has no bullet citing its description.

```
06-bullets.tmp/bullets.json: /0/sources/2: metric:m_2 belongs to pj_77e0a1c3, not to this bullet's project pj_da2a2b53
06-bullets.tmp/bullets.json: /0/text: the number '250' is in none of its sources
06-bullets.tmp/bullets.json: /1/sources/0: ev_5c0ffee0 is in no project and is not a performance review
06-bullets.tmp/bullets.json: /1/work_ref: /work/1 (2019-06 to 2022-12) does not overlap pj_da2a2b53 (2025-02 to 2025-05); use /work/0
06-bullets.tmp/bullets.json: /3: a bullet without a project needs a place: a work_ref, or a resume: pointer into /projects/<i>
06-bullets.tmp/bullets.json: pj_77e0a1c3 'Ledger export retries' has no bullet
06-bullets.tmp/bullets.json: resume:/work/1/highlights/1 is cited by no bullet
  fix: edit 06-bullets.tmp/bullets.json: cite only a project's own evidence, performance reviews, its metrics and the profile; write only numbers the sources state; give each bullet its place; and cover every project, metric and resume highlight (see SKILL.md)
```

Then it sorts each bullet's sources, assigns IDs, and writes the records back with keys in schema order (`id`, `project_id`, `work_ref`, `text`, `form`, `sources`).

### Numbers

`rcore.numbers.numbers(text)` finds each number written with digits: a run of digits with optional thousands separators and decimals, so `p99` gives 99, `40%` 40, `1,200` 1200 and `2.5x` 2.5. A number is supported when some source text holds a number of the same value:

| Source | Text |
|---|---|
| `ev_…` | `title` and `excerpt`; for a performance review also its full text in `01-raw/` at `raw_ref` (`rcore.raw.RawReader`). If the raw record cannot be read, the excerpt stands in and a `warning:` says so. |
| `metric:<id>` | `value` and `statement` |
| `resume:` or `wizard:` pointer | the value it points to |

Evidence `stats` (lines and files changed) are not sources: a line count is not an achievement. Numbers written as words (`two engineers`) are not checked, and neither is which unit follows a number; the engineer reviews the wording at checkpoint 4.

### IDs

Flags and attestations name bullets by ID, so a bullet the model did not change keeps its ID:

1. The previous bullets are the committed `06-bullets/bullets.json`, if there is one and it is valid (otherwise none, with a `warning:`).
2. In file order, a bullet whose text equals a previous bullet's text takes that bullet's ID, each previous ID once.
3. Every other bullet, in file order, gets `b_<n>`, counting on from the highest number in a previous or taken ID.

A first run numbers the bullets `b_1` to `b_n` in file order. A rewritten bullet gets a new ID, so an attestation for its old text can never apply to it.

## Stories

The model writes `06-bullets.tmp/stories.md`, one story for each project with `metric_prompt: true`, in rank order:

```
# Stories

## Project Falcon checkout latency

- **Situation:** Checkout for Contoso Bank missed its p99 latency target at peak traffic.
- **Task:** Jordan led the fix for the Project Falcon checkout path.
- **Action:** Built a Redis-backed idempotency cache in Go and added cache eviction metrics.
- **Result:** p99 checkout latency fell 40%.
```

`write.py --commit` stops, with the line number and a `fix:` line, when:

- `stories.md` is missing or is not UTF-8 text;
- the first line is not `# Stories`;
- the `## ` headings are not the `internal_name` of each `metric_prompt` project, in rank order, each once;
- a section's lines, ignoring blank ones, are not exactly `- **Situation:** …`, `- **Task:** …`, `- **Action:** …` and `- **Result:** …`, in that order, each with text;
- a number in a section appears in none of the project's evidence (`title` and `excerpt`), the performance reviews (with their full text) or the project's metrics. Stories match projects by position, so under a wrong heading the numbers are checked once the heading is right.

```
06-bullets.tmp/stories.md:3: expected '## Project Falcon checkout latency' (rank 1, pj_da2a2b53)
06-bullets.tmp/stories.md:8: the number '250' is in none of pj_da2a2b53's evidence, the performance reviews or its metrics
06-bullets.tmp/stories.md:11: '## Ledger export retries' is a story too many: stories are only for the 1 project write.py marked 'story'
06-bullets.tmp/stories.md: no story for pj_77e0a1c3 'Ledger export retries' (rank 2)
  fix: edit 06-bullets.tmp/stories.md: '# Stories', then for each project write.py marked 'story', in its order, '## <its name>' and one line each for Situation, Task, Action and Result, with only numbers its evidence, the performance reviews or its metrics state (see SKILL.md)
```

Problems are listed in line order.

With no `metric_prompt` project, `stories.md` is `# Stories` alone. Stories cite no sources line by line, so render checks them for terms only. These checks keep them to the projects and numbers the bullets can prove, and sanitize and the engineer's review at checkpoint 4 do the rest.

## Inputs

`write.py --commit` commits `06-bullets` with inputs `04-projects/projects.json`, `02-evidence/evidence.jsonl` and each of `01-raw` (review texts), `03-profile/profile.json`, `decisions/profile.json` (the effective `work` that `work_ref` indexes, and `wizard:` pointers) and `decisions/metrics.json` that exists. A new or removed metric therefore makes `06-bullets` stale, as the wizard relies on, and so does a new profile answer. `decisions/terms.json` is not an input: write writes names as the evidence spells them, and sanitize apply, which records the decisions, replaces them.

## What write.py prints

For the fixture:

```
write: 1 project (1 story), 3 evidence items in projects, 1 performance review, 1 metric; profile: 2 jobs, 1 project
jobs:
  /work/0  Senior Software Engineer, Northwind Payments  2023-01 to present  projects: pj_da2a2b53
  /work/1  Software Engineer, Tailspin Toys  2019-06 to 2022-12  projects: none
    resume:/work/1/highlights/0  Migrated the order service from PHP to Go, serving 2M requests per day
profile projects:
  /projects/0  ledger-lint  2021-04 to present
    resume:/projects/0/description  Open-source linter for double-entry ledger files; 300 GitHub stars
projects:
 1. pj_da2a2b53  Project Falcon checkout latency  [lead, cross-team, 2025-02 to 2025-05]  story
    Idempotency cache that cut checkout latency for Contoso Bank.
    reasons: authored the core PR and owned the epic; customer-facing latency impact
    job: /work/0
    metric:m_1  p99 checkout latency reduced 40%  (value 40, unit %)
    ev_99a74656  epic, assignee, 2025-02-10  Project Falcon: checkout latency
      Reduce p99 checkout latency for Contoso Bank.
    ev_191cc8ce  pr, author, 2025-03-04  PAY-42: Add Redis idempotency cache for Project Falcon checkout
      Adds a Redis-backed idempotency cache in front of the Contoso Bank checkout path.
    ev_56410ed1  review, reviewer, 2025-04-02  PAY-57: Cache eviction metrics
      Adds eviction metrics for the PAY-42 idempotency cache.
performance reviews:
  ev_cbf558fa  2025-07-15  2025 H1 performance review  full text at 01-raw/reviews.jsonl:1#/items/0
began 06-bullets.tmp/: write 06-bullets.tmp/bullets.json and 06-bullets.tmp/stories.md, then run write.py --commit
```

A job with `projects: none` is an earlier role. A job prints its `highlights`, or its `summary` when it has none, and a profile project its `highlights`, or its `description`. A project's evidence prints in evidence order, and a project with an empty summary (a part split off at checkpoint 2) prints `(no summary)`. A project overlapping several jobs prints `jobs: /work/0 or /work/2 (it overlaps each; choose one)`, and one overlapping none `job: none in the profile`.

`warning:` lines come first: no `03-profile/profile.json` (`no jobs or profile projects to put bullets under; run /resume-builder:import`), a metric whose project is not current (`warning: decisions/metrics.json m_2: pj_1d2c3b4a is not a project in 04-projects/projects.json; the wizard re-links or removes it`), a project in no job, and a review whose raw record cannot be read. Then a `note:` for each `metric_prompt` project without a metric: `note: pj_… 'Ledger export retries' has a metric prompt and no metric in decisions/metrics.json: its bullets use the xyz form; if the engineer has not been through the wizard, run /resume-builder:wizard first`.

With `--commit`, after the checks pass, it prints the warnings that still apply (a metric whose project is gone, an unreadable review, and `warning: 2 bullets of pj_… 'Ledger export' (2025-02 to 2025-05) have no place: no job of the profile overlaps it; …` for bullets without a place), then each bullet and story:

```
  b_1  /work/0  pj_da2a2b53  xyz_quantified  Cut p99 checkout latency 40% for Contoso Bank by building a Redis-backed idempotency cache for Project Falcon in Go
  b_2  /work/0  xyz  Mentored two new engineers through on-call onboarding
  b_3  /work/1  xyz  Migrated the order service from PHP to Go, serving 2M requests per day
  b_4  /projects/0  xyz  Built ledger-lint, an open-source linter for double-entry ledger files with 300 GitHub stars
  story  pj_da2a2b53  Project Falcon checkout latency
committed 06-bullets: 4 bullets (1 quantified), 1 story
```

A bullet without a place prints `no place` where its place would be.

## `06-bullets/` contents

| File | Written by | Schema |
|---|---|---|
| `bullets.json` | the model, then `write.py --commit` assigns IDs and sorts sources | `bullets.schema.json` |
| `stories.md` | the model, checked by `write.py --commit` | none (text) |
| `_stage.json` | `write.py --commit` through `rcore.stages` | `stage.schema.json` |

## SKILL.md

1. Run `stage.py status`. If `04-projects` is missing, stop and suggest `/resume-builder:analyze`; if it is stale, offer to analyze again first. If `06-bullets.tmp/bullets.json` exists, a write was interrupted: go to step 6.
2. Run `write.py`, or `write.py --from-current` to revise the committed bullets (for example after the wizard added a metric). If it prints a `note:` about a missing metric and the engineer has not been through the wizard, offer to run `/resume-builder:wizard` first.
3. Read the printed material, and each performance review's full text in `01-raw/` at its `raw_ref`.
4. Write `06-bullets.tmp/bullets.json`:
   - XYZ: "accomplished X, as measured by Y, by doing Z". One line, starting with a past-tense verb, no pronoun, no trailing period, no dates, ticket keys or URLs.
   - Verbs follow the project's `role` (`lead`: led, designed, drove; `core`: built, implemented; `supporting`: contributed, reviewed) and claims follow its `scope`.
   - `xyz_quantified` when the bullet cites a metric of its project, stating the metric's value; `xyz` otherwise.
   - Only numbers the cited sources state. Write codenames and customer names as the evidence spells them: sanitize replaces them mechanically, so prefer places where a name stands alone (`for Contoso Bank`) over uses as a modifier (`the Contoso Bank team`).
   - Place each bullet as the [placement](#placement) table says, and cover every project, metric and resume highlight.
   - Top projects get two to four bullets, others one or two. Resume highlights may be reworded into XYZ form, adding nothing they do not say.
5. Write `06-bullets.tmp/stories.md`: one story per project the printout marks `story`, in the printed order, headed by its name, with the four STAR lines, past tense, about the engineer's own part, using only what its evidence, the performance reviews and its metrics say.
6. Run `write.py --commit`. On exit 1, fix the files as each line says.
7. Report the bullets by place, the stories, and every `warning:` and `note:`. Say that sanitize apply replaces denied terms next, and that the engineer reviews every bullet at checkpoint 4.

Never edit `06-bullets/` or `decisions/` by hand, and never weaken or skip a check.

## Changes to resume-core, fixtures and the architecture spec

1. New `rcore/numbers.py`: `numbers(text)` and `states_value(text, value)`, moved from resume-wizard's `rwizard/metrics.py`, which imports them from here. The wizard's statement rule and write's bullet rule are one rule.
2. New `rcore/raw.py`: `RawReader`, the text of the raw record at a `raw_ref`, moved from resume-sanitize's `rsanitize/texts.py`, which imports it from here. resume-analyze keeps its own reader, which reads people rather than text.
3. Fixture: `06-bullets/bullets.json` and `07-sanitized/bullets.json` `b_1` gain `work_ref: 0`, the job its project falls in. From the fixture's projects, evidence, profile and metrics, with its bullets (without IDs) and stories as the draft, `write.py --commit` writes the saved `06-bullets/bullets.json` and `stories.md` byte for byte, and sanitize apply then rebuilds the saved `07-sanitized/` as before.
4. `pytest.ini` adds `skills/resume-write/scripts` to `pythonpath`. The test command and CI do not change: write uses only the standard library.
5. resume-core `SKILL.md`: what `work_ref` means, and the new helpers.
6. The architecture spec: the plugin layout lists `write.py`; the Bullet contract gives `work_ref`'s meaning, the placement of profile-project bullets, what a bullet may cite and the forms; the resume-write section points here and states the stories format and the stage inputs.

## Error handling

| Case | Behavior |
|---|---|
| No projects or evidence | `write.py` exits 1 naming `/resume-builder:analyze` or `/resume-builder:collect`. Nothing begun. |
| An invalid input | Exit 1 naming the file and the command that fixes it. Nothing begun. |
| A bullet or story problem | Exit 1, one line per problem and a `fix:` line. The draft stays in `06-bullets.tmp/` to fix. |
| `--commit` without `06-bullets.tmp/`, or `--from-current` without a committed `06-bullets/` | Exit 1. |
| A metric whose project is gone | Warning. The wizard re-links or removes it. Bullets cannot cite it. |
| A project no job overlaps | Warning. Its bullets have `work_ref` null, and resume-ats cannot place them until the wizard adds the job. |
| A raw review record cannot be read | Warning. Its excerpt stands in for the full text. |
| No imported profile | Allowed: no jobs, so project bullets have no place (warnings) and every other bullet is refused. |
| Commit fails | Exit 1. The previous stage stays. |

## Testing

- **Numbers:** digits with separators and decimals, `p99`, a trailing comma; `states_value` as the wizard used it; a number from each kind of source, including a review's full text and a pointer's value; an unreadable raw record (excerpt, warning); `stats` not counted.
- **Placement:** job months from `YYYY`, `YYYY-MM` and `YYYY-MM-DD`, open start, ongoing end; a project overlapping one, two and no jobs; a pointer into `/work/i` with another `work_ref`; a profile project pointer with a `work_ref`; two profile projects; a project bullet placed in a profile project; a bullet without a project and without a place; a job the wizard added.
- **Sources:** another project's evidence, evidence in no project (including an excluded project's), a review on a project bullet and a job bullet, a project bullet citing none of its items, a metric of another project or of a bullet without a project, `x-lines` pointers, duplicates, unresolved references.
- **Forms:** `xyz_quantified` without a metric, `xyz` with one, a text that does not state the metric's value.
- **Completeness:** a project without bullets, an unused metric, an uncited highlight, a profile project description; a metric of a gone project is not required (and warned about).
- **Stories:** the title line, headings in rank order, a missing and an extra story, the four lines in order, extra lines, numbers from the project's evidence, a review and its metrics, a number from another project.
- **IDs:** a first run numbers in file order; unchanged texts keep their IDs, new ones count on from the highest; an invalid previous file; a model's `id` ignored; sources sorted and keys in schema order.
- **CLIs:** exit codes; `write.py` begins fresh; `--from-current` copies the committed files and fails without them; `--commit` without a `.tmp/`; the commit's inputs and `extra`; warnings and notes; missing projects or evidence.
- **Must promises:** `stories.md` is written with `bullets.json`, and a commit without it fails; `xyz_quantified` only with a confirmed metric of the bullet's project; every bullet has sources; earlier roles' bullets set `work_ref` and cite `resume:` pointers; reviews are cited directly; `groups.json` is never read; a term decision leaves `06-bullets` fresh while a new metric makes it stale.
- **Fixture end to end:** `write.py --commit` rebuilds the saved `06-bullets/` byte for byte, then sanitize apply rebuilds the saved `07-sanitized/`, the workspace validates, and render's gate passes.

## Out of scope for v1

- Judging wording: whether a bullet's verb fits the role, or a claim the scope, beyond numbers. The engineer reviews every bullet at checkpoint 4, and resume-ats's claim diff checks rewrites for job versions.
- Numbers written as words, and units.
- Selecting and ordering bullets for length. resume-ats does that.
- Asking the engineer for a job when a project falls in none. The wizard can add one (`answer.py profile /work/-/name …`), but does not ask yet.
