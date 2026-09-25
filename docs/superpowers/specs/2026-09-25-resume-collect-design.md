# resume-collect: Design

- **Date:** 2026-09-25
- **Status:** Approved
- **Scope:** The `resume-collect` skill (checkpoint 1): confirming sources and the data notice, fetching or loading work data into `01-raw/`, and normalizing, linking and de-duplicating it into `02-evidence/evidence.jsonl`. Also the resume-core changes collect needs. This is follow-up spec 4 of the [architecture spec](2026-09-24-resume-builder-architecture-design.md).

## Goal

Turn the engineer's work history into `02-evidence/evidence.jsonl`: one item per pull request, merge request, code review, issue, ticket, epic, commit and performance review, each with a stable ID and links to related items. Every later claim cites these IDs, so an item must say exactly what the source says. It must belong to the engineer, carry the right role, and point back to the raw record it came from.

## Gaps

The architecture spec leaves these open:

1. **Connector output has no shape.** A GitHub search result for a pull request the engineer reviewed looks the same as any other pull request. A normalizer that sees only the item cannot tell that the engineer reviewed it.
2. **Exports never reach the workspace.** An export file sits outside the workspace. `stage.py commit` cannot hash it, and `raw_ref` cannot point into it. Nothing defines who writes `01-raw/` for an export.
3. **Git has no identity.** `config.json` has usernames for GitHub, GitLab and Jira, but nothing names the engineer's git author email.
4. **IDs are global.** `rcore.ids.assign_evidence_ids` lengthens IDs that collide across *all* items. A normalizer that runs on one source cannot assign final IDs.
5. **Review dates are undefined.** `created_at` is required, but a review file has no date field.
6. **`01-raw/` has several writers and no commit rule.** The model writes connector pages, and scripts write git and review data. Nothing says who commits the stage, or where an interrupted fetch waits.
7. **The data notice is not enforced.** Only the skill's instructions stop the model from collecting before the engineer agrees.
8. **Links and duplicates are loosely defined.** "Connects items and removes duplicates" does not say which references count, or which copy survives.
9. **Review text needs a document reader.** resume-import already has a tested PDF and DOCX reader. The portability rules stop another skill from importing it.

## Decisions

| Topic | Decision |
|---|---|
| Raw format | Every line of `01-raw/<source>.jsonl` is a page: `{"items": [...]}` holding records exactly as fetched, plus optional `query`, `cursor`, `export` and `row`. The query is kept because it proves why an item was fetched, for example `reviewed-by:jrivera` (gap 1). |
| Exports | `ingest_export.py` loads an export file into `01-raw/<source>.jsonl`, one item per page line, with the file path and row. Everything downstream reads only `01-raw/` (gap 2). |
| Git identity | New optional `config.json` field `git_authors`: the engineer's commit emails or names, matched exactly and case-insensitively (gap 3). |
| One place for IDs | `link.py` runs every normalizer in process, then assigns IDs over all items at once, links, de-duplicates and commits. The `normalize_*.py` scripts run one normalizer and print a report without writing anything, so a fetch can be checked before linking (gap 4). |
| Review dates | A `YYYY-MM-DD` date in the file name, otherwise the file's modification date. The report says which, so the engineer can rename a file whose date is wrong (gap 5). |
| Stage writing | `stage.py begin 01-raw` starts collection. The model and the ingest scripts write into `01-raw.tmp/`. `link.py` commits `01-raw` and then `02-evidence`. An interrupted fetch stays in `01-raw.tmp/<source>.partial.jsonl`, and `link.py` refuses to run while one exists (gap 6). |
| Data notice | `configure.py notice` prints it and `--accept` records the time. Every ingest, normalize and link script exits 1 until `data_notice_acknowledged_at` is set (gap 7). |
| Links | Directed, from an item to the items it references: Jira keys, GitHub and GitLab references and URLs, and a ticket's parent. A reference links only when the target is itself evidence. Nothing is inferred from similar wording (gap 8). |
| Duplicates | Items with the same `source` and `native_key` merge into one. The copy with the stronger role is kept. A git commit that is an authored pull request's squash or merge commit is dropped in favour of the pull request (gap 8). |
| Document reader | The PDF, DOCX, TXT and Markdown reader moves from `rimport/extract.py` to `rcore/documents.py`. Its PDF and DOCX dependencies are imported only inside the functions that read those formats (gap 9). |
| Ownership | Only the engineer's items become evidence: authored, reviewed, assigned or reported by one of the configured identities. Everything else is filtered out and counted. |
| Time range | Items outside `config.json` `time_range` are filtered out, except performance reviews, which the engineer chose file by file. |

