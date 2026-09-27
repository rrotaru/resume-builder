# resume-build and commands: Design

- **Date:** 2026-09-27
- **Status:** Approved
- **Scope:** The `resume-build` skill, which runs the whole workflow and its four checkpoints and resumes an interrupted run; the scripts it needs (where the run stands, checkpoint 4's review, and the only writer of `decisions/attestations.json`); the ten command files; and the plugin and marketplace manifests. Also the resume-core change build needs. Follow-up spec 9, the last, of the [architecture spec](2026-09-24-resume-builder-architecture-design.md).

## Goal

Take the engineer from an empty folder to rendered resumes, one checkpoint at a time, and pick up where the last session stopped. Each earlier skill already writes its own stage, checks it and says how to continue it. resume-build decides which step comes next, hands the step to the skill that owns it, offers to reuse what is still fresh, and runs checkpoint 4, the final review, where the engineer decides new terms, confirms allowed-term notices, reviews the sanitized text and the reports, and accepts, reverts or edits every flagged job bullet. The commands and manifests make the skills installable as a Claude Code plugin and give each step the short name the scripts already print (`/resume-builder:wizard`).

## Gaps

The architecture spec and the roadmap leave these open:

1. **Which step is next.** `stage.py status` says whether each stage is missing, fresh or stale, but not why, not which drafts are in progress (`<stage>.tmp/`), and not which command continues them. Each skill describes only its own resume.
2. **Two stages are always fresh.** `01-raw` and `03-profile` record no inputs. A collection months old, or a resume file edited since the import, looks fresh.
3. **A stale stage has more than one fix.** A new project decision needs only `match_projects.py` on the committed grouping, changed evidence needs grouping again, and a wizard answer needs write to recommit its bullets unchanged. `status` does not say which input changed.
4. **Checkpoint 3 has no state.** The wizard writes only `decisions/`, and no stage records `decisions/wizard.json`. Whether questions are open is known only to `questions.py`.
5. **Attestations have no writer.** "Nothing else writes attestations; resume-ats never does." Hand-written JSON could attest a hash no flag holds, or another job's bullet.
6. **Checkpoint 4 has no list.** Its material is spread over `07-sanitized/new-terms.json`, `rcore.terms.allowed_notices`, sanitize apply's printout (gone after the session that ran it), each version's `report.json`, and each job's flags and attestations.
7. **Skills cannot name each other's paths.** Portability rule 1 forbids `../<skill>/` outside resume-core, so the orchestrator cannot run another skill's scripts by path.
8. **Commands and manifests** are named in the plugin layout, with no contents and no format.

## Decisions

| Topic | Decision |
|---|---|
| Orchestration | resume-build's `SKILL.md` walks the steps in order and hands each one to the skill that owns it, by name ("follow the resume-analyze skill"), never by a path into its folder. The owning skill's instructions and scripts do the work, so a step behaves the same run standalone or inside build (gap 7). |
| Where the run stands | `progress.py` prints each step's state, the stage inputs that made a stage stale, the drafts in progress, and the one command that continues the first step not done. Every session starts with it, so an interrupted run resumes from `decisions/` and the drafts (gaps 1 and 3). |
| Collect | `progress.py` shows when `02-evidence` was built and whether `config.json`'s time range ends before that. The engineer decides whether to collect again. A `01-raw.tmp/` is continued, never begun again (gap 2). |
| Import | `progress.py` compares `03-profile/source.json` with `config.json` `resume_path` and the file's current hash. A different path or hash is `changed`: import again. With no resume in `config.json` and no import, import is skipped (gap 2). |
| Checkpoint 3 | Not tracked. Before write, sanitize apply or ats begins again, the wizard runs until `questions.py` prints `wizard: no open questions`. With nothing open that is one command (gap 4). |
| Attestations | `attest.py` is the only writer of `decisions/attestations.json`. It records `accept` or `edit` for a flag of a committed job version only while the flag holds the bullet's current text hash, and can withdraw one. The file is validated and replaced atomically (gap 5). |
| Checkpoint 4 | `final_review.py` prints the review in a fixed order and counts the open items: stale stages, undecided new terms, facts holding a denied term, and flags not accepted, reverted or edited. Notices are shown every time and confirmed every time; nothing records them (gap 6). |
| Commands | `commands/<name>.md` for the ten names in the plugin layout. Each is one line that hands `$ARGUMENTS` to the skill of that name, with `disable-model-invocation: true`, so the model uses the skills and the engineer has the short names (gap 8). |
| Manifests | `.claude-plugin/plugin.json` with the plugin's metadata and no `version`, so installs follow the repository's commits; `.claude-plugin/marketplace.json` makes the repository its own marketplace, with the plugin at `./` (gap 8). |
| resume-core | `rcore.stages.stale_inputs`: for each committed stage, the recorded inputs that make it stale and why. `status` is computed from it, so the two never disagree (gap 3). |

## Skill layout

```
skills/resume-build/
  SKILL.md
  scripts/
    progress.py            # CLI: each step's state and the next step
    final_review.py        # CLI: checkpoint 4's material and its open items
    attest.py              # CLI: accept, edit or withdraw a flagged job bullet in decisions/attestations.json
    rbuild/
      common.py            # errors, workspace files, reading and validating
      steps.py             # the steps, their states and notes, and the next step
      jobs.py              # committed job versions, their flags and attestations
      final.py             # checkpoint 4's sections and open items
commands/
  build.md  init.md  collect.md  import.md  analyze.md
  wizard.md  write.md  sanitize.md  ats.md  render.md
.claude-plugin/
  plugin.json
  marketplace.json
skills/resume-core/scripts/rcore/
  stages.py                # gains stale_inputs
```

Every script uses only the standard library and imports `rcore` as portability rule 6 allows. `progress.py` reads one file outside the workspace, the resume `config.json` names, to hash it as resume-import did.

## Command line

```
uv run scripts/progress.py --workspace WS
uv run scripts/final_review.py --workspace WS
uv run scripts/attest.py --workspace WS accept SLUG BULLET
uv run scripts/attest.py --workspace WS edit SLUG BULLET
uv run scripts/attest.py --workspace WS withdraw SLUG BULLET
uv run scripts/attest.py --workspace WS list
```

| Script | Exit | Meaning |
|---|---|---|
| `progress.py` | 0 | The steps and the next one printed |
| | 1 | Error: an input that does not validate (`config.json`, `03-profile/source.json`, `decisions/terms.json`, `decisions/attestations.json`, `07-sanitized/new-terms.json`, a committed job version). The lines name it and what writes it. |
| `final_review.py` | 0 | The review printed, with or without open items |
| | 1 | Error: no committed `08-ats`, or an invalid input as above |
| `attest.py` | 0 | Recorded, withdrawn, listed, or nothing to change (said so) |
| | 1 | Rejected: no such committed job, no such bullet, a bullet that is not flagged or changed after the claim diff, nothing to withdraw, or an invalid file. `decisions/attestations.json` is unchanged. |
| All | 2 | Usage error |

## Steps

A run has eleven steps. Each is owned by one skill, which the build hands it to:

| # | Step | Checkpoint | Skill | Writes |
|---|---|---|---|---|
| 1 | `init` | | resume-init | `config.json`, empty `decisions/` files |
| 2 | `collect` | 1: sources | resume-collect | `01-raw`, `02-evidence` |
| 3 | `import` | | resume-import | `03-profile` |
| 4 | `analyze` | 2: projects | resume-analyze (`decide.py` for every choice) | `04-projects`, `decisions/projects.json` |
| 5 | `scan` | | resume-sanitize, scan half | `05-terms` |
| 6 | `wizard` | 3: wizard | resume-wizard (`answer.py`) | `decisions/profile.json`, `terms.json`, `metrics.json`, `wizard.json` |
| 7 | `write` | | resume-write | `06-bullets` |
| 8 | `apply` | | resume-sanitize, apply half | `07-sanitized` |
| 9 | `ats` | | resume-ats: the general resume, then each posting | `08-ats` |
| 10 | `review` | 4: final review | resume-build (`final_review.py`, `attest.py`), with the wizard, sanitize apply and ats | `decisions/attestations.json` |
| 11 | `render` | | resume-render | `out` |

### States

`progress.py` gives each step one state:

| State | Steps | Meaning |
|---|---|---|
| `done` | init | `config.json` is valid and every `decisions/` file exists |
| `missing` | all but wizard and review | not built yet (for init: no `config.json`, or a `decisions/` file is missing) |
| `draft` | collect to ats | a draft is in progress in `<stage>.tmp/` |
| `stale` | collect, analyze to render | committed, and `stages.stale_inputs` names why |
| `changed` | import | committed, but `config.json` names another file or the file changed since the import |
| `none` | import | no import and no resume in `config.json`: the engineer has none, and the step is skipped |
| `fresh` | collect to render | committed and up to date |
| `check` | wizard | checkpoint 3 has no state; `questions.py` decides |
| `waiting` | review | `08-ats` is not fresh yet |
| `open`, `ready` | review | `final_review.py` has open items, or none |

The collect step's stage is `02-evidence`, with `01-raw` behind it. A draft wins over every other state: an interrupted step is continued before anything else about it.

## Next step

The next step is the first step, in order, that is not `done`, `fresh` or `none`, skipping the wizard. Review is skipped when it is `ready` and render is fresh; render itself always comes through review, so checkpoint 4 is never skipped before a render. When that step is write, apply or ats and it is not a draft, checkpoint 3 comes first: `next: wizard: checkpoint 3 until questions.py prints 'wizard: no open questions' (resume-wizard); then <the step>`. The wizard can have questions whatever the stages say (a new candidate term, a skipped metric the engineer now has), and asking an empty wizard costs one command.

Each state and cause has one command, named in the owning skill's terms:

| Step | State and cause | Next |
|---|---|---|
| init | missing: no `config.json` | create the workspace and `config.json` (resume-init) |
| init | missing: a `decisions/` file | run resume-init again: `init_workspace.py` creates only what is missing |
| collect | draft holding a `<source>.partial.jsonl` | continue the paused fetch in `01-raw.tmp/` (resume-collect step 5); never run `stage.py begin 01-raw`, which deletes it |
| collect | draft | continue the collection in `01-raw.tmp/` (resume-collect steps 5 to 8); never run `stage.py begin 01-raw`, which deletes it |
| collect | missing, with `01-raw` committed | `link.py` builds `02-evidence` from the committed `01-raw` (resume-collect step 8) |
| collect | missing | checkpoint 1: confirm the sources and collect (resume-collect) |
| collect | stale | `01-raw` changed since `02-evidence` was built: `link.py` (resume-collect step 8) |
| import | draft holding `profile.json` | check and commit it with `check_profile.py --commit` (resume-import step 5) |
| import | draft holding `resume.txt` | map `03-profile.tmp/resume.txt` into `profile.json`, then `check_profile.py --commit` (resume-import steps 4 and 5) |
| import | draft, empty | run `extract_text.py` again (resume-import) |
| import | missing | import `<the file config.json names>` (resume-import), or, when it is not found, ask the engineer for the resume |
| import | changed | import it again (resume-import); wizard answers the new import moves become `moved:` questions (resume-wizard) |
| analyze | draft holding `groups.json` | continue checkpoint 2 with `match_projects.py` (resume-analyze step 5) |
| analyze | draft holding `signals.json` | group the evidence into `04-projects.tmp/groups.json` (resume-analyze step 3) |
| analyze | draft, empty | run `signals.py` again (resume-analyze step 2) |
| analyze | missing | checkpoint 2: find and review the projects (resume-analyze) |
| analyze | stale: only `decisions/projects.json` or `config.json` | apply it to the committed grouping: `stage.py begin 04-projects --from-current`, then `match_projects.py` (resume-analyze step 5) |
| analyze | stale: anything else | the evidence changed: group again with `signals.py`, starting from the last `groups.json` (resume-analyze) |
| scan | draft holding `candidates.json` | `scan.py --commit` (resume-sanitize, scan step 5) |
| scan | draft | `scan.py` again (resume-sanitize, scan) |
| scan | missing or stale | `scan.py` (resume-sanitize, scan) |
| write | draft holding `bullets.json` | `write.py --commit` (resume-write step 6) |
| write | draft | `write.py` again, with `--from-current` when `06-bullets` is committed, then `write.py --commit` (resume-write) |
| write | missing | write the bullets and stories: `write.py`, then `write.py --commit` (resume-write) |
| write | stale: only `decisions/profile.json` or `decisions/metrics.json` | a wizard answer: recommit the bullets with `write.py --from-current`, then `write.py --commit`; bullets that still pass keep their IDs, and a new metric needs a bullet that cites it (resume-write) |
| write | stale: anything else | revise the bullets: `write.py --from-current`, then `write.py --commit` (resume-write) |
| apply | draft holding `new-terms.json` | `apply.py --commit`; if it says the inputs changed, `apply.py` again (resume-sanitize, apply step 5) |
| apply | draft, missing or stale | `apply.py`, then `apply.py --commit` (resume-sanitize, apply) |
| ats | draft | continue with `ats.py --commit`, or start over from the committed stage with `stage.py begin 08-ats --from-current` (resume-ats) |
| ats | missing | draft and commit the general resume, then each posting (resume-ats) |
| ats | stale | re-check every version: `stage.py begin 08-ats --from-current`, then `ats.py --commit`; redraft a version it refuses (`ats.py`, `ats.py --job SLUG`) or remove it (`ats.py --remove SLUG`) (resume-ats) |
| review | open | checkpoint 4: `final_review.py` lists the open items |
| review | ready, render missing or stale | checkpoint 4 (`final_review.py`), then render (resume-render) |
| none | | every stage is fresh and `out/` holds the resumes; for another posting, `ats.py --jd FILE` (resume-ats), then checkpoint 4 and render |

A draft that another step's draft or stale stage comes before still waits: `progress.py` shows it in its row, and the step that owns it continues it when its turn comes. Rebuilding an earlier stage never deletes a later draft, except where that step's own command does (`signals.py`, `scan.py`, `write.py` and `apply.py` without `--commit` begin a fresh draft).

### Collect and import

`01-raw` and `03-profile` record no inputs, so `stage.py status` calls them fresh as soon as they exist.

- **Collect.** The note gives the items per source from `02-evidence/_stage.json` `extra` and the date it was built (`created_at`), with its age in days. When it was built before today and `config.json` `time_range.end` is null, it adds `the time range is open, so work since then is not in it`; when the range ends after the build date, `the time range ends <end>, so work since then is not in it`. The skill then asks whether to collect again. A change to `config.json` (a username, a repository, the time range) is not visible here: the skill collects again when the engineer changes one.
- **Import.** For a committed `03-profile`:
  - `config.json` `resume_path` null: `fresh`, noting that `config.json` names no resume.
  - `rcore.config.resolve_path(workspace, resume_path)` differs from `source.json` `path`: `changed`, `config.json names <path>, not the imported <path>`.
  - The file is gone: `fresh`, noting that it is no longer there, so the import stays.
  - The file's sha256 differs from `source.json` `sha256`: `changed`, `<path> changed since the import`.
  - Otherwise `fresh`, `unchanged since the import`.

  With no committed `03-profile`: `none` when `resume_path` is null (the engineer has no resume; the wizard asks for the name and contact details, and project bullets have no place until jobs are added), otherwise `missing`.

### What progress.py prints

For a workspace built to the end of ats on 2026-09-27, with the fixture's decisions and a text resume:

```
resume-builder run in /home/jordan/resume-workspace (target role: Senior Backend Engineer)
 1. init     done     config.json and decisions/
 2. collect  fresh    4 items (github 2, jira 1, review 1), built 2026-09-27 (today)
 3. import   fresh    /home/jordan/resume.txt, unchanged since the import
 4. analyze  fresh    1 project (0 excluded), metric prompts for 1, 1 decision
 5. scan     fresh    2 candidates
 6. wizard   check    checkpoint 3: questions.py lists what is open
 7. write    fresh    4 bullets (1 quantified), 1 story
 8. apply    fresh    1 of 4 bullets changed, 0 new terms
 9. ats      fresh    general, fintech-sre: 1 flagged, 0 open
10. review   ready    checkpoint 4: no open items
11. render   missing
next: review: checkpoint 4 (final_review.py), then render (resume-render)
```

A stale stage's note lists why, from `stages.stale_inputs`: `decisions/projects.json changed`, `02-evidence/evidence.jsonl is gone`, `04-projects is stale`. A draft's note names what is in it: `04-projects.tmp/groups.json: checkpoint 2 in progress`, `01-raw.tmp/github.partial.jsonl: a paused fetch`, `08-ats.tmp/ with general, fintech-sre`.

## Checkpoint 4

### final_review.py

`final_review.py` needs a committed `08-ats`, and prints, in this order:

1. **Stages.** Each stage from `02-evidence` to `08-ats` that is missing or stale (`03-profile` also when `changed`), each an open item: the review is of the current workspace.
2. **New terms.** Each term in `07-sanitized/new-terms.json` that `decisions/terms.json` does not decide (`rcore.terms.key`), with its kind, proposed replacement and places. Each is an open item.
3. **Notices.** Every line of `rcore.terms.allowed_notices`. The engineer confirms each allowed term is a different word; if it is not, the wizard changes the decision (`answer.py term TERM --replacement TEXT`, or `remove-term`).
4. **Sanitized text.** Each bullet whose text `07-sanitized/bullets.json` changed from `06-bullets/bullets.json` (`was:` and `now:`), each changed line of `stories.md` (by `difflib` over the lines), and each profile string `07-sanitized/profile.json` changed.
5. **Facts.** Each fact field of the effective profile a tailored resume may copy (`rcore.facts.fact_values`) that holds a denied term, as sanitize apply warns. One outside `skills` keywords is an open item: the wizard sets a replacement value (`fact:` question). A keyword is left out of the resumes by resume-ats and is shown as a note.
6. **Versions.** For `general`, then each job in slug order, from its `report.json`: bullets used of those in `07-sanitized/bullets.json`, estimated lines against the budget, the keyword counts, each keyword missing with evidence and where (at most three places, `and N more`), each bullet left out with its reason and text, and each warning. For a job, each flag with its status and reasons.
7. **Open items**, each with its fix, then `checkpoint 4: N open items` or `checkpoint 4: no open items`.

A flag's status comes from the job's `resume.json`, `flags.json` and `decisions/attestations.json`, by the rules `check_flags.py` applies:

| Status | When | Open |
|---|---|---|
| `accepted`, `edited` | an attestation for this job, bullet and current text hash, with that action | no |
| `flagged` | the flag holds the current text hash, and nothing attests it | yes: accept, revert or edit |
| `changed after the claim diff` | the text's hash is neither the flag's nor `checked`'s | yes: `ats.py --commit` |
| `not in resume.json` | a flag or `checked` entry for a bullet the resume no longer holds | yes: `ats.py --commit` |
| `used twice` | a `bullet_id` twice in one resume | yes: redraft |

A job's open flag items are exactly the lines `rcore.flags.check_job` prints for it, so the review and render agree.

For the workspace above:

```
checkpoint 4: final review
stages: fresh from 02-evidence to 08-ats
new terms: none undecided
notices: none
sanitized bullets: 1 of 4 changed
  b_1  was: Cut p99 checkout latency 40% for Contoso Bank by building a Redis-backed idempotency cache for Project Falcon in Go
       now: Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency cache for real-time fraud-detection platform in Go
sanitized stories: 3 lines changed
  3  was: ## Project Falcon checkout latency
     now: ## Real-time fraud-detection platform checkout latency
  5  was: - **Situation:** Checkout for Contoso Bank missed its p99 latency target at peak traffic.
     now: - **Situation:** Checkout for a top-10 US bank missed its p99 latency target at peak traffic.
  6  was: - **Task:** Jordan led the fix for the Project Falcon checkout path.
     now: - **Task:** Jordan led the fix for the real-time fraud-detection platform checkout path.
sanitized profile: no prose changed
facts holding a denied term: none
general: 4 of 4 bullets, 36 of 50 lines (1 page for 88 months of experience)
  keywords: 4 covered, 1 missing with evidence, 1 missing without evidence
    missing with evidence  metrics  ev_56410ed1
  left out: none
  warnings: none
fintech-sre: 4 of 4 bullets, 36 of 50 lines (1 page for 88 months of experience)
  keywords: 5 covered, 1 missing with evidence, 2 missing without evidence
    missing with evidence  metrics  ev_56410ed1
  left out: none
  warnings: none
  flags: 1, 0 open
    b_1  accepted  Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency cache in Go, raising checkout SLO compliance
      introduces 'SLO compliance', which no cited source mentions
checkpoint 4: no open items
```

With open items, they come before the last line:

```
open items: 2
  new term 'Fabrikam': decide it with the wizard (resume-wizard), then run sanitize apply and ats again
  fintech-sre b_1 is flagged: accept it (attest.py accept fintech-sre b_1), or revert or edit it (resume-ats: ats.py --revise fintech-sre)
checkpoint 4: 2 open items
```

### Resolving each item

- **A stale stage:** finish the steps `progress.py` names first.
- **A new term** or **a fact holding a denied term:** the wizard, until `questions.py` prints no open questions (a `fact:` answer makes `06-bullets` stale). Then recommit write when it is stale (`write.py --from-current`, then `--commit`), sanitize apply (`apply.py`, new terms, `--commit`) and ats (`stage.py begin 08-ats --from-current`, `ats.py --commit`, redrafting what it refuses).
- **A notice** the engineer does not confirm: change the term decision in the wizard, then apply and ats again.
- **Wording** the engineer wants changed: an awkward replacement is reworded in the wizard (`answer.py term TERM --replacement TEXT`); a bullet or story in resume-write (`--from-current`). Then apply and ats again.
- **A keyword missing with evidence** the engineer has: the wizard adds it to the skills (`answer.py add /skills/<i>/keywords KEYWORD`). That makes `06-bullets` stale: recommit write, sanitize apply, then draft the version again (`ats.py` or `ats.py --job SLUG`, since a kept version holds only the skills it was drafted with) and commit.
- **A bullet left out:** `no place` needs the job in the profile (the wizard, `answer.py profile /work/-/name …`); `not selected` comes back by drafting the version again and selecting it.
- **A flag.** Show the text, its original (`ats.py --revise SLUG` prints it as `was:`) and the reasons, and ask:
  - **Accept:** `attest.py accept SLUG BULLET`.
  - **Revert:** `ats.py --revise SLUG`, set the text in `08-ats.tmp/jobs/SLUG/resume.json` to the original, `ats.py --commit`. A text equal to its original is never flagged.
  - **Edit:** `ats.py --revise SLUG`, write the engineer's text, `ats.py --commit`, which runs the claim diff again. If the new text is still flagged and the engineer keeps it, `attest.py edit SLUG BULLET`.

  A flag on `summary` (the job's `basics.summary`) is handled the same way.

Run `final_review.py` again after each round, until it prints `checkpoint 4: no open items` and the engineer has confirmed every notice and approved the text. Then render.

### attest.py

`accept` and `edit` record `{"job_slug", "bullet_id", "text_sha256", "action"}` in `decisions/attestations.json`:

- `SLUG` is a committed job version: `08-ats/jobs/SLUG/resume.json` and `flags.json` exist and validate. Attestations name the committed text; a draft in `08-ats.tmp/` gets a `note:` that the attestation holds after its commit only if the text is unchanged.
- `BULLET` is a `bullet_id` in the resume's `x-highlights`, or `summary` for `basics.summary`.
- `flags.json` holds a flag for `BULLET` whose `text_sha256` is the hash of its current text. Otherwise the command is refused: a bullet that is not flagged has nothing to attest, and one whose text changed after the claim diff needs `ats.py --commit` first.
- The record's `text_sha256` is the flag's. An attestation for the same job, bullet and hash is replaced in place (`accept` after `edit` changes the action), and saying the same thing again records nothing. Attestations for other hashes are kept, so an attestation for an unchanged text survives a redraft.
- `edit` is for a text the engineer changed at checkpoint 4 that is still flagged; `accept` for the text as ats wrote it. Both need the same flag.

`withdraw SLUG BULLET` removes the attestation for the bullet's current text, so its flag is open again. `list` prints every attestation, numbered, and whether it applies to a committed text now.

The file is validated against `attestations.schema.json` before and after the change and replaced through a temporary file. On an error, `attest.py` prints `error:` lines and `decisions/attestations.json unchanged`, and exits 1. After recording it prints the job's open flags (`fintech-sre: no open flags`), and a `warning:` when `08-ats` is stale.

```
recorded: fintech-sre b_1 accept for its current text: Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency cache in Go, raising checkout SLO compliance
fintech-sre: no open flags
```

`08-ats` never records `decisions/attestations.json`, so attesting leaves it fresh. `out` records it, so render runs again.

## Commands and manifests

### Commands

`commands/<name>.md` gives each step its short name, `/resume-builder:<name>`, the name every script's hints already print:

```markdown
---
description: Collect your work evidence from GitHub, GitLab, Jira, local git and performance reviews (checkpoint 1)
argument-hint: "[--workspace PATH]"
disable-model-invocation: true
---

Use the `resume-builder:resume-collect` skill with these arguments: $ARGUMENTS
```

| Command | Skill | Arguments |
|---|---|---|
| `build` | resume-build | `[--workspace PATH] [--jd FILE ...]` |
| `init` | resume-init | `[--workspace PATH] [--target-role "ROLE"]` |
| `collect` | resume-collect | `[--workspace PATH]` |
| `import` | resume-import | `[--workspace PATH] [--resume FILE]` |
| `analyze` | resume-analyze | `[--workspace PATH]` |
| `wizard` | resume-wizard | `[--workspace PATH]` |
| `write` | resume-write | `[--workspace PATH] [--from-current]` |
| `sanitize` | resume-sanitize | `[scan\|apply] [--workspace PATH]` |
| `ats` | resume-ats | `[--workspace PATH] [--jd FILE [--job SLUG]]` |
| `render` | resume-render | `[--workspace PATH] [--target general\|SLUG ...] [--paper letter\|a4] [--no-pdf] [--check]` |

- The body is that one line: the command passes its arguments to its skill and holds no instructions of its own. All logic stays in the skills, so another harness loses only the short names.
- `disable-model-invocation: true` keeps the commands out of the model's listing: the model uses the skills, which Claude Code also offers as `/resume-builder:resume-<name>`. Commands are the older plugin format, and skills supersede them, but only a command gives a skill a name other than its folder's.
- `$ARGUMENTS` appears only in command files; the skill lint still forbids it in skills.

### Manifests

`.claude-plugin/plugin.json`:

```json
{
  "name": "resume-builder",
  "description": "Build an evidence-backed engineering resume: collect your pull requests, reviews, tickets and performance reviews, find your most impactful projects, and produce ATS-friendly PDF, DOCX and plain-text resumes whose every claim cites a source.",
  "author": {"name": "rrotaru", "url": "https://github.com/rrotaru"},
  "homepage": "https://github.com/rrotaru/resume-builder",
  "repository": "https://github.com/rrotaru/resume-builder",
  "keywords": ["resume", "career", "ats", "engineering", "job-search"]
}
```

`.claude-plugin/marketplace.json`:

```json
{
  "name": "resume-builder",
  "owner": {"name": "rrotaru", "url": "https://github.com/rrotaru"},
  "description": "The resume-builder plugin.",
  "plugins": [
    {"name": "resume-builder", "source": "./",
     "description": "Build an evidence-backed engineering resume, one checkpoint at a time."}
  ]
}
```

- The plugin uses the default layout (`skills/`, `commands/`), so the manifest declares no component paths. `skills/` holds ten skills, installed as a set (portability rule 4).
- No `version` in either file: Claude Code then versions a relative-path plugin in a git-hosted marketplace by its commit, so an install follows the repository. A pinned version would keep users on one copy until someone changes it.
- No `license`: the repository has none to name.
- `claude plugin validate .` passes, with a warning that the development `CLAUDE.md` at the root is not loaded as context and one about the missing `version`. Both are expected.
- The engineer installs with `/plugin marketplace add rrotaru/resume-builder`, then `/plugin install resume-builder@resume-builder`.

## SKILL.md

1. **Where the run stands.** Run `scripts/progress.py --workspace WS` (`--workspace` from the arguments, default `./resume-workspace`, absolute). Show the table. If init is `missing`, follow resume-init first. Reuse every fresh stage unless the engineer wants it rebuilt: offer to collect again when the note says later work is not in it, and to import again when import is `changed`. To rebuild a fresh stage, follow its skill from the start; later stages go stale on their own.
2. **Continue** at the step `next:` names, then take the steps in order, running `progress.py` again after each one. Each step is its skill's `SKILL.md`, followed as written, including its checks and what it reports; build adds only the order and the checkpoints.
3. **Collect (checkpoint 1)** with resume-collect. It shows the data notice, confirms the sources, the resume file and the time range, and never runs `stage.py begin 01-raw` over a `01-raw.tmp/`.
4. **Import** with resume-import, unless import is `none` (the engineer has no resume).
5. **Analyze (checkpoint 2)** with resume-analyze. Every choice the engineer makes is recorded with resume-analyze's `decide.py`, never by editing `decisions/projects.json` or regrouping `groups.json`, and orphaned decisions are re-linked or discarded before the commit.
6. **Scan** with resume-sanitize, scan half.
7. **Wizard (checkpoint 3)** with resume-wizard: run its `questions.py` until it prints `wizard: no open questions`, again after each round, since deciding a term can open a `fact:` question. Run it before write, apply or ats begins again.
8. **Write** with resume-write, `--from-current` when bullets are committed. A `note:` about a metric prompt without a metric after checkpoint 3 means the engineer skipped it.
9. **Apply** with resume-sanitize, apply half.
10. **ats** with resume-ats: the general resume, then each posting from the `--jd` arguments or that the engineer gives.
11. **Checkpoint 4.** Run `scripts/final_review.py`. Show every section. Resolve each open item as [Resolving each item](#resolving-each-item) says, show every `notice:` and have the engineer confirm each, and have them review the changed bullets, story lines and profile prose, the reports and every flag. Record an accepted or still-flagged edited bullet only with `scripts/attest.py`. Run `final_review.py` again until it prints `checkpoint 4: no open items` and the engineer approves.
12. **Render** with resume-render. Show its `notice:` lines again.
13. Report what was built, what was reused, the decisions recorded, and the files in `out/`.

Never edit a stage folder or `decisions/` by hand, and never weaken or skip a check. If the engineer stops partway, say which step comes next: `progress.py` finds it in the next session.

## Changes to resume-core, fixtures and the architecture spec

1. `rcore.stages.stale_inputs(workspace)`: for each committed stage, the list of `(input, why)` that make it stale, `why` being `changed`, `missing` or `stale` (the input is in a stage that is itself stale); empty for a fresh stage. `status` is derived from it, and it restores an interrupted swap first, as `status` does.
2. resume-core `SKILL.md`: `stale_inputs` among the helpers; `decisions/attestations.json` is written only by resume-build's `attest.py`, and `decisions/projects.json` only by resume-analyze's `decide.py`. resume-ats's `SKILL.md` names `attest.py` as the writer of attestations.
3. `pytest.ini` adds `skills/resume-build/scripts` to `pythonpath`. The test command and CI do not change: build uses only the standard library.
4. No fixture changes. The fixture's `decisions/` is what a first run records through the scripts (a test rebuilds it), and its attestation is what `attest.py accept fintech-sre b_1` writes.
5. The architecture spec: the plugin layout lists build's scripts and the command files; "Commands" describes their format and the manifests; the Decisions table names `attest.py` as the writer of `attestations.json`; the resume-build section points here; staleness mentions `stale_inputs`.
6. README: installing the plugin and the commands.
7. The roadmap: piece 9 ticked, and "Start here" says the checklist is done and points to the small follow-ups.

## Error handling

| Case | Behavior |
|---|---|
| No workspace or `config.json` | `progress.py` shows init `missing`, and every other step `missing`. |
| An invalid input | `progress.py` and `final_review.py` exit 1 naming the file and what fixes it. |
| An interrupted step | Its draft is shown and continued with the owning skill's command; a later step's draft waits for its turn. |
| A stage stale because of a decision | `progress.py` names the input and the cheapest rebuild. |
| The resume file changed or moved | Import is `changed`: import again. The wizard then asks about answers the import moved. |
| No committed `08-ats` | `final_review.py` exits 1 naming the ats step. |
| Attesting a bullet that is not flagged, or changed after the claim diff | `attest.py` exits 1; `decisions/attestations.json` unchanged. |
| A notice the engineer does not confirm | The wizard changes the term decision; apply and ats run again. |
| The engineer stops partway | Nothing is lost: every choice is in `decisions/` or a draft, and `progress.py` names the next step. |

## Testing

- **`stale_inputs`:** each reason (changed, missing, an input in a stale stage); every reason listed, not only the first; `status` agrees with it on every stage; an interrupted swap is restored.
- **Steps:** each state of each step: drafts with and without the model's file, a paused fetch, `01-raw` committed without `02-evidence`, the collection note (today, days ago, a time range that ends before or after it), each import case (no resume, missing, unchanged, another path, a changed file, a file gone), stale causes and their commands (a project decision, changed evidence, a wizard answer, a term decision), the checkpoint 3 gate before write, apply and ats but not before a draft, review `waiting`, `open` and `ready`, and everything fresh.
- **Checkpoint 4:** every section on the fixture; a stale stage; an undecided new term and a decided one; a notice; changed bullets, story lines and profile prose; a fact and a keyword holding a denied term; keywords missing with evidence (at most three places); left-out bullets; each flag status; the open items equal `check_flags.py`'s lines; no committed `08-ats`.
- **attest.py:** accept and edit record the flag's hash; the fixture's attestation is what accepting writes; refused for an unknown job, a draft-only job, an unknown bullet, an unflagged bullet, a changed text, and an invalid file, leaving the file unchanged; the same attestation twice; accept after edit; withdraw; list; the note for a draft and the warning for a stale `08-ats`.
- **Must promises:** checkpoint 2's choices recorded only with `decide.py` (the skill says so, and a decision makes `04-projects` stale with the from-current command); every allowed-term notice shown at checkpoint 4; accept, revert and edit each end with `check_flags.py` passing, and only `attest.py` writes attestations (no other script names the file for writing); attesting leaves `08-ats` fresh and makes `out` stale; an attestation for an unchanged text survives a redraft; a wizard answer makes `06-bullets` stale and write recommits it with the same IDs; each interrupted stage resumes with the command the roadmap names; `03-profile` and `01-raw` freshness as above.
- **A first run end to end:** from an empty workspace, following `progress.py`'s `next:` at every step, with the fixture's files standing in for the engineer's sources and the model's output, and every decision recorded through `configure.py`, `decide.py`, `answer.py` and `attest.py`: every committed stage equals the fixture's saved files, `decisions/` equals the fixture's, `final_review.py` reports no open items and render's gate passes. With render's dependencies, `render.py --no-pdf` then leaves every step fresh and `next:` says there is nothing to do.
- **Commands and manifests:** the ten command files and no others; each one's front matter and single delegating line naming an existing skill; `plugin.json` and `marketplace.json` parse and have the fields and names above; the marketplace entry's source is the repository root, which holds `plugin.json`.
- **Skill lint:** resume-build passes the existing portability checks.

## Out of scope for v1

- Recording notice confirmations, or keywords the engineer declined to add. Both are asked again at the next checkpoint 4.
- Detecting a changed `config.json` source, username or time range after collection. The engineer collects again after changing one.
- Running a step without the model. Every script-only part runs in CI; the model's parts need a harness.
- Versioned releases of the plugin.
