---
name: resume-analyze
description: Find the engineer's projects in a resume-builder workspace (checkpoint 2). Clusters linked evidence and computes signals, groups the evidence into projects with a role, scope and rank, keeps project IDs stable across runs, applies the engineer's recorded decisions (merge, split, rename, exclude, role, scope, rank), marks the top projects for metric questions, and writes 04-projects/projects.json. Use when the engineer asks to analyze their work or review their projects, or when resume-build reaches the analyze step.
---

# resume-analyze

Follow `../resume-core/SKILL.md` for workspace conventions.

- Resolve `scripts/...` and `../resume-core/...` against this skill's own folder, not against the current directory.
- Run commands from the engineer's project directory, not from the skill folder.
- Always pass `--workspace` explicitly, preferably as an absolute path.

Later stages attach metrics, bullets and stories to project IDs. Scripts decide IDs, dates, ranks after decisions, and which projects get metric questions. You decide the grouping, names, summaries, role, scope and ranking. The engineer's corrections are decisions in `decisions/projects.json`, recorded only with `scripts/decide.py`, and they apply again on every later run.

## Steps

1. Run `uv run ../resume-core/scripts/stage.py --workspace WS status`.
   - If `02-evidence` is `missing`, stop and suggest `/resume-builder:collect`. If it is `stale`, tell the engineer and offer to collect again first.
   - If `04-projects.tmp/groups.json` exists, checkpoint 2 was interrupted. Do not run `signals.py`, which would discard it: go to step 5.
   - To apply new decisions to a committed `04-projects` without grouping again (the evidence has not changed), run `stage.py --workspace WS begin 04-projects --from-current` and go to step 5.
2. Run `uv run scripts/signals.py --workspace WS`. It begins `04-projects`, writes `04-projects.tmp/signals.json` and prints each cluster of linked evidence with its signals, then each performance review. Show the engineer its first line.
3. Read what you need to group:
   - `04-projects.tmp/signals.json`: the clusters, with `label`, `evidence_ids` and signals.
   - `02-evidence/evidence.jsonl`: each item's `title` and `excerpt`, by `id`.
   - Each performance review's full text in `01-raw/reviews.jsonl`, at its `raw_ref` (the excerpt holds only 500 characters). Note which projects a review names in words: `review_mentions` counts only reviews that cite a ticket key or link.
   - If `04-projects/groups.json` exists (the last run), start from it: keep a group as it was unless the evidence changed, so its ID and the engineer's decisions carry over.
4. Write `04-projects.tmp/groups.json`, a JSON list with one object per project:
   ```json
   [{"internal_name": "Project Falcon checkout latency",
     "summary": "Idempotency cache that cut checkout latency for Contoso Bank.",
     "evidence_ids": ["ev_191cc8ce", "ev_56410ed1", "ev_99a74656"],
     "role": "core", "scope": "cross-team", "rank": 1,
     "rank_reasons": ["authored the core PR and owned the epic", "customer-facing latency impact"]}]
   ```
   - A group is one piece of work with one goal. Start from the clusters: a cluster is usually one project. Split a cluster that a catch-all ticket holds together, and join clusters that are clearly the same work (the same epic name, repository and time). Small unrelated items may stay out of every group.
   - Copy evidence IDs exactly. List each one in at most one group. Never add a performance review (`kind: perf_review`): reviews are cited directly by bullets.
   - `internal_name`: the name the evidence uses, such as the epic's title or the codename. `summary`: one sentence saying what the project did, from the titles and excerpts, with no number the evidence does not state.
   - `role`: `lead` when the engineer authored most of the changes, owned or created its epic, or started it (`authored_first`); `core` when they authored a substantial share; `supporting` when their part is mostly reviews or small changes.
   - `scope`: `team` for one repository or Jira project and few contributors; `cross-team` for several repositories or Jira projects, or many contributors. Use `org` or `company` only when the evidence says so, such as a performance review or an epic describing work across the organization. Never from size alone.
   - `rank`: 1 to n, each once, by impact: scope, role, size (authored changes and lines), duration, and mentions in performance reviews, including those you found in step 3.
   - `rank_reasons`: one to three short facts from the signals or the evidence, such as `authored 12 of 15 pull requests` or `named in the 2025 H1 review`. Nothing the evidence does not show.
   - Do not write `id`, `start`, `end` or `metric_prompt`. The script sets them.
