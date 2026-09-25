# Fetching each source

Read this in step 5 of `SKILL.md` (connectors), or when helping the engineer make an export file.

## Page lines

Write each page of results as one line of `01-raw.tmp/<source>.jsonl`:

```json
{"query": "is:pr author:jrivera updated:>=2023-01-01 created:<=2025-12-31", "items": [{...}, {...}]}
```

- `items` holds the results exactly as the connector returned them. Keep every field; do not summarize, trim or reorder.
- `query` is the search or request you ran, written out in full. The normalizers read it. A GitHub query containing `reviewed-by:<username>` or a GitLab request containing `reviewer_username=<username>` marks its results as reviews. A no-results report shows it.
- A page with no results is still a line (`"items": []`), so the file shows the search ran.
- If a fetch fails partway, the last line also gets `"cursor"`: the page number, `after` cursor or `startAt` that fetches the next page.

Use the time range from `configure.py show`. Search by **last update**, not by creation: ask for everything updated on or after `START` and created on or before `END`. An item opened before the range but merged, closed, reviewed or still worked on during it was updated during it, and the normalizer keeps every item whose life overlaps the range (see the Collect spec, "Time range"). Searching by creation date would miss those. The normalizer applies the exact range afterwards, so a wider fetch is safe. With an open end, leave that bound out of the query.

## GitHub

Connector searches (GitHub search syntax), one file for all of them:

1. Authored pull requests: `is:pr author:USERNAME updated:>=START created:<=END`
2. Reviewed pull requests: `is:pr reviewed-by:USERNAME -author:USERNAME updated:>=START created:<=END`
3. Issues: `is:issue assignee:USERNAME updated:>=START created:<=END`, then `is:issue author:USERNAME updated:>=START created:<=END`

A search returns at most 1,000 results. If the total is larger, split the `updated:` range (`updated:START..MID`, then `updated:>MID`) and search each part.

Search results have no size or merge commit. When the connector can fetch a single pull request (`GET /repos/OWNER/REPO/pulls/NUMBER`), fetch each authored one and write it as its own page with that request as the query. `link.py` merges it with the search result, which adds `additions`, `deletions`, `changed_files`, `merge_commit_sha` and the branch name.

The normalizer reads REST objects (search results or pull requests), GraphQL nodes, and `gh` CLI JSON. It uses `number`, `title`, `body`, `html_url` or `url`, `user.login` or `author.login`, the repository (`base.repo.full_name`, `repository.nameWithOwner` or `repository_url`), `state`, `created_at`, `closed_at` and `merged_at` (or their camelCase forms), `labels`, `assignees`, `reviews` or `latestReviews`, `head.ref`, and the size fields.

**Export without a connector.** With the GitHub CLI (`gh`) signed in, the engineer (or you, if you can run commands) can write an export file:

```
gh search prs --author USERNAME --updated ">=START" --created "<=END" --limit 1000 \
  --json number,title,body,url,author,createdAt,closedAt,state,labels,repository > authored.json
gh search prs --reviewed-by USERNAME --updated ">=START" --created "<=END" --limit 1000 \
  --json number,title,body,url,author,createdAt,closedAt,state,labels,repository > reviewed.json
```

Then combine them into pages that keep each query, and configure `github-export.json` as the export:

```
python3 -c 'import json; print(json.dumps([
  {"query": "author:USERNAME", "items": json.load(open("authored.json"))},
  {"query": "reviewed-by:USERNAME", "items": json.load(open("reviewed.json"))}]))' > github-export.json
```

A plain array of pull requests also works, but then only the authored ones become evidence: nothing says the others were reviewed.

## GitLab

Connector requests (REST API v4), with `scope=all`:

1. Authored merge requests: `GET /merge_requests?scope=all&author_username=USERNAME&updated_after=START&created_before=END`
2. Reviewed merge requests: `GET /merge_requests?scope=all&reviewer_username=USERNAME&updated_after=START&created_before=END`
3. Issues: `GET /issues?scope=all&assignee_username=USERNAME&updated_after=START&created_before=END`, then the same with `author_username`.

The normalizer uses `iid`, `title`, `description`, `references.full` or `web_url`, `author.username`, `reviewers`, `assignees`, `state`, `created_at`, `merged_at`, `closed_at`, `labels`, `source_branch`, `merge_commit_sha` and `squash_commit_sha`.

**Export without a connector.** With the GitLab CLI (`glab`) signed in:

```
glab api --paginate "merge_requests?scope=all&author_username=USERNAME&updated_after=START" > authored.json
```

Combine several requests into pages with their queries, as for GitHub. Keep `reviewer_username=USERNAME` in the query of the reviewed ones.

## Jira

Connector search (JQL): `(assignee = "USERNAME" OR reporter = "USERNAME") AND updated >= "START" AND created <= "END" ORDER BY created`, asking for the fields `summary`, `description`, `issuetype`, `status`, `created`, `resolutiondate`, `labels`, `assignee`, `reporter` and `parent`. Write each page of `issues` as the page's `items`. Jira Cloud identifies people by account ID or display name, so the configured username may be either. The normalizer compares it with the assignee's and reporter's `name`, `key`, `accountId`, `emailAddress` and `displayName`.

**Export without a connector.** In Jira, run the same search in the issue navigator, then use Export, "Export CSV (all fields)". Save it as UTF-8. The normalizer reads the columns `Issue key`, `Issue id`, `Summary`, `Issue Type`, `Status`, `Created`, `Resolved`, `Assignee`, `Assignee Id`, `Reporter`, `Reporter Id`, `Labels`, `Description`, `Parent` and `Custom field (Epic Link)`. Dates in Jira's default format (`10/Feb/25 9:15 AM`) or ISO format are read, in English, as UTC.

A JSON search result saved from the REST API (`{"issues": [...]}`) also works as an export.

## Local repositories and reviews

No fetching: `ingest_git_log.py` and `ingest_reviews.py` read them (`SKILL.md` step 6).
