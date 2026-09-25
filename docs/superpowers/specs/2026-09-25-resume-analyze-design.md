# resume-analyze: Design

- **Date:** 2026-09-25
- **Status:** Approved
- **Scope:** The `resume-analyze` skill (checkpoint 2): signals for each linked cluster of evidence, grouping evidence into projects, carrying project IDs from run to run, the engineer's project decisions, and the top-N metric prompts. Also the resume-core changes analyze needs. This is follow-up spec 5 of the [architecture spec](2026-09-24-resume-builder-architecture-design.md).

## Goal

Turn `02-evidence/evidence.jsonl` into `04-projects/projects.json`: the engineer's projects, each with its evidence, role, scope, dates and rank, and the top N marked for metric prompts. Later stages attach metrics (the wizard), bullets and stories (resume-write) to project IDs. So an ID must name the same project from one run to the next, and every correction the engineer makes at checkpoint 2 must apply again on every later run.

## Gaps

The architecture spec leaves these open:

1. **The model cannot write a project ID.** `projects.json` requires `id` as `pj_` plus 8 hex characters of a sha256 (`rcore.ids.project_id`), and dates and `metric_prompt` follow fixed rules. Nothing says which fields the model writes and which a script fills in, or where the model's draft lives.
2. **Matching against the last `projects.json` breaks after a merge or an exclusion.** `projects.json` holds projects after the engineer's decisions. Say the engineer merged B into A, and the next run's model groups A and B apart again. Both new groups overlap the merged project, and the larger one takes A's ID. If that is B's group, A's ID moves to B's work, and the merge decision now names the wrong projects. An excluded project is not in `projects.json` at all, so its ID cannot carry forward, and its `exclude` decision is orphaned on every later run.
3. **Decisions have no semantics.** `project-decisions.schema.json` lists `merge_with`, `split_groups`, `name`, `role`, `scope` and `evidence_ids`. It does not say which action uses which field, in what order decisions apply, what a split's new projects are called, or what `evidence_ids` is for.
4. **Ranking cannot be corrected.** Checkpoint 2 reviews the ranking, but no action changes a rank, so a correction would be lost on the next run.
5. **Nothing writes decisions exactly.** Only checkpoints write `decisions/`. Hand-written JSON can name a project that does not exist, or split off items the project does not hold.
6. **"Linked cluster" and its signals are undefined.** Links are directed. It is not said which items form a cluster, or whether a performance review that mentions two projects joins them into one. Contributor counts and epic creation need the people on an item, which evidence does not record.
7. **An orphaned exclusion is only shown.** If an orphaned `exclude` merely appears in a list, a project the engineer excluded (a confidential one, say) comes back under a new ID.
8. **`signals.json` has no schema or fixture** (roadmap).

## Decisions

| Topic | Decision |
|---|---|
| Clusters | Connected components of the link graph, reading each link in both directions. Performance reviews are not clustered, because a review that mentions two projects would join them. A review's links count as *mentions* of the clusters they reach (gap 6). |
| People | `signals.py` reads the raw record at each item's `raw_ref` for its author, assignees and reporter. That gives contributor counts and who created each epic (gap 6). |
| Three files | `signals.json` (written by `signals.py`), `groups.json` (the model's grouping, with IDs from `match_projects.py`) and `projects.json` (the groups after the engineer's decisions, written by `match_projects.py`). |
| The model's draft | The model writes `04-projects.tmp/groups.json` with no IDs, dates or `metric_prompt`: only name, summary, evidence, role, scope, rank and rank reasons. `match_projects.py` fills in the rest (gap 1). |
| ID continuity | New groups are matched against the last run's `groups.json`, the model's grouping *before* decisions. That compares two model groupings, like with like, and the decisions then apply the same way again (gap 2). Jaccard similarity of 0.5 or more, best match first, one-to-one. |
| Decisions | `match_projects.py` applies them, in file order. Each action is fully defined, including the IDs of a split's new projects (gap 3). |
| New actions and fields | `set_rank` with `rank` (gap 4). `rename` also takes an optional `summary`, so a split's new part can be described. |
| Recording decisions | `decide.py` is the only writer of `decisions/projects.json`. It checks the project against the current projects, stores the project's evidence IDs in `evidence_ids`, and replaces an older decision of the same kind for the same project (gap 5). |
| Orphans | A decision whose project is not in the current run is orphaned. `match_projects.py` shows it with the current project closest to its `evidence_ids`, and refuses to commit until each orphan is re-linked or discarded (gap 7). |
| Performance reviews | Never part of a project, since one review covers many. They appear as mentions, and bullets cite them directly. |
| Dates | `start` and `end` are the months of a project's earliest and latest evidence dates. `end` is never null: a ticket left open does not prove the work goes on. |
| Metric prompts | `metric_prompt` is true for ranks 1 to N, where N is `rcore.config.metric_prompt_count` of the number of projects left after exclusions, with `config.json` `metric_prompts`. |
| Commit | `match_projects.py --commit` checks and commits `04-projects` in the same process, as `check_profile.py --commit` does for `03-profile`. |
| Reuse | With unchanged evidence, `stage.py begin 04-projects --from-current` and `match_projects.py` apply new decisions to the committed grouping without grouping again. |