5. Run `uv run scripts/match_projects.py --workspace WS`. It gives each group its ID, applies the recorded decisions, and writes `04-projects.tmp/groups.json` (now with IDs) and `04-projects.tmp/projects.json`.
   - **Exit 1:** fix `groups.json` as each line and its `fix:` line say, then run it again. If the evidence, a username or a raw record changed since `signals.py` (the error says so), start again at step 2.
   - Check every `note:` about a cluster that is partly grouped: an evidence ID may have been missed while copying.
6. **Checkpoint 2: review the projects.** Show the engineer the projects as printed (rank, name, role, scope, dates, summary, reasons), the excluded projects, and every `warning:` and `orphaned:` line. Explain that the projects marked `metric prompt` get questions about measurable results in the wizard. Ask whether the grouping, names, summaries, roles, scopes and ranking are right, and whether any project should be left out. Record each change with one command:
   - `uv run scripts/decide.py --workspace WS merge PJ --with PJ2 [PJ3 ...]` moves the other projects' evidence into `PJ`.
   - `decide.py --workspace WS split PJ --group EV,EV [--group EV ...]` splits each group of `PJ`'s evidence off into its own project. Then propose a name and summary for each new part, and record them with `rename`.
   - `decide.py --workspace WS rename PJ --name "NAME" [--summary "TEXT"]`
   - `decide.py --workspace WS set-role PJ lead|core|supporting`, `set-scope PJ team|cross-team|org|company`, `set-rank PJ N`
   - `decide.py --workspace WS exclude PJ` leaves a project out of the resume.
   - `decide.py --workspace WS list` shows the decisions, and `discard N` removes one.
   After each change, run `match_projects.py` again and show the result. Never edit `decisions/projects.json` by hand, and never change `groups.json` to carry out the engineer's choice: the decision would be lost on the next run.
7. **Orphaned decisions.** Exit 3 means a recorded decision names a project that is not in this run, for example because its evidence changed. Each `orphaned:` line names the closest current project. Ask the engineer, for each one, whether to re-link it (`decide.py --workspace WS relink N PJ`) or discard it (`decide.py --workspace WS discard N`). Nothing can be committed while one remains, because an orphaned `exclude` could let a project the engineer left out back onto the resume.
8. When the engineer approves the projects, run `uv run scripts/match_projects.py --workspace WS --commit`.
9. Report the projects committed, the ones marked for metric prompts, the exclusions, the decisions applied, and every `warning:` line (a metric whose project is gone is fixed in the wizard).

## What the scripts guarantee

- A project keeps its ID from the last run when it shares at least half of its combined evidence with one of the last run's groups (one-to-one, best match first). Any other project's ID is derived from its evidence, so the same evidence gives the same ID.
- Decisions apply in the order they were recorded, the same way on every run. A decision that no longer finds its project is shown, never silently dropped.
- Every evidence ID in a project exists, belongs to only one project, and is not a performance review.
- `start` and `end` are the months of a project's first and last evidence dates. `rank` runs from 1, and `metric_prompt` marks the top N: `N = min(projects, clamp(ceil(30% of projects), 3, 8))`, with the percent, floor and cap from `config.json` `metric_prompts`.

## Output

```
04-projects/
  signals.json    # clusters of linked evidence and their signals; performance reviews
  groups.json     # your groups, with the IDs the script gave them, before decisions
  projects.json   # the projects after the engineer's decisions: what later stages read
decisions/
  projects.json   # the engineer's checkpoint 2 decisions, written by decide.py
```
