---
name: resume-write
description: Write the engineer's resume bullets and STAR stories in a resume-builder workspace. Turns each project from checkpoint 2, the metrics from the wizard, the performance reviews and the imported resume into XYZ bullets (06-bullets/bullets.json), each citing the evidence, metric or resume line it rests on and naming the job or profile project it goes under, and writes a STAR story for each top project (06-bullets/stories.md). A script checks that every bullet cites its own project's evidence, states only numbers its sources state, and that together the bullets cover every project, metric and resume highlight. Use when the engineer asks to write or revise bullets or stories, or when resume-build reaches the write step.
---

# resume-write

Follow `../resume-core/SKILL.md` for workspace conventions.

- Resolve `scripts/...` and `../resume-core/...` against this skill's own folder, not against the current directory.
- Run commands from the engineer's project directory, not from the skill folder.
- Always pass `--workspace` explicitly, preferably as an absolute path.

Every claim on the resume starts here. resume-ats later selects, orders and rewords these bullets, so write the whole pool: every project, every confirmed metric and every highlight of the old resume. `scripts/write.py` prints what to write about, then checks what you wrote and commits it. You choose the wording. Sanitize apply replaces confidential names next, and the engineer reviews every bullet at checkpoint 4.

## Steps

1. Run `uv run ../resume-core/scripts/stage.py --workspace WS status`.
   - If `04-projects` is `missing`, stop and suggest `/resume-builder:analyze`. If it is `stale`, tell the engineer and offer to analyze again first.
   - If `06-bullets.tmp/bullets.json` exists, a write was interrupted. Do not run `write.py` without `--commit`, which would discard it: go to step 6.
2. Run `uv run scripts/write.py --workspace WS`. To revise the committed bullets and stories instead of starting over (for example after the wizard added a metric), add `--from-current`: `06-bullets.tmp/` then starts as a copy of them, and bullets you leave unchanged keep their IDs and the wording the engineer reviewed. It prints:
   - `warning:` lines: a metric whose project is gone (the wizard re-links or removes it), a project that falls in no job of the profile, a performance review whose full text cannot be read.
   - `note:` lines: a project marked for a metric that has none. If the engineer has not been through the wizard yet, offer to run `/resume-builder:wizard` first.
   - The jobs (`/work/<i>`), with their dates, the projects that fall in them, and their lines from the old resume (`resume:/work/<i>/highlights/<j>`). A job with `projects: none` is an earlier role: its bullets come from the resume.
   - The profile projects (`/projects/<i>`), with their resume lines.
   - The projects in rank order: name, role, scope, months, summary (`(no summary)` for a part split off at checkpoint 2), reasons, `job:` (the job its bullets go under), metrics, and each evidence item with its title and excerpt. Projects marked `story` get a STAR story.
   - The performance reviews, with where their full text is.