## Skill layout

```
skills/resume-analyze/
  SKILL.md
  scripts/
    signals.py             # CLI: begin 04-projects, clusters and signals -> signals.json
    match_projects.py      # CLI: check the model's groups, carry IDs forward, apply decisions, commit
    decide.py              # CLI: record checkpoint 2 decisions in decisions/projects.json
    ranalyze/
      common.py            # workspace files, errors, dates
      raw.py               # raw records at raw_ref: people, epic reporters, commit repositories
      clusters.py          # clusters and their signals
      groups.py            # the model's groups: checks and ID matching
      decisions.py         # decision checks, applying decisions, orphans, decide.py's edits
      report.py            # what the scripts print
skills/resume-core/schemas/
  signals.schema.json          # new: 04-projects/signals.json
  project-groups.schema.json   # new: 04-projects/groups.json
```

Every script uses only the standard library and imports `rcore` as portability rule 6 allows.

## Command line

```
uv run scripts/signals.py --workspace WS
uv run scripts/match_projects.py --workspace WS [--commit]
uv run scripts/decide.py --workspace WS list
uv run scripts/decide.py --workspace WS exclude PJ
uv run scripts/decide.py --workspace WS rename PJ --name NAME [--summary TEXT]
uv run scripts/decide.py --workspace WS set-role PJ lead|core|supporting
uv run scripts/decide.py --workspace WS set-scope PJ team|cross-team|org|company
uv run scripts/decide.py --workspace WS set-rank PJ N
uv run scripts/decide.py --workspace WS merge PJ --with PJ [PJ ...]
uv run scripts/decide.py --workspace WS split PJ --group EV[,EV ...] [--group ...]
uv run scripts/decide.py --workspace WS relink N PJ
uv run scripts/decide.py --workspace WS discard N
```

| Script | Exit | Meaning |
|---|---|---|
| `signals.py` | 0 | `04-projects.tmp/signals.json` written |
| | 1 | Error: no or invalid `config.json`, `02-evidence/evidence.jsonl` missing, invalid or empty. Nothing written. |
| `match_projects.py` | 0 | Groups checked; `groups.json` and `projects.json` written to `04-projects.tmp/`, and committed with `--commit` |
| | 1 | Error: no `04-projects.tmp/`, a missing or invalid `signals.json` or `groups.json`, evidence changed since `signals.py`, a group problem, an invalid decision, or a failed commit. Nothing committed. |
| | 3 | Orphaned decisions. The files are written to `04-projects.tmp/` for review, and nothing is committed. |
| `decide.py` | 0 | Decision recorded, changed or listed |
| | 1 | Error: no projects to decide about, an unknown project or evidence ID, an invalid split, a rank out of range, or an invalid `decisions/projects.json`. The file is left unchanged. |
| All | 2 | Usage error |

## Pipeline

