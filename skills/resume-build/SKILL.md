---
name: resume-build
description: Run the whole resume-builder workflow in a workspace, from an empty folder to rendered resumes, one checkpoint at a time, and pick up where an interrupted run stopped. Shows where the run stands and which stages can be reused, hands each step to the skill that owns it (collect with checkpoint 1, import, analyze with checkpoint 2, the sanitize scan, the wizard as checkpoint 3, write, sanitize apply, ats for the general resume and each job posting, render), and runs checkpoint 4, the final review, where the engineer decides new terms, confirms allowed-term notices, reviews the sanitized text and the reports, and accepts, reverts or edits every flagged job bullet. Use when the engineer asks to build, update or continue their resume, or when a render check sends a flagged bullet to checkpoint 4.
---

# resume-build

Follow `../resume-core/SKILL.md` for workspace conventions.

- Resolve `scripts/...` and `../resume-core/...` against this skill's own folder, not against the current directory.
- Run commands from the engineer's project directory, not from the skill folder.
- Always pass `--workspace` explicitly, preferably as an absolute path: the workspace the engineer named (`--workspace PATH`), else `./resume-workspace`. Job postings given as `--jd FILE` are tailored at the ats step.

Each step belongs to another resume-builder skill. Follow that skill's `SKILL.md` as written, with its checks and its report, and run its scripts from its own folder: this skill adds only the order, the reuse of fresh stages and checkpoint 4. `scripts/progress.py` says where the run stands and which command continues it, so every session, including one that resumes an interrupted run, starts there. Every choice the engineer makes is in `decisions/` or in a draft, so stopping loses nothing.

## Steps

1. **Where the run stands.** Run `uv run scripts/progress.py --workspace WS` and show the table. Each step is `done` or `fresh` (reuse it), `missing`, `draft` (an interrupted step, continued first), `stale` (with the inputs that changed), `changed` (import: the resume file changed, or `config.json` names another), `none` (import: no resume), `check` (the wizard) or, for the review, `waiting`, `open` or `ready`. The last line, `next:`, names the step to continue and its command.
   - If init is `missing`, follow the **resume-init** skill first.
   - Reuse every fresh stage unless the engineer wants it rebuilt. Offer to collect again when the collect note says work since then is not in it (the time range is open or ends after the collection), and to import again when import is `changed`. To rebuild a fresh stage, follow its skill from the start; the later stages go stale on their own.
2. **Continue** at the step `next:` names, then take the steps below in order, running `progress.py` again after each one. A step that is `fresh` is skipped. A `draft` is always continued with the command `progress.py` prints, never begun again.
3. **Collect (checkpoint 1)** with the **resume-collect** skill: the data notice, the sources, the time range, the review folder and the resume file. A `01-raw.tmp/` is a collection in progress, possibly a paused fetch (`<source>.partial.jsonl`): continue it, and never run `stage.py begin 01-raw`, which deletes it. With `01-raw` committed and no `02-evidence`, or `01-raw` changed since, `link.py` builds `02-evidence` again. The engineer collects again after changing a source, a username, a repository or the time range.
4. **Import** with the **resume-import** skill, unless import is `none` (the engineer has no resume: the wizard asks for the name and contact details, and project bullets have no place until jobs are added with the wizard).
5. **Analyze (checkpoint 2)** with the **resume-analyze** skill. Record every change the engineer asks for (merge, split, rename, exclude, role, scope, rank) only with resume-analyze's `decide.py`, never by editing `decisions/projects.json` or regrouping `groups.json`: its evidence snapshots are what orphaned decisions are matched against. Re-link or discard every orphaned decision before the commit. When only a decision changed since the commit, `progress.py` says to apply it to the committed grouping (`stage.py begin 04-projects --from-current`, then `match_projects.py`).
6. **Scan** with the **resume-sanitize** skill, scan half.
7. **Wizard (checkpoint 3)** with the **resume-wizard** skill. Run its `questions.py` until it prints `wizard: no open questions`, again after each round of answers, because deciding a term can open a `fact:` question. Checkpoint 3 has no state of its own: run it before write, sanitize apply or ats begins again (`progress.py` puts it first in `next:`). A wizard answer makes `06-bullets` stale, and everything after it.
8. **Write** with the **resume-write** skill. When bullets are committed, begin with `write.py --from-current`, so reviewed wording and bullet IDs stay. After a wizard answer, `write.py --from-current` then `write.py --commit` recommits the bullets unchanged; a new metric needs a bullet that cites it. A `note:` about a metric prompt without a metric after checkpoint 3 means the engineer skipped it.
9. **Apply** with the **resume-sanitize** skill, apply half. An interrupted apply (`07-sanitized.tmp/new-terms.json`) continues with `apply.py --commit`; if it says the inputs changed, run `apply.py` again.
10. **ats** with the **resume-ats** skill: the general resume first, then each posting from the `--jd` arguments or that the engineer gives. A stale `08-ats` is re-checked with `stage.py begin 08-ats --from-current` and `ats.py --commit`; redraft a version the commit refuses (`ats.py`, `ats.py --job SLUG`) or remove it (`ats.py --remove SLUG`).
11. **Checkpoint 4: the final review.** Run `uv run scripts/final_review.py --workspace WS` and show every section. Resolve the items as described below, then run it again, until it prints `checkpoint 4: no open items` and the engineer has confirmed every notice and approved the text.
12. **Render** with the **resume-render** skill. Show its `notice:` lines again.
13. Report what was built and what was reused, the decisions recorded at each checkpoint, and the files in `out/`. If the engineer stops partway, say which step comes next; `progress.py` finds it in the next session.