## Skill layout

```
skills/resume-collect/
  SKILL.md
  references/
    sources.md             # per source: connector queries, export formats, fields read
  scripts/
    configure.py           # CLI: data notice, sources, repos, git authors, reviews folder, time range
    ingest_export.py       # CLI: export file -> 01-raw.tmp/<source>.jsonl
    ingest_git_log.py      # CLI: local repos -> 01-raw.tmp/git.jsonl
    ingest_reviews.py      # CLI: review files -> 01-raw.tmp/reviews.jsonl (pypdf, python-docx)
    normalize_github.py    # CLI: report on one source, write nothing
    normalize_gitlab.py
    normalize_jira.py
    link.py                # CLI: normalize all, IDs, links, duplicates, commit 01-raw and 02-evidence
    rcollect/
      common.py            # config and notice, raw pages, timestamps, excerpts, the Draft record
      exports.py           # CSV, JSON and JSONL export files
      github.py  gitlab.py  jira.py  git.py  reviews.py   # one normalizer each
      refs.py              # references found in text
      merge.py             # duplicates, IDs and links
skills/resume-core/scripts/rcore/
  documents.py             # moved from resume-import: document text extraction
```

`ingest_reviews.py` pins `pypdf==6.19.0` and `python-docx==1.2.0`, the versions `extract_text.py` and `render.py` pin, so the existing test command covers it. Every other collect script uses only the standard library. All scripts import `rcore` as portability rule 6 allows.

## Command line

```
uv run scripts/configure.py --workspace WS show
uv run scripts/configure.py --workspace WS notice [--accept]
uv run scripts/configure.py --workspace WS time-range --start YYYY-MM-DD|none --end YYYY-MM-DD|none
uv run scripts/configure.py --workspace WS source github|gitlab|jira --mode connector|export|skip [--username U] [--export PATH]
uv run scripts/configure.py --workspace WS repos [PATH ...]
uv run scripts/configure.py --workspace WS git-authors [EMAIL_OR_NAME ...]
uv run scripts/configure.py --workspace WS reviews PATH|none
uv run scripts/configure.py --workspace WS resume PATH|none
uv run scripts/ingest_export.py --workspace WS --source github|gitlab|jira
uv run scripts/ingest_git_log.py --workspace WS
uv run scripts/ingest_reviews.py --workspace WS
uv run scripts/normalize_github.py --workspace WS [--raw REL]      # likewise gitlab, jira
uv run scripts/link.py --workspace WS
```

| Exit | Meaning |
|---|---|
| 0 | Done |
| 1 | Error: no or invalid `config.json`, data notice not accepted, a missing file or folder, `01-raw.tmp/` not begun, or (for `link.py`) raw data that does not match the configured sources. Nothing written. |
| 2 | Usage error |
| 3 | Nothing found for the engineer: no commits by the git authors, no review file with text, or no item for the username. The report shows what was searched. |

## Configuration

`configure.py` is the only way the skill changes `config.json`. It validates the whole file against `config.schema.json` before writing it, and replaces it atomically, so a rejected change leaves the file as it was.

