---
name: resume-collect
description: Collect the engineer's work history for a resume-builder workspace (checkpoint 1). Confirms sources and the data notice, fetches pull requests, merge requests, reviews, issues and tickets from GitHub, GitLab and Jira connectors or export files, reads commits from local git repositories and text from performance review files, then builds 02-evidence/evidence.jsonl with stable IDs, links and duplicates removed. Use when the engineer asks to collect or refresh their work evidence, or when resume-build reaches the collect step.
---

# resume-collect

Follow `../resume-core/SKILL.md` for workspace conventions.

- Resolve `scripts/...`, `references/...` and `../resume-core/...` against this skill's own folder, not against the current directory.
- Run commands from the engineer's project directory, not from the skill folder.
- Always pass `--workspace` explicitly, preferably as an absolute path.

Every later claim cites the evidence built here, so an item must be exactly what the source says and must belong to the engineer. Scripts decide ownership, dates, IDs and links. Never edit `02-evidence/` or a raw file's items by hand.

## Steps

1. Run `uv run scripts/configure.py --workspace WS show`. If `config.json` is missing, run resume-init first.
2. **Data notice.** If `show` says it is not accepted, run `configure.py --workspace WS notice` and show its text to the engineer unchanged. Ask whether to continue. Only on a clear yes, run `configure.py --workspace WS notice --accept`. On no, stop: nothing may be fetched or read. Every collect script refuses to run until the notice is accepted.
3. **Checkpoint 1: confirm the sources.** Look at your tools for connectors that search GitHub pull requests, GitLab merge requests or Jira issues. With the engineer, confirm each of these and record it with `configure.py`:
   - The time range: `time-range --start YYYY-MM-DD --end YYYY-MM-DD` (`none` leaves an end open).
   - GitHub, GitLab and Jira, each one of: `source github --mode connector --username NAME`, `source jira --mode export --username NAME --export PATH` when there is no connector (see `references/sources.md` for how to export), or `source gitlab --mode skip`. Ask for each username. Never assume it from a name or an email.
   - Local repositories, `repos PATH ...`, and the emails or names the engineer commits under, `git-authors EMAIL ...`.
   - The folder of exported performance reviews (PDF, DOCX, TXT or Markdown), `reviews PATH`.
   - The existing resume, `resume PATH` (resume-import reads it later).
4. Run `uv run ../resume-core/scripts/stage.py --workspace WS begin 01-raw`. **Exception:** if `01-raw.tmp/` already holds a `<source>.partial.jsonl`, a paused fetch is waiting. Do not run `begin`, which would delete it. Continue it in step 5.
5. **Connector sources.** Fetch each one as `references/sources.md` describes. Write every page the connector returns as one line of `01-raw.tmp/<source>.jsonl`: `{"query": "<the search you ran>", "items": [<the results exactly as returned>]}`. Do not reword, trim or reorder the items. If a connector fails partway, rename the file to `<source>.partial.jsonl`, add `"cursor"` (what fetches the next page) to its last line, and offer three choices:
   - **Retry:** continue from the cursor, then rename the file back to `<source>.jsonl`.
   - **Continue without the source:** delete the file and run `configure.py source <source> --mode skip`.
   - **Pause:** stop here and leave `01-raw.tmp/` as it is. The next run continues it.
6. **Files.** Run each script that applies:
   - `uv run scripts/ingest_export.py --workspace WS --source <source>` for each export source.
   - `uv run scripts/ingest_git_log.py --workspace WS` if there are repositories. On exit 3, show the report: it names the identities searched and each repository's most frequent authors. Ask which identity is the engineer's, set it with `git-authors`, and run it again.
   - `uv run scripts/ingest_reviews.py --workspace WS` if there is a review folder. Show every `skipped` line: a scanned PDF needs a DOCX or TXT copy. Show each date that came from "the file's modification date", and suggest adding the review's date to the file name (`2025-07-15 review.pdf`) if it is wrong, then run it again.
7. **Check each source.** Run `uv run scripts/normalize_<source>.py --workspace WS` for each connector and export source. It writes nothing. On exit 3, show its report (the queries used and the authors seen) and ask for another username or email, or check the time range. Never guess a username. Fetch again with the corrected one.
8. Run `uv run scripts/link.py --workspace WS`. It checks the raw files against `config.json`, builds `02-evidence/evidence.jsonl`, and commits `01-raw` and `02-evidence`. On exit 1 nothing is committed. Each `error:` line says how to fix it.
9. Report to the engineer:
   - the items kept per source and kind, and the time range covered;
   - the bad rows (the first 10 per source, with file and line), which were skipped;
   - how many items were filtered as not theirs or outside the time range, and how many duplicates were removed;
   - every `warning:` line.

## What the scripts guarantee

- An item becomes evidence only if one of the engineer's identities authored, reviewed, was assigned or reported it. Performance reviews are always kept.
- A pull request found by a `reviewed-by:<username>` search, or whose reviews include the engineer, is a `review`. Its size is not credited to the engineer.
- IDs depend only on the source and the item's key, so re-collecting gives the same IDs.
- Links connect an item to Jira keys, pull requests, merge requests and issues it mentions, and a ticket to its epic, but only when the target is itself evidence.
- The same item fetched twice appears once. A squash or merge commit of the engineer's own pull request is dropped in favour of the pull request.

## Output

```
01-raw/
  github.jsonl  gitlab.jsonl  jira.jsonl   # pages as fetched or loaded from exports
  git.jsonl                                # one commit per line
  reviews.jsonl                            # one review file per line, with its text
02-evidence/
  evidence.jsonl                           # one evidence item per line, sorted by created_at
  _stage.json                              # extra: items per source, skipped_rows, filtered, duplicates
```