## Checkpoint 4

`final_review.py` prints, in order: stages that are not fresh, new terms nobody has decided, allowed-term notices, the bullets, story lines and profile prose sanitize apply changed, fact fields holding a denied term, then each version with its length, keyword coverage, bullets left out, warnings and, for a job, each flag. The open items come last, each with its fix.

- **A stage that is not fresh:** finish the steps `progress.py` names first. The review is of the current workspace.
- **New terms** and **facts holding a denied term:** run the wizard until `questions.py` prints no open questions (it asks about `07-sanitized/new-terms.json`, then `fact:` questions). Then recommit write if a wizard answer made it stale (`write.py --from-current`, `write.py --commit`), run sanitize apply again (it is stale, since `07-sanitized` records the term decisions), and re-check ats.
- **Notices.** Show every `notice:` line: an allowed term that looks like a denied term. Ask the engineer to confirm that each allowed term is a different word. If it is not, change the decision in the wizard (`answer.py term TERM --replacement TEXT`, or `answer.py remove-term TERM`), then run sanitize apply and ats again. Notices are not recorded, so they are confirmed at every checkpoint 4.
- **The sanitized text.** Show every changed bullet, story line and profile string. Mechanical replacement can read awkwardly: reword the replacement in the wizard (`answer.py term TERM --replacement TEXT`), or the bullet or story with resume-write (`write.py --from-current`), then sanitize apply and ats again.
- **Keywords missing with evidence:** ask whether each belongs in the engineer's skills. On yes, record it with the wizard (`answer.py add /skills/<i>/keywords KEYWORD`), recommit write, run sanitize apply, then draft that version again (`ats.py` or `ats.py --job SLUG`, since a kept version holds only the skills it was drafted with) and commit it. Never add a keyword to a resume yourself.
- **Bullets left out:** `no place` means the project falls in no job of the profile, which the wizard can add (`answer.py profile /work/-/name …`); `not selected` comes back by drafting the version again and keeping it. Show every warning.
- **Flags.** For each flagged job bullet (or `summary`, the job's `basics.summary`), show its text, its original (`ats.py --revise SLUG` prints it as `was:`) and the reasons, and ask whether to accept, revert or edit it:
  - **Accept:** `uv run scripts/attest.py --workspace WS accept SLUG BULLET`.
  - **Revert:** `ats.py --revise SLUG`, set the text in `08-ats.tmp/jobs/SLUG/resume.json` to its original, and run `ats.py --commit`. The original text is never flagged.
  - **Edit:** `ats.py --revise SLUG`, write the engineer's wording, and run `ats.py --commit`, which runs the claim diff again. If the new text is still flagged and the engineer keeps it, `uv run scripts/attest.py --workspace WS edit SLUG BULLET`.

Only `scripts/attest.py` writes `decisions/attestations.json`. It records a flag only while the flag holds the bullet's current text; `attest.py withdraw SLUG BULLET` takes an attestation back, and `attest.py list` shows them all. Attesting leaves `08-ats` fresh, and an attestation for an unchanged text survives a redraft; render runs again, since `out` records the attestations.

Never edit a stage folder or `decisions/` by hand, never record a choice the engineer did not make, and never weaken or skip a check.

## What the scripts guarantee

- `progress.py` reads each stage's `_stage.json` and names the inputs that changed. It calls `03-profile` `changed` when `config.json` names another file or the file's hash differs from `03-profile/source.json`, and shows when `02-evidence` was built, since `01-raw` and `03-profile` record no inputs and so always look fresh to `stage.py status`.
- Each draft is continued with the owning skill's command, and the first step that is not done is named with the one command that continues it.
- `final_review.py` lists every allowed-term notice, every undecided new term and every flag, and its open flag items are exactly what render's flags check would refuse.
- `attest.py` records `{job_slug, bullet_id, text_sha256, action}` for a flag of a committed job version only when the flag holds the hash of the bullet's current text, validates the file, and replaces it atomically. It never changes `08-ats`.

## Output

```
decisions/
  attestations.json   # accept or edit, per job, bullet and text hash, written only by attest.py
```

Every other file is written by the skill that owns its step.