- `notice` prints the [data notice](#data-notice). `notice --accept` sets `data_notice_acknowledged_at` to the current UTC time (`YYYY-MM-DDTHH:MM:SSZ`). If it is already set, it is left unchanged.
- `source` adds or replaces the entry for that type. `connector` and `export` need `--username`. `export` also needs `--export`, an existing file stored as an absolute path. `connector` and `skip` set `export_path` to null.
- `repos` sets `local_repos` to the given folders. Each must be inside a git work tree and is stored as an absolute path. With no paths, the list is cleared.
- `git-authors` sets `git_authors`. An entry containing `@` is an email; anything else is an author name.
- `reviews` sets `reviews_dir` to an existing folder, stored absolute. `resume` sets `resume_path` to an existing file, stored absolute. `none` clears either one.
- `time-range` takes real dates, and `start` may not be after `end`. `none` leaves that end open.
- `show` prints the sources, repos, authors, reviews folder, resume, time range and notice state.

Relative paths given on the command line resolve against the current directory, like `extract_text.py --resume`. Relative paths already in `config.json` resolve against the workspace (`rcore.config.resolve_path`).

### Data notice

```
Before anything is collected: resume-builder sends your work data to the AI model
provider that runs this assistant. That includes the titles, descriptions and
metadata of your pull requests, merge requests, code reviews, issues and tickets,
the messages of your commits in the local repositories you name, and the full
text of any performance reviews you provide. Your employer's policies may limit
where this data may go. Everything collected is also stored in the workspace
folder on this computer. Continue only if you may share this data.
```

## Raw data (`01-raw/`)

`01-raw/` has no schema (the roadmap says so), but every file in it has the same line format so that one reader serves all sources:

```json
{"query": "is:pr reviewed-by:jrivera created:>=2023-01-01", "cursor": "3", "items": [{...}, {...}]}
```

- `items` (required): records exactly as the connector, export or script produced them.
- `query`: the search or request used. The GitHub and GitLab normalizers read it to recognize reviewed items, and a no-results report shows it.
- `cursor`: whatever fetches the next page (a page number, an `after` cursor, a `startAt`).
- `export` and `row`: the export file and its row, line or item number, written by `ingest_export.py`.

A line that is not valid JSON, or not an object with an `items` array, is a bad row. `raw_ref` in evidence is `01-raw/<file>:<line>#/items/<index>`, such as `01-raw/github.jsonl:2#/items/0`.

| File | Written by | Items |
|---|---|---|
| `github.jsonl` | the model (connector) or `ingest_export.py` | GitHub REST, GraphQL or `gh` CLI pull requests and issues |
| `gitlab.jsonl` | the model or `ingest_export.py` | GitLab REST or `glab` merge requests and issues |
| `jira.jsonl` | the model or `ingest_export.py` | Jira REST issues, or rows of a Jira CSV export |
| `git.jsonl` | `ingest_git_log.py` | one commit per line |
| `reviews.jsonl` | `ingest_reviews.py` | one review file per line, with its full text |
| `<source>.partial.jsonl` | the model | pages of a fetch that failed partway, the last carrying its `cursor` |

The model writes each page the connector returns as one line, with the query it used. [`references/sources.md`](../../../skills/resume-collect/references/sources.md) lists the queries and the fields each normalizer reads.

### Exports

`ingest_export.py --source S` reads `export_path` from that source's entry (mode `export`). It writes `01-raw.tmp/S.jsonl`, one line per item, with `export` set to the file's absolute path and `row` set to its position:

- `.csv` (Jira only): UTF-8, BOM allowed. Each record becomes an object keyed by header. A header that repeats, as `Labels` does in Jira exports, becomes a list of its non-empty values. `row` is the line the record starts on.
- `.json`: an array of items, a page object (`items`, or Jira's `issues`, with an optional `query`), or an array of page objects. `row` is the item's 1-based position. A page's `query` is kept on each of its lines.
- `.jsonl` or `.ndjson`: one item or page per line. `row` is the line number. A line that is not valid JSON is written as `{"export": ..., "row": n, "error": "invalid JSON: ...", "items": []}`, so linking reports it as a bad row and processes the rest.

A file that cannot be read or parsed as a whole (not UTF-8, invalid `.json`) is an error, and nothing is written.

### Git

`ingest_git_log.py` reads `local_repos` and `git_authors` (an empty `git_authors` is an error). For each repository it runs

```
git -C REPO log --branches --remotes --tags --no-merges -F -i --author=ID ... [--since=START]
    --shortstat --format=%x00%H%x1f%an%x1f%ae%x1f%aI%x1f%B%x00
```

and keeps a commit only if its author email equals an email in `git_authors`, or its author name equals a name there, ignoring case. `--author` only narrows the search. All refs are read because a local `HEAD` may be stale, and each commit appears once by hash. Merge commits carry no authored change and are skipped. `--since` filters on the committer date, which is never earlier than the author date, so the time range is applied exactly on the author date afterwards.

Each item is `{"sha", "repo", "remote", "author_name", "author_email", "authored_at", "message", "files", "additions", "deletions"}`. `remote` is `origin`'s URL reduced to `host/path` (for example `github.com/northwind/ledger`), or null. A folder that is not a git work tree is an error, and nothing is written. If no commit matches in a repository, the report shows the identities searched and that repository's five most frequent authors, so the engineer can name another identity. Exit 3 if no repository had a match.

### Reviews

`ingest_reviews.py` reads every `.pdf`, `.docx`, `.txt`, `.md` and `.markdown` file under `reviews_dir`, recursively, in path order. It skips hidden files. It lists other files as unsupported. Text comes from `rcore.documents`. A file with no text (a scanned PDF), a password-protected file or an unreadable one is reported and skipped, and the rest are read. Each item is `{"file", "path", "sha256", "format", "date", "date_from", "text"}`. `file` is the path relative to `reviews_dir`. `date` is the first `YYYY-MM-DD` in the file name that is a real date (`date_from: "name"`), or else the file's modification date in UTC (`"modified"`). Exit 3 if no file yielded text.

## Normalization

Each normalizer turns raw items into drafts: evidence items without `id` or `links`, plus the references found in their full text.

### Common rules

- **Timestamps** become UTC `YYYY-MM-DDTHH:MM:SSZ`. Accepted: ISO 8601 with `Z`, `±HH:MM` or `±HHMM` and optional fractions, a bare `YYYY-MM-DD` (midnight), `YYYY-MM-DD HH:MM[:SS]`, and Jira's `d/Mon/yy h:mm AM` with a two- or four-digit year and English month abbreviations. A time without an offset is read as UTC. Anything else makes the item a bad row. Nothing is guessed.
- **Title**: whitespace runs become one space, and the ends are trimmed.
- **Excerpt**: the body with HTML comments removed (pull request templates are full of them), whitespace runs as one space, trimmed, then the first 500 characters. It is always present, and empty when there is no body.
- **Labels**: names, in order, without duplicates.
- **Ownership**: a username matches when it equals one of the item's identity fields, ignoring case. An item that matches no role is *filtered* (not the engineer's), not bad.
- **Time range**: an item is kept when `created_at` is on or before `end`, and `closed_at` (or, while it is open, the present) is on or after `start`, comparing UTC dates. Commits are kept when their author date is inside the range. Reviews are always kept. Others are filtered.
- **Bad rows** are items missing a required field or holding a value that does not parse. Each is reported as `<file>:<line>: <reason>`, the first 10 per source, and all are counted.

### GitHub

Items may be REST (search results or pull request objects), GraphQL nodes, or `gh` CLI JSON. The normalizer reads the first field present:

| Evidence | Read from |
|---|---|
| repository | `base.repo.full_name`, `repository.nameWithOwner`, `repository.full_name`, `repository_url`, or the path of `html_url`/`url` |
| number | `number`, or the web URL |
| `url` | `html_url`, or `url` unless it is an API URL |
| author | `user.login`, `author.login` |
| pull request or issue | `pull_request` present, `isPullRequest`, `/pull/` in the web URL, or pull request fields such as `merged_at` or `head` |
| `created_at` | `created_at`, `createdAt` |
| `closed_at` | `merged_at`, `mergedAt`, `pull_request.merged_at`, then `closed_at`, `closedAt` |
| `state` | `merged` when merged, otherwise `open` or `closed` in lower case |
| `stats` | `additions`, `deletions`, and `changed_files` or `changedFiles`, when all three are present |
| branch | `head.ref`, `headRefName` (read for Jira keys) |
| merge commit | `merge_commit_sha`, `mergeCommit.oid`, when merged |

- `native_key` is `owner/repo#number`, the same for a pull request and an issue because they share numbers.
- **Pull request, author** (`kind: pr`, `engineer_role: author`) when the author is the username.
- **Review** (`kind: review`, `engineer_role: reviewer`) when the username appears in the item's `reviews` or `latestReviews` (a list, or GraphQL `nodes`), or the page's `query` contains `reviewed-by:<username>`. `created_at` is the engineer's first review's `submitted_at`/`submittedAt` when present, otherwise the pull request's. A review has no `stats`: the size of the change is the author's work.
- **Issue** (`kind: issue`): `assignee` when the username is among `assignees` (or `assignee`), otherwise `author` when the engineer opened it.
- Anything else is filtered.

### GitLab

REST or `glab` JSON. `native_key` is `references.full` (`group/project!12` for a merge request, `group/project#7` for an issue), or is built from `web_url` (`/-/merge_requests/12`, `/-/issues/7`) and `iid`. Author is `author.username`. `state` is `merged`, `open` (for `opened`), `closed` or `locked`. `closed_at` is `merged_at`, then `closed_at`. Merge requests read `source_branch` for Jira keys, and `merge_commit_sha` and `squash_commit_sha` for duplicates. There are no `stats`.

- **Merge request** (`kind: mr`): `author` for the author. `reviewer` when the username is in `reviewers` or the query contains `reviewer_username=<username>`. `assignee` when it is only in `assignees`.
- **Issue** (`kind: issue`): `assignee`, then `author`.

### Jira

REST issues (`key` and `fields`, API version 2 or 3, including Atlassian Document Format descriptions, which are read as plain text) or CSV rows (`Issue key`, `Summary`, and the other columns, matched ignoring case).

| Evidence | REST | CSV |
|---|---|---|
| `native_key` | `key` | `Issue key` |
| `title` | `fields.summary` | `Summary` |
| `kind` | `epic` when `fields.issuetype.name` is `Epic`, else `ticket` | `Issue Type` |
| `state` | `fields.status.name` | `Status` |
| `created_at`, `closed_at` | `fields.created`, `fields.resolutiondate` | `Created`, `Resolved` |
| `url` | `<site>/browse/<key>`, where `<site>` is `self` up to `/rest/` | null (the CSV does not name the site) |
| parent | `fields.parent.key`, `fields.epic.key` | `Parent`, `Parent key`, `Custom field (Epic Link)`. A numeric parent is an `Issue id` looked up among the rows. |

The username matches `name`, `key`, `accountId`, `emailAddress` or `displayName` of `fields.assignee` and `fields.reporter` (CSV: `Assignee`, `Assignee Id`, `Reporter`, `Reporter Id`). The role is `assignee`, then `reporter`.

### Git and reviews

- **Commit:** `source: git`, `kind: commit`, `engineer_role: author`, `native_key` is the full hash, so a commit in two clones is one item. The title is the message's first line and the excerpt the rest. `stats` come from `--shortstat`. `url` is `https://github.com/<path>/commit/<sha>` or `https://gitlab.com/<path>/-/commit/<sha>` for those two hosts, else null.
- **Review:** `source: review`, `kind: perf_review`, `engineer_role: subject`, `native_key` is `file` without its extension (`2025-H1` for `2025-H1.pdf`), so a PDF and a DOCX of the same review merge. The title is the first non-empty line of the text, and the excerpt is the text after it. `created_at` is `date` at midnight UTC. `url`, `closed_at` and `state` are null.

## Links and duplicates

### References

`rcollect/refs.py` finds references in an item's full text (title, body, branch or message), not in the 500-character excerpt:

- **Jira keys:** `[A-Z][A-Z0-9_]+-[1-9][0-9]*` standing alone. Branch names are matched in upper case, so `pay-42-cache` refers to `PAY-42`.
- **GitHub:** web URLs `/<owner>/<repo>/pull/<n>` or `/issues/<n>` on any host, `owner/repo#n`, and a bare `#n` inside the item's own repository.
- **GitLab:** web URLs `/<path>/-/merge_requests/<n>` or `/-/issues/<n>`, `group/project!n` and `group/project#n`, and a bare `!n` or `#n` inside the item's own project.
- **Jira parent:** a ticket refers to its parent or epic.
- A commit reads its message against its remote's path, as GitHub and as GitLab. Only references that name real evidence survive, so trying both is exact.
- Review text and Jira descriptions have no repository, so only keys and URLs count there.

A reference links only when an evidence item with that `source` and `native_key` exists, compared ignoring case for GitHub and GitLab. `links` holds the IDs it resolves to, sorted, never the item's own ID.

### Duplicates

1. **Same `source` and `native_key`.** The same item fetched twice (overlapping pages, two queries, a connector and an export, one commit in two clones, one review in two formats) merges into one. The kept copy has the stronger role (`author`, `assignee`, `reviewer`, `reporter`, `subject`), then `stats`, then the earlier raw line. Labels and references are combined. So when the engineer both wrote a pull request and commented on it as a review, one `pr` item remains.
2. **Squash and merge commits.** A commit is dropped when an authored pull request or merge request names it as its merge or squash commit, or when its subject ends in `(#n)` (GitHub's squash format) and `<remote path>#n` is an authored pull request. Its references move to the pull request. A commit whose pull request is not the engineer's is kept, and links to it.

The report counts both kinds.

### IDs and order

After duplicates are removed, `rcore.ids.assign_evidence_ids` runs once over every `(source, native_key)`, so a collision anywhere lengthens both IDs to 12 characters. `evidence.jsonl` is sorted by `created_at`, then `id`, with keys sorted on each line (`wsio.write_jsonl`).

## link.py

1. Load and validate `config.json`, and check that the data notice is accepted.
2. Choose the raw folder: `01-raw.tmp/` if it exists (a collection in progress), else the committed `01-raw/`.
3. Check the raw folder against the configuration and stop with every problem listed:
   - a `*.partial.jsonl` file (an unfinished fetch);
   - a GitHub, GitLab or Jira source in mode `connector` or `export` without its raw file, or with no username, or a raw file for a source that is missing or set to `skip`;
   - `git.jsonl` without `local_repos`, or the reverse; `reviews.jsonl` without `reviews_dir`, or the reverse.
   Other files are ignored with a warning.
4. Normalize every raw file, remove duplicates, assign IDs, resolve links, and validate every item against `evidence.schema.json`.
5. If the raw folder is `01-raw.tmp/`, commit `01-raw` (no inputs).
6. `stages.begin(ws, "02-evidence")`, write `evidence.jsonl`, and commit with inputs `["01-raw"]` and `extra`:
   `{"items": {"github": 14, "jira": 9, ...}, "skipped_rows": 2, "filtered": 31, "duplicates": 3}`.
7. Print the bad rows, the per-source report, and `committed 02-evidence: <n> items (...)`.

`config.json` is not a stage input. Changing a username or the time range means fetching again, which rewrites `01-raw` and so makes `02-evidence` stale. `01-raw` records no inputs, like `03-profile`, so `stage.py status` always calls it fresh. When to collect again is resume-build's decision (roadmap piece 9).

The `normalize_*.py` scripts run steps 1 and 4 for one source (default `01-raw.tmp/<source>.jsonl` when collecting, else `01-raw/`), print the same report, and write nothing. Exit 3 when no item belongs to the username. The report then lists the queries in the file and the most frequent authors seen, and the skill asks the engineer for another username or email.

## SKILL.md

1. Run `configure.py show`. If `config.json` is missing, run resume-init first.
2. **Data notice.** If it is not accepted, run `configure.py notice`, show its text unchanged, and ask. On yes, run `configure.py notice --accept`. On no, stop: nothing may be collected.
3. **Checkpoint 1: confirm sources.** Look for connectors whose tools search GitHub pull requests, GitLab merge requests or Jira issues. With the engineer, confirm the time range, each system's username, and connector, export or skip for each source. Also confirm local repositories with the git author emails, the review folder, and the resume file. Record each answer with `configure.py`. A source with no connector needs an export path or a skip.
4. `stage.py begin 01-raw`. If `01-raw.tmp/` already holds a `.partial.jsonl`, a paused fetch is waiting: do not run `begin`, continue it instead.
5. Fetch each connector source as `references/sources.md` describes, one page per line, with the query. If a connector fails partway, rename the file to `<source>.partial.jsonl` (the last page keeps its `cursor`) and offer three choices. **Retry:** continue from the cursor, then rename the file back. **Continue without the source:** delete the file and run `configure.py source <s> --mode skip`. **Pause:** leave `01-raw.tmp/` as it is.
6. Run `ingest_export.py` for each export source, `ingest_git_log.py` if there are repositories, and `ingest_reviews.py` if there is a review folder. Show review dates that came from a modification date, and suggest renaming a file whose date is wrong.
7. Run `normalize_<source>.py` for each connector and export source. On exit 3, or from `ingest_git_log.py`, show the queries or identities searched and ask for another username or email. Never guess one.
8. Run `link.py`. Show the bad rows (the first 10 per source), filtered and duplicate counts, and warnings. Report the items per source and kind, and the time range covered.

## Changes to resume-core, fixtures and the architecture spec

1. `rcore/documents.py`: the document reader moves here from `rimport/extract.py` unchanged. `rimport/extract.py` keeps the JSON Resume format entry and re-exports the rest, so resume-import is unchanged. rcore stays importable with the standard library alone. Only reading a PDF or DOCX needs the pinned dependencies.
2. `config.schema.json`: optional `git_authors`, an array of non-empty strings. `default_config()` includes it as `[]`. It is optional so that existing workspaces stay valid.
3. Fixture: `01-raw/github.jsonl` (connector pages), `01-raw/jira.jsonl` and `exports/jira.csv` (a Jira CSV export and its ingested form), `01-raw/reviews.jsonl` and `reviews/2025-H1.txt`. `02-evidence/evidence.jsonl` is exactly `link.py`'s output for them: the same IDs, now in `created_at` order and with the new `raw_ref` form. The config gains `"git_authors": []`.
4. The architecture spec: the resume-collect section points here, and the plugin layout lists the collect scripts. The Evidence contract gains the raw line format, `raw_ref`, `native_key` per source, directed links and duplicates. The workspace section lists `git_authors`.
5. Core `SKILL.md` lists `rcore.documents` among the helpers. The test command, CI and `pytest.ini` add `skills/resume-collect/scripts`.

## Error handling

| Case | Behavior |
|---|---|
| Notice not accepted | Every ingest, normalize and link script exits 1. The skill shows the notice. |
| No connector for a source | The skill asks for an export path or a skip, and records it with `configure.py`. |
| Connector fails partway | Pages stay in `01-raw.tmp/<source>.partial.jsonl` with the cursor. Retry, continue without the source, or pause. `link.py` refuses to run while a partial file exists. |
| Username yields no results | Exit 3 with the queries and the authors seen. The engineer names another username or email. Nothing is guessed. |
| Malformed rows | The first 10 per source are reported with file and line. The rest are processed, and the count is stored as `skipped_rows` in `02-evidence/_stage.json`. |
| Export file unreadable | Exit 1 naming the file. Nothing written. |
| Folder not a git repository | Exit 1. Nothing written. |
| Review file without text | Reported and skipped. The rest are read. The engineer can supply a DOCX or TXT copy. |
| Raw data and configuration disagree | `link.py` exits 1 listing each mismatch with its fix. Nothing committed. |

## Testing

- **Common:** every timestamp form, including offsets, fractions, Jira CSV dates and rejected forms; excerpts (HTML comments, whitespace, the 500-character cut); the time-range rule, including open items; raw lines that are not JSON or not pages.
- **Each normalizer:** REST, GraphQL and CLI shapes; role by author, embedded reviews and the `reviewed-by:`/`reviewer_username=` query; assignee and reporter; filtered items; bad rows with line numbers; ADF descriptions; CSV repeated headers and numeric parents.
- **References and duplicates:** each reference form, case-insensitive matching, references to items that are not evidence, a pull request both authored and reviewed, squash commits by hash and by `(#n)`, a commit whose pull request is not the engineer's, and an ID collision (by monkeypatching the digest).
- **Ingest:** CSV, JSON and JSONL exports, including bad JSONL lines and repeated headers; git log against a repository built in the test with two authors, a merge commit, a rename, a binary file and dates on both sides of the range; the zero-match report; reviews in TXT and Markdown, a file with too little text, an unsupported file and dates from the name or modification time; DOCX (needs the dependencies, and fails rather than skips in CI).
- **CLIs:** `configure.py` for every subcommand and rejection; the notice guard on every script; `link.py` on each configuration mismatch; `link.py` commits both stages and records `extra`; `normalize_*.py` exit 3.
- **Fixture end to end:** from `exports/jira.csv`, `reviews/2025-H1.txt` and the saved GitHub pages, `ingest_export.py`, `ingest_reviews.py` and `link.py` reproduce `02-evidence/evidence.jsonl` exactly. The evidence still validates, and the fixture's bullets still resolve against it.

## Out of scope for v1

- Incremental collection: every run fetches the whole time range. IDs are stable, so it can be added later.
- Comments and discussion threads beyond titles and bodies, and review comments' text.
- Other sources (Bitbucket, Linear, Asana, Azure DevOps) and connectors that return other shapes. Save them as a supported export instead.
- OCR of scanned reviews, and non-English month names in Jira CSV dates.