1. `signals.py` validates `config.json` and `02-evidence/evidence.jsonl`, computes the [clusters and signals](#clusters-and-signals), runs `stages.begin(ws, "04-projects")`, writes `signals.json` and prints the clusters.
2. The model reads the signals, the evidence and the performance reviews, and writes `04-projects.tmp/groups.json` (see [Groups](#groups)).
3. `match_projects.py` checks the groups, gives them IDs, applies `decisions/projects.json`, writes `groups.json` (now with IDs) and `projects.json` into `04-projects.tmp/`, and prints the projects for checkpoint 2.
4. **Checkpoint 2.** The engineer reviews the projects. Each change is recorded with `decide.py`, and step 3 runs again to show the result. Orphaned decisions are re-linked or discarded.
5. `match_projects.py --commit` repeats step 3 and, if nothing is orphaned, commits `04-projects` with inputs `02-evidence/evidence.jsonl`, `01-raw` (the raw records `signals.py` read), `config.json` and, when it exists, `decisions/projects.json`, and with `extra`:
   `{"projects": 5, "excluded": 1, "metric_prompts": 3, "carried": 4, "new": 2, "decisions": 3, "unassigned": 41}`.

`signals.json` records `evidence_sha256`, the hash of the evidence it was computed from. `match_projects.py` stops with `02-evidence/evidence.jsonl changed since signals.py ran; run signals.py and group again` when the evidence has changed since.

`signals.py` always begins a fresh `04-projects.tmp/`, which discards a draft in progress. When `04-projects.tmp/groups.json` exists, checkpoint 2 is in progress: continue it with `match_projects.py` instead.

### `04-projects/` contents

| File | Written by | Schema |
|---|---|---|
| `signals.json` | `signals.py` | `signals.schema.json` (new) |
| `groups.json` | the model, then `match_projects.py` adds IDs | `project-groups.schema.json` (new) |
| `projects.json` | `match_projects.py` | `projects.schema.json` |
| `_stage.json` | `match_projects.py` through `rcore.stages` | `stage.schema.json` |

Only `projects.json` is read by later stages.

## Clusters and signals

### Clusters

Every evidence item except performance reviews (`kind: perf_review`) is a node. Each link joins its two ends, whichever way it points: a pull request links to its ticket, and a ticket to its epic, so a pull request and the epic's other tickets end up in one cluster. A link to a performance review, or to an ID that is not evidence, is ignored. Clusters are the connected components, so an unlinked item is a cluster of one.

Clusters are ordered by their first item in `evidence.jsonl` (sorted by `created_at`, then `id`) and named `c1`, `c2` and so on. The names hold for one `signals.json` only.

### Signals

For each cluster, from its items (evidence order) and their raw records:

| Field | Meaning |
|---|---|
| `id` | `c1`, `c2`, ... |
| `label` | The title of its first epic, else of its first ticket or issue, else of its first item |
| `evidence_ids` | Its items, in evidence order |
| `start`, `end`, `days` | The earliest `created_at` date, the latest `created_at` or `closed_at` date (`YYYY-MM-DD`, UTC), and the days between them |
| `kinds` | Items per kind, such as `{"epic": 1, "pr": 1, "review": 1}` |
| `authored` | Authored work: `pr`, `mr` or `commit` with `engineer_role: author` |
| `reviewed` | Reviews: `kind: review` (the engineer reviewed someone else's change) |
| `assigned` | Items with `engineer_role: assignee` |
| `reported` | Items with `engineer_role: reporter`, and issues the engineer opened (`kind: issue`, `engineer_role: author`) |
| `stats` | `additions`, `deletions` and `files` summed over authored work. Reviews carry no `stats`, because the size is the author's. |
| `repos` | Repository paths, sorted: a GitHub or GitLab key without its `#n` or `!n` (`northwind/ledger`), and a commit's remote without its host, or its folder name when it has no remote |
| `jira_projects` | Jira project keys, sorted (`PAY` for `PAY-42`) |
| `contributors` | The number of other people named as author, assignee or reporter on its items' raw records (see [People](#people)) |
| `epics` | Its epics |
| `epics_created` | Epics the engineer created: the raw record's reporter is the Jira username, or `engineer_role` is `reporter` |
| `first_authored_at` | The date of the engineer's earliest authored work in the cluster, or null |
| `authored_first` | True when the cluster has authored work and no review in it is dated before that work: the engineer wrote code there before reviewing anyone else's |
| `open_items` | `pr`, `mr`, `issue`, `ticket` or `epic` items with no `closed_at` |
| `review_mentions` | Performance reviews that link to any of its items, in evidence order |

`signals.json` also lists every performance review: `{"id", "title", "date", "raw_ref", "clusters"}`, where `clusters` are the clusters its links reach. Its full text is in `01-raw/reviews.jsonl` at `raw_ref`, because `excerpt` holds only 500 characters. Links come from keys and URLs in the full text (resume-collect), so a review that names a project in words mentions nothing here. The model reads each review for that.

```json
{"evidence_sha256": "sha256:…",
 "clusters": [{"id": "c1", "label": "Project Falcon: checkout latency",
               "evidence_ids": ["ev_99a74656", "ev_191cc8ce", "ev_56410ed1"],
               "start": "2025-02-10", "end": "2025-05-30", "days": 109,
               "kinds": {"epic": 1, "pr": 1, "review": 1},
               "authored": 1, "reviewed": 1, "assigned": 1, "reported": 0,
               "stats": {"additions": 812, "deletions": 140, "files": 23},
               "repos": ["northwind/ledger"], "jira_projects": ["PAY"], "contributors": 2,
               "epics": ["ev_99a74656"], "epics_created": [],
               "first_authored_at": "2025-03-04", "authored_first": true,
               "open_items": 0, "review_mentions": []}],
 "reviews": [{"id": "ev_cbf558fa", "title": "2025 H1 performance review", "date": "2025-07-15",
              "raw_ref": "01-raw/reviews.jsonl:1#/items/0", "clusters": []}]}
```

### People

`raw_ref` is `01-raw/<file>:<line>#/items/<index>`. `ranalyze/raw.py` reads each raw file named there once and takes the item. It reads the same fields resume-collect reads for ownership:

| Source | People |
|---|---|
| GitHub | `user.login`, `author.login`, `assignee.login`, `assignees` (a list or GraphQL `nodes`) |
| GitLab | `author.username`, `assignee.username`, `assignees` |
| Jira REST | `fields.assignee`, `fields.reporter`; a person is their first non-empty `displayName`, `name`, `key`, `emailAddress` or `accountId` |
| Jira CSV | `Assignee` (or `Assignee Id`), `Reporter` (or `Reporter Id`), headers matched ignoring case |
| Git, reviews | none: every commit is the engineer's, and a review has no people |

A person is the engineer when a field equals that source's username in `config.json`, ignoring case; for a Jira REST user, when any of the five fields does. `contributors` counts the other people as distinct `(source, name)` pairs, ignoring case. The same person on GitHub and in Jira therefore counts twice, and so do two spellings of one name. The count is a rough measure of how many people a cluster involved, not a list of teammates.

A raw file or line that is missing or unreadable gives no people for its items, and `signals.py` prints one `warning:` per file. `epics_created` then falls back to `engineer_role: reporter`.

### What signals.py prints

A header (items, clusters, reviews), then one block per cluster of two or more items, one line per single item, and one line per performance review with its `raw_ref`:

```
02-evidence: 4 items in 1 cluster, 1 performance review
c1  3 items, 2025-02-10 to 2025-05-30 (109 days): epic 1, pr 1, review 1
    authored 1, reviewed 1, assigned 1, reported 0; +812/-140 lines in 23 files
    repos northwind/ledger; Jira PAY; 2 contributors; epics created 0; authored first; 0 open
    "Project Falcon: checkout latency"
review ev_cbf558fa 2025-07-15 "2025 H1 performance review": no cluster; full text at 01-raw/reviews.jsonl:1#/items/0
wrote 04-projects.tmp/signals.json
```

## Groups

The model writes `04-projects.tmp/groups.json`, a list of groups:

```json
[{"internal_name": "Project Falcon checkout latency",
  "summary": "Idempotency cache that cut checkout latency for Contoso Bank.",
  "evidence_ids": ["ev_191cc8ce", "ev_56410ed1", "ev_99a74656"],
  "role": "core", "scope": "cross-team", "rank": 1,
  "rank_reasons": ["authored the core PR and owned the epic", "customer-facing latency impact"]}]
```

Grouping, role, scope, ranking and wording need judgment, so the model does them. The [SKILL.md](#skillmd) gives the rules. An item may stay out of every group: most small tickets and one-line commits are not projects.

### Checks

`match_projects.py` stops with one line per problem, and a `fix:` line, when:

- `groups.json` is missing, not JSON, or does not match `project-groups.schema.json` with `id` optional;
- an evidence ID is not in `02-evidence/evidence.jsonl`;
- an evidence ID appears twice, in one group or in two;
- a group holds a performance review;
- the ranks are not 1 to the number of groups, each used once.

```
04-projects.tmp/groups.json: /1/evidence_ids/2: ev_0badc0de is not in 02-evidence/evidence.jsonl
04-projects.tmp/groups.json: /2/evidence_ids/0: ev_191cc8ce is also in /0 ('Project Falcon checkout latency')
04-projects.tmp/groups.json: /0/evidence_ids/3: ev_cbf558fa is a performance review; reviews are never part of a project
04-projects.tmp/groups.json: ranks must be 1 to 3, each once (found 1, 1, 3)
  fix: edit 04-projects.tmp/groups.json: list each evidence ID from 02-evidence/evidence.jsonl in at most one group, leave out performance reviews, and rank the groups 1 to n.
```

It also prints a `note:` for each cluster of two or more items that is partly in a group and partly in none, naming the items left out. That is usually an ID missed while copying, but it can be deliberate.

### ID continuity

The previous groups are the committed `04-projects/groups.json`, if there is one and it is valid.

1. For every pair of a new group *A* and a previous group *B*, the Jaccard similarity is |A ∩ B| / |A ∪ B| over their evidence IDs.
2. Pairs with a similarity of 0.5 or more are taken best first: the highest similarity, then the larger overlap, then the new group's rank, then the previous ID. A pair is used when neither group is matched yet, so matching is one-to-one.
3. A matched group takes the previous group's ID. Every other group gets `ids.project_id(evidence_ids)`.
4. If an ID is already taken (possible only if two different evidence sets hash alike, or through a split's ID below), the group gets `ids.project_id(evidence_ids + ["#1"])`, then `#2`, and so on. Later runs carry that ID forward like any other.

An `id` the model writes is ignored and replaced. `match_projects.py` writes `groups.json` back with `id` first, evidence IDs sorted, and groups in rank order.

Because both sides are the model's groupings before decisions, a run on the same evidence with the same grouping gives every group its old ID. The decisions then give the same projects. When the evidence or the grouping changes, a group keeps its ID as long as it shares at least half of its combined items with a previous group.

## Decisions

### Records

`decisions/projects.json` is a list, applied in order:

| Action | Fields | Effect |
|---|---|---|
| `exclude` | | The project is left out of `projects.json`, and its evidence is in no project. |
| `merge` | `merge_with`: project IDs | Each named project's evidence moves into this project, and the named project is removed. This project keeps its ID, name, summary, role and scope, takes the best rank of those merged, and adds their rank reasons after its own. |
| `split` | `split_groups`: lists of evidence IDs | Each group is split off into a new project, of the listed items this project holds. This project keeps its ID and the rest. |
| `rename` | `name`, optional `summary` | Sets `internal_name`, and `summary` when given |
| `set_role` | `role` | Sets `role` |
| `set_scope` | `scope` | Sets `scope` |
| `set_rank` | `rank` | Moves the project to that position (or last, if there are fewer projects), keeping the order of the others |

Every record may carry `evidence_ids`: the project's evidence IDs when the decision was made. `decide.py` always stores them. `match_projects.py` uses them only to suggest where an orphan belongs. A record with a field its action does not use, or without a field it needs, is an error (`decisions/projects.json: /2: rename needs name`), and nothing is written.

A split's new project gets ID `ids.project_id(<the group as listed in the decision>)`, made unique as in step 4 above. The decision does not change, so the ID is the same on every run, and later decisions can name it. The project is placed right after the one it came from, is named `<name> (part 2)`, `(part 3)` and so on, has an empty summary and no rank reasons, and keeps the role and scope. The skill proposes a name and summary with a `rename` decision.

### Applying them

Projects start as the groups in rank order. Each decision applies in file order to the projects as the earlier decisions left them, so a decision can name a project that an earlier split created.

- A decision whose `project_id` is not a project at that point is **orphaned**, and does nothing. The reason names what happened to the project where known: `pj_… is not a project in this run`, `was excluded by decision 2`, `was merged into pj_… by decision 3`.
- A `merge_with` ID that is not a project, and a split group that names none of the project's items, are skipped with a `note:`. The rest of the decision applies. A merged project is often regrouped by the model on the next run, so a missing ID is expected.
- A split that would leave the project with no items is orphaned too, and nothing of it applies.

Then each project gets its rank (its position, from 1), `start` and `end`, and `metric_prompt`.

### Orphans

`match_projects.py` prints each orphan with the current project that shares the most of its `evidence_ids`, if any does:

```
orphaned: decision 2 (exclude pj_1d2c3b4a): pj_1d2c3b4a is not a project in this run; closest is pj_77e0a1c3 'Ledger export retries' (3 of its 4 items)
  fix: re-link it to a project with decide.py relink 2 PJ, or discard it with decide.py discard 2
```

It exits 3 while any orphan remains, even with `--commit`, and commits nothing. An orphaned `exclude` could otherwise let an excluded project back onto the resume under a new ID, and an orphaned `set_role` would silently stop applying.

`match_projects.py` also prints a `warning:` for each confirmed metric in `decisions/metrics.json` whose `project_id` is not a project in this run. Metrics belong to the wizard, so this never blocks.

### decide.py

`decide.py` is how checkpoint 2 records the engineer's choices. It works against the *current projects*: `04-projects.tmp/projects.json` while a checkpoint is in progress, else the committed `04-projects/projects.json`. With neither, it exits 1 and says to run `signals.py` and `match_projects.py` first.

- Every action checks that `PJ` is a current project, and stores that project's evidence IDs in `evidence_ids`.
- `merge PJ --with Q ...`: each `Q` is a current project, not `PJ`, and named once.
- `split PJ --group EV,EV --group EV`: every ID is one of `PJ`'s items, each is listed once, and at least one item stays in `PJ`.
- `set-rank PJ N`: `N` is from 1 to the number of current projects.
- `rename PJ --name NAME [--summary TEXT]`: the name is not empty.
- `exclude`, `rename`, `set-role`, `set-scope` and `set-rank` replace any earlier decision with the same action for the same project. The new record goes last, so it applies after everything the engineer saw. `merge` and `split` are added.
- `relink N PJ` records decision `N` again for `PJ`, with the same checks, and removes the old one. `discard N` removes decision `N`. `list` prints the decisions, numbered from 1.

It validates the whole file against the schema before writing it, and replaces it atomically, so a rejected change leaves the file as it was. It never runs `match_projects.py` itself: the skill runs it next to show the result.

## Projects

`projects.json` holds, for each project in rank order, `id`, `internal_name`, `summary`, `evidence_ids` (sorted), `role`, `scope`, `start`, `end`, `rank`, `rank_reasons` and `metric_prompt`:

- `start` is the month (`YYYY-MM`) of the earliest `created_at`, and `end` the month of the latest `created_at` or `closed_at`, of its items.
- `rank` runs from 1 to the number of projects.
- `metric_prompt` is true for ranks up to `N = config.metric_prompt_count(len(projects), percent, min, max)`, with `config.json` `metric_prompts`. With the defaults, 10 projects give 3 prompts and 20 give 6.

### Checkpoint 2 output

`match_projects.py` prints each project, then the excluded projects, the evidence in no project, the decisions and any orphans:

```
5 projects (4 carried from the last run, 1 new); metric prompts for the top 3
 1. pj_da2a2b53  Project Falcon checkout latency  lead, cross-team, 2025-02 to 2025-05  metric prompt
    Idempotency cache that cut checkout latency for Contoso Bank.
    3 items: 1 authored, 1 reviewed, 1 assigned; mentioned in no review
    reasons: authored the core PR and owned the epic; customer-facing latency impact
    decisions: set_role (1)
 ...
excluded: pj_1d2c3b4a 'Hackathon badge printer' (decision 2)
not in any project: 41 of 60 items, including 2 performance reviews
decisions: 3 applied, 0 orphaned
wrote 04-projects.tmp/groups.json and 04-projects.tmp/projects.json
```

## SKILL.md

1. Run `stage.py status`. If `02-evidence` is missing, stop and suggest `/resume-builder:collect`. If it is stale, tell the engineer and offer to collect again first. If `04-projects.tmp/groups.json` exists, checkpoint 2 was interrupted: go to step 5.
2. Run `signals.py`. Show the header line.
3. Read `04-projects.tmp/signals.json`, the titles and excerpts in `02-evidence/evidence.jsonl`, and each performance review's full text in `01-raw/reviews.jsonl` at its `raw_ref`. If `04-projects/groups.json` exists, start from it: keep a group as it was unless the evidence changed, so its ID and its decisions carry over.
4. Write `04-projects.tmp/groups.json`:
   - A group is one piece of work with one goal. Start from clusters: one cluster is usually one project, but split a cluster held together by a catch-all ticket, and join clusters that are clearly the same work (the same epic name, repository and time). Items in no group are fine.
   - List each evidence ID in at most one group. Never add a performance review.
   - `internal_name`: the name the evidence uses (the epic's title or codename). `summary`: one sentence of what the project did, from the titles and excerpts, with no number the evidence does not state.
   - `role`: `lead` when the engineer authored most of the changes, owned or created its epic, or started it; `core` when they authored a substantial share; `supporting` when their part is mostly reviews or small changes.
   - `scope`: `team` for one repository or Jira project and few contributors; `cross-team` for several repositories or Jira projects, or many contributors. `org` or `company` only when the evidence says so, such as a performance review or an epic describing organization-wide work. Never from size alone.
   - `rank` 1 to n by impact: scope, role, size, duration, and mentions in performance reviews, including mentions by name found in step 3. `rank_reasons`: one to three short facts from the signals or the evidence, such as `authored 12 of 15 pull requests` or `named in the 2025 H1 review`.
   - Do not write `id`, `start`, `end` or `metric_prompt`.
5. Run `match_projects.py`. On exit 1, fix `groups.json` as each line says and run it again. Check every `note:` about a cluster partly left out.
6. **Checkpoint 2.** Show the projects as printed, the excluded projects, and every orphan and warning. Explain that the top N get metric questions in the wizard. Ask the engineer to review the grouping (merge, split), the names, role, scope, ranking and exclusions. Record each change with one `decide.py` command, then run `match_projects.py` again and show the result. After a split, propose a name and summary for each new part and record them with `rename`. For each orphan, ask whether to re-link it to the suggested project or another one, or discard it. Never edit `decisions/projects.json` by hand, and never regroup `groups.json` to carry out a decision.
7. When the engineer approves, run `match_projects.py --commit`. Report the projects, the ones with metric prompts, the exclusions and the decisions applied, and every `warning:`.

To apply new decisions to a committed `04-projects` when the evidence has not changed, run `stage.py begin 04-projects --from-current` and continue at step 5.

## Changes to resume-core, fixtures and the architecture spec

1. New `signals.schema.json` and `project-groups.schema.json`, mapped in `FILE_SCHEMAS` as `04-projects/signals.json` and `04-projects/groups.json`. Every object in them is closed.
2. `project-decisions.schema.json`: `action` gains `set_rank`, with a new `rank` (integer, at least 1). `rename` gains an optional `summary`. `name` and `summary` must be non-empty. Fields per action are checked by `match_projects.py` and `decide.py`, since the schema validator has no conditionals.
3. Fixture: `04-projects/signals.json` and `04-projects/groups.json` are exactly the output of `signals.py` and `match_projects.py` for the fixture. The group's `role` is `core` and the fixture's `set_role` decision makes the project `lead`, so `projects.json` is unchanged. `decisions/projects.json` gains the `evidence_ids` that `decide.py` stores.
4. `pytest.ini` adds `skills/resume-analyze/scripts` to `pythonpath`. The test command and CI are unchanged, because analyze uses only the standard library.
5. The architecture spec: the plugin layout lists `decide.py`; the workspace tree lists `groups.json`; the Project contract describes ID continuity against `groups.json`, the dates and the metric prompt count; the Decisions table lists `set_rank`, `rank` and `summary`; the resume-analyze section points here; orphaned decisions block the commit.

## Error handling

| Case | Behavior |
|---|---|
| No evidence, or invalid evidence or config | `signals.py` exits 1. Nothing begun. |
| Evidence changed after `signals.py` | `match_projects.py` exits 1. Run `signals.py` and group again. |
| A group problem | Exit 1, one line per problem and a `fix:` line. The draft stays in `04-projects.tmp/` to fix. |
| Invalid decisions file | Exit 1 naming each record. The skill fixes it with `decide.py discard` and records the decision again. |
| Orphaned decision | Exit 3 with the closest current project. Nothing committed until it is re-linked or discarded. |
| Metric for a missing project | Warning. The wizard re-links or removes it. |
| Missing raw record | Warning. Its item adds no people. |
| Commit fails | Exit 1. The previous `04-projects/` stays. |

## Testing

- **Clusters:** links in both directions, a chain through a ticket and an epic, a performance review linking two clusters without joining them, links to non-evidence, order and names.
- **Signals:** every field on made-up evidence, including stats that skip reviews, repositories from keys, remotes and folders, Jira projects, `authored_first` both ways, open items, and mentions.
- **People:** GitHub REST and GraphQL, GitLab, Jira REST and CSV, the engineer left out ignoring case, distinct people counted once, epics created from the raw reporter or the role, and a missing raw file or line.
- **Groups:** each check failing on its own with its line; the note for a partly grouped cluster.
- **ID continuity:** no previous run, an identical grouping, a grown group (similarity at least 0.5), a changed group (below 0.5), one previous group wanted by two new ones, the exact tie at 0.5, the model's `id` ignored, and a forced ID collision.
- **Decisions:** each action, file order (a rename of a split's new part), the three orphan reasons, a skipped `merge_with` and split group, a split that would empty the project, set-rank past the end, invalid records, the closest-project suggestion, and metric warnings.
- **Metric prompts:** N after exclusions with the default and custom settings.
- **Runs:** a first run, decisions, then a second run with a regrouped draft that keeps every ID and decision; a merged project that the model regroups apart; `--from-current` reuse.
- **CLIs:** each `decide.py` command and rejection, replacement of an older decision, `relink` and `discard`, an unchanged file on error; `match_projects.py` exit 3 with and without `--commit`, the commit's inputs and `extra`; `signals.py` on missing or empty evidence.
- **Fixture end to end:** from the fixture's evidence and raw files, `signals.py` writes `signals.json` exactly as saved; with the saved groups as the draft, `match_projects.py --commit` writes the saved `groups.json` and `projects.json` byte for byte. The committed stage validates, and the fixture's bullets and metrics still name its project.

## Out of scope for v1

- Recognizing a project named in words in a performance review. The model reads the reviews for that.
- Joining one person's identities across sources for the contributor count.
- Grouping by text similarity. Clusters come only from links.
- Model-quality evaluation of grouping, role and ranking (the architecture spec's manual evals).