3. Read each performance review's full text in `01-raw/reviews.jsonl` at the printed `raw_ref`. Note what it says about each project and about the engineer's work outside projects.
4. Write `06-bullets.tmp/bullets.json`, a JSON list:
   ```json
   [{"project_id": "pj_da2a2b53", "work_ref": 0,
     "text": "Cut p99 checkout latency 40% for Contoso Bank by building a Redis-backed idempotency cache for Project Falcon in Go",
     "form": "xyz_quantified", "sources": ["ev_191cc8ce", "ev_99a74656", "metric:m_1"]},
    {"project_id": null, "work_ref": 0, "text": "Mentored two new engineers through on-call onboarding",
     "form": "xyz", "sources": ["ev_cbf558fa"]},
    {"project_id": null, "work_ref": 1, "text": "Migrated the order service from PHP to Go, serving 2M requests per day",
     "form": "xyz", "sources": ["resume:/work/1/highlights/0"]},
    {"project_id": null, "work_ref": null,
     "text": "Built ledger-lint, an open-source linter for double-entry ledger files with 300 GitHub stars",
     "form": "xyz", "sources": ["resume:/projects/0/description"]}]
   ```
   - **Wording.** XYZ: accomplished X, as measured by Y, by doing Z. One line that starts with a past-tense verb, with no pronoun, no trailing period, no dates, and no ticket keys, IDs or URLs. Verbs follow the project's role (`lead`: led, designed, drove; `core`: built, implemented; `supporting`: contributed, reviewed), and claims follow its scope: never "company-wide" for a `team` project.
   - **Forms.** `xyz_quantified` when the bullet cites a metric of its own project (`metric:<id>`), and the text states the metric's value as its statement does (`40%` for 40). `xyz` otherwise.
   - **Numbers.** Write only numbers the bullet's sources state: an evidence title or excerpt, a review's text, a metric, or the resume line it cites. Never invent or estimate one, and never turn a count of lines changed into a claim.
   - **Sources.** A project bullet cites at least one of its project's evidence items, and may add performance reviews, its project's metrics and resume lines about the same work. A bullet without a project cites performance reviews and resume lines only. Never cite evidence of another project or of none: the engineer left it out.
   - **Places.** Each bullet goes under one job or profile project:
     - A project bullet: `project_id` is the project and `work_ref` the job printed as `job:` (any of them when several are printed). When the project falls in no job, `work_ref` is null and resume-ats cannot place it until the engineer adds the job with the wizard.
     - A bullet from a job's resume lines, or about the engineer's work in a job that a performance review describes: `project_id` null and `work_ref` that job. A `resume:/work/<i>/…` source requires `work_ref` `i`.
     - A bullet about a profile project: `project_id` and `work_ref` null, citing `resume:/projects/<i>/…`.
   - **Coverage.** Every project gets a bullet: two to four for projects marked `story`, one or two for the others. Every metric is cited by a bullet of its project. Every printed `resume:…/highlights/…` line is cited by some bullet, and so is a profile project's description when it has no highlights. A resume line about a project's work can be cited by that project's bullet rather than repeated. You may reword a resume line into XYZ form, adding nothing it does not say.
   - **Names.** Write codenames and customer names exactly as the evidence spells them, and do not generalize them yourself: the engineer decides each in the wizard, and sanitize apply replaces the denied ones word for word, capitalizing only at a sentence start. So prefer places where a name stands on its own (`for Contoso Bank`) over uses as a modifier (`the Contoso Bank team`, which becomes `the a top-10 US bank team`).
   - Do not write `id`: the script assigns IDs.
5. Write `06-bullets.tmp/stories.md`: `# Stories`, then for each project marked `story`, in the printed order, a `## ` heading with its exact name and one line each for Situation, Task, Action and Result:
   ```
   # Stories

   ## Project Falcon checkout latency

   - **Situation:** Checkout for Contoso Bank missed its p99 latency target at peak traffic.
   - **Task:** Jordan led the fix for the Project Falcon checkout path.
   - **Action:** Built a Redis-backed idempotency cache in Go and added cache eviction metrics.
   - **Result:** p99 checkout latency fell 40%.
   ```
   Write in the past tense about the engineer's own part, naming them by first name. Use only what the project's evidence, the performance reviews and its metrics say, with no number they do not state. Spell names as in step 4. With no project marked `story`, the file is `# Stories` alone. Sanitize apply needs this file, so always write it.
6. Run `uv run scripts/write.py --workspace WS --commit`. On exit 1 nothing was committed: fix the files as each line and its `fix:` line say, and run it again.
7. Report the bullets by place (each printed as its ID, place, project, form and text), the stories, and every `warning:` and `note:` line. Say that sanitize apply (`/resume-builder:sanitize`) replaces denied terms next, and that the engineer reviews every bullet and story at checkpoint 4.

Never edit `06-bullets/` or `decisions/` by hand, and never weaken or skip a check.

## What the script guarantees

- Every bullet cites at least one source, and every source resolves: evidence, a confirmed metric, or a single value in the imported profile (`resume:`) or the wizard's answers (`wizard:`).
- A bullet cites evidence only of its own project, or a performance review, so an excluded project's evidence never returns, and the sanitize scan has read everything a bullet cites.
- `xyz_quantified` exactly when the bullet cites a metric; such a bullet belongs to the metric's project and states its value.
- Every number written with digits in a bullet appears in its sources, and every number in a story in its project's evidence, the performance reviews or its metrics.
- Every bullet names its place: `work_ref`, a job of the effective profile whose dates overlap its project's months, or a profile project it cites. A project bullet has no place only when no job overlaps the project, and the script warns about it.
- Every project has a bullet, every metric of a current project and every highlight of the imported resume is cited, and each project marked for a metric has one story, in rank order.
- A bullet whose text is unchanged since the last commit keeps its ID. New bullets get the next numbers.

## Output

```
06-bullets/
  bullets.json   # the bullets: id, project_id, work_ref, text, form, sources
  stories.md     # a STAR story for each project marked for a metric; names as the evidence spells them
```

Sanitize apply writes `07-sanitized/` from these files, and resume-ats reads only the sanitized ones.
