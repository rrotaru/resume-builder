# resume-ats: Design

- **Date:** 2026-09-27
- **Status:** Approved
- **Scope:** The `resume-ats` skill: the general resume and the per-job versions in `08-ats/`, the draft each starts from, keyword coverage, the claim diff that writes `flags.json`, the lint and length rule, `report.json`, and the commit that checks every version. Also the resume-core changes ats needs. Follow-up spec 8 of the [architecture spec](2026-09-24-resume-builder-architecture-design.md).

## Goal

Turn the sanitized bullets into the resumes render prints. The general resume selects, orders and rewords the bullets within what their sources say, fits one or two pages, and uses the target role's keywords. Each job version (`--jd <file>`) may rewrite freely against a posting, and a script flags every claim the rewrite adds that its sources do not state, for the engineer to accept, revert or edit at checkpoint 4. Scripts copy every fact from the profile, put every bullet in its place, and check the result as render will. The model chooses and words the bullets.

## Gaps

The architecture spec and the roadmap leave these open:

1. **Script and model.** Three scripts are named (`ats_lint.py`, `keywords.py`, `diff_claims.py`), but nothing says who writes `resume.json`, where a draft lives, or who commits `08-ats`, which holds several versions in one stage.
2. **Fact fields by hand.** Every name, title and date must be copied exactly from the effective profile. A model retyping them makes mistakes the source check then rejects.
3. **Placement.** A bullet must go under the entry its `work_ref` or profile-project pointer names. Nothing checks a tailored resume's `x-highlights` against it.
4. **"Wording changes must stay supported by the cited sources"** has no check for the general resume.
5. **The claim diff has no rules.** What counts as a skill, technology, number or scope, what a rewrite is compared with, and how a sanitized bullet compares with sources that still hold the confidential names.
6. **Keywords.** Nothing lists a version's keywords, says how a keyword matches a text, or what counts as evidence for a missing one.
7. **Length.** Pages are known only after render, and "about 8 years of experience" is not defined.
8. **`report.json`** has no schema and no defined contents.
9. **Several versions in one stage.** Rebuilding one job keeps the others, which were built from earlier inputs.
10. **Lint.** No list of rules, and the template rules ("no tables or columns") belong to render, which ats cannot read.
11. **Stage inputs.** A term decision must make `08-ats` stale. An attestation at checkpoint 4 must not.
12. **Checkpoint 4** reverts or edits flagged job bullets, which means changing `08-ats`, and only resume-ats may write it.

## Decisions

| Topic | Decision |
|---|---|
| Script and model | `ats.py` drafts one version at a time into `08-ats.tmp/` and prints what it holds. The model writes each version's `keywords.json` and edits its `resume.json`. `ats.py --commit` checks every version in the draft, writes `report.json` and `flags.json`, and commits `08-ats`. `ats_lint.py`, `keywords.py` and `diff_claims.py` run the same checks on the draft while the model works (gap 1). |
| Drafts | `ats.py` writes a full `resume.json`: every fact copied from the effective profile and every placed bullet from `07-sanitized/bullets.json` in its place. The model leaves out, orders and rewords; it never types a fact (gaps 2 and 3). |
| Placement | A bullet stays in the entry that copies its place: `work_ref` `i` under the entry matching the profile's `work[i]`, a profile-project pointer under the entry matching `projects[i]`. `x-highlights` keep the bullet's ID and sources. A bullet with no place is left out and reported (gap 3). |
| Claim diff | One rule for both kinds of version: a rewrite may use only technical terms, keywords, numbers and scope words that its original bullet, its sources (with denied terms replaced) or its entry state. A job version records every result in `flags.json`. The general resume must have none (gaps 4 and 5). |
| Keywords | The model lists each version's keywords in `keywords.json`: the target role's for the general resume, the posting's (each found in `jd.txt`) for a job. A script reports each as covered, missing with evidence, or missing without evidence, by one matching rule (gap 6). |
| Length | Experience is the union of the profile's job dates. Under 96 months, 1 page, else 2. An estimate in lines, calibrated against render's template, must fit 50 lines per page (gap 7). |
| Report | `report.json` holds the length, keyword coverage, the bullets left out and the lint warnings, with a schema (gap 8). |
| One stage | Each draft starts as a copy of the committed `08-ats/` and redrafts only the named version, and every commit re-checks every version against the current inputs (gap 9). |
| Lint | Rules on what ats controls: bullet characters and shape, duplicates, name and contact, dates and their order, length. Headings, date formats on the page and the one-column template are render's, guaranteed by its fixed model and tested there (gap 10). |
| Inputs | `08-ats` records the sanitized bullets and profile, the imported profile, the wizard's answers, the term decisions, the metrics, projects, evidence, `01-raw` and `config.json`. Never `decisions/attestations.json` (gap 11). |
| Revising | `ats.py --revise <version>` begins a draft without redrafting, prints each bullet beside its original, and `--commit` re-runs the claim diff. Checkpoint 4 reverts or edits through it and records attestations itself (gap 12). |

## Skill layout

```
skills/resume-ats/
  SKILL.md
  scripts/
    ats.py                 # CLI: draft a version into 08-ats.tmp/, revise or remove one; --commit checks every version and commits
    ats_lint.py            # CLI: lint and length of draft versions
    keywords.py            # CLI: keyword coverage of draft versions
    diff_claims.py         # CLI: the claim diff of draft versions; writes a job's flags.json
    rats/
      common.py            # errors, workspace files, versions and slugs, reading and validating inputs
      material.py          # bullets, places, citations, profile entries and the texts ats matches against
      draft.py             # the draft resume: facts from the profile, bullets in their places
      match.py             # how a keyword or term is found in a text
      claims.py            # the claim diff
      coverage.py          # keyword coverage
      lint.py              # lint rules, experience and the length estimate
      check.py             # the commit's checks: files, keywords.json, bullets and places
      report.py            # what the scripts print; report.json
skills/resume-core/scripts/rcore/
  citations.py             # new: what a source reference says (moved from resume-write)
  places.py                # new: a bullet's place (moved from resume-write)
```

Every script uses only the standard library and imports `rcore` as portability rule 6 allows.

## Command line

```
uv run scripts/ats.py --workspace WS                          # draft the general resume
uv run scripts/ats.py --workspace WS --jd FILE [--job SLUG]   # draft a job version from a posting
uv run scripts/ats.py --workspace WS --job SLUG               # redraft a job version from its saved posting
uv run scripts/ats.py --workspace WS --revise VERSION         # revise a version without redrafting it
uv run scripts/ats.py --workspace WS --remove SLUG            # drop a job version
uv run scripts/ats.py --workspace WS --commit                 # check every version and commit 08-ats
uv run scripts/ats_lint.py --workspace WS [VERSION ...]
uv run scripts/keywords.py --workspace WS [VERSION ...]
uv run scripts/diff_claims.py --workspace WS [VERSION ...]
```

A version is `general` or a job slug. A slug matches `^[a-z0-9][a-z0-9-]*$` and is not `general`, which render reserves for the general resume. Without `--job`, the slug comes from the posting's file name: `Fintech SRE.txt` gives `fintech-sre` (lower case, each run of other characters as `-`, no `-` at either end). `--jd` is resolved against the workspace, like the paths in `config.json`, so pass an absolute path. The posting must be UTF-8 text; the model saves a PDF or web page as text first.

| Script | Exit | Meaning |
|---|---|---|
| `ats.py` | 0 | Drafted, revised or removed in `08-ats.tmp/`; with `--commit`, every version checked and `08-ats` committed |
| | 1 | Error: `07-sanitized/bullets.json` or `decisions/terms.json` missing, an invalid input, a bad slug or posting, no such version, a problem in the draft, no `08-ats.tmp/` for `--commit`, or a failed commit. Nothing committed. |
| `ats_lint.py` | 0 / 1 | No lint errors / a lint error, or no draft |
| `keywords.py` | 0 / 1 | Coverage printed / `keywords.json` missing or invalid, or no draft |
| `diff_claims.py` | 0 / 1 | Diffed (a job's flags are allowed) / a claim in the general resume, or no draft |
| All | 2 | Usage error |

The three checkers read the draft in `08-ats.tmp/`, every version in it by default. The committed results are each version's `report.json` and `flags.json`.

## Pipeline

1. `ats.py` reads and validates its [inputs](#inputs). A missing `07-sanitized/bullets.json` names `/resume-builder:sanitize`, and an invalid input the command that fixes it. It warns when `06-bullets` or `07-sanitized` is stale.
2. If `08-ats.tmp/` exists, a draft is in progress and `ats.py` works in it. Otherwise it begins one as a copy of the committed `08-ats/` (`stages.begin(..., from_current=True)`), or empty when there is none. So versions it does not name are kept.
3. It [drafts](#drafts) the named version (replacing its folder in the draft), revises or removes one, and prints the [material](#what-atspy-prints).
4. The model writes the version's `keywords.json`, runs `keywords.py`, and edits `resume.json`, checking with `ats_lint.py` and `diff_claims.py` as it goes.
5. `ats.py --commit` runs the [checks](#commit) on every version in the draft. On any problem it prints each with a `fix:` line and exits 1; the draft stays. Otherwise it writes each version's `report.json`, each job's `flags.json` and the normalized `resume.json`, and commits `08-ats`.

Commit each version before drafting the next, or draft several and commit once: every commit checks the whole draft. To start over, `stage.py begin 08-ats --from-current` replaces the draft with a copy of the committed stage.

## Drafts

`ats.py` builds `resume.json` for the version from the effective profile (`rcore.profile.effective_profile`) and `07-sanitized/bullets.json`. It never reads `06-bullets/`.

**Facts.** For each field `tailored-resume.schema.json` allows, the draft copies the effective profile's value exactly, and leaves out a value that does not fit the schema (the commit's fact check then names it):

- `basics`: `name`, `email`, `phone`, `url`; `location` `city`, `region` and `countryCode` (not the street address or postal code, which render never shows); each `profiles` item's `network`, `username` and `url`. `label` is `config.json` `target_role`, as it spells it, when set, else the profile's `label`.
- One entry per entry of the effective profile's `work`, `projects`, `education`, `certificates` and `skills`, in profile order, with the fields the schema allows (`description`, `summary`, `roles` and `x-lines` never). Dates are copied as they are; render formats them.
- `skills` keywords holding a denied term are left out, each with a `note:`. A keyword cannot be replaced, since keywords combine in the overlay. With every keyword gone, the entry keeps its name, or is left out when it has none.
- `basics.summary` is the sanitized profile's summary (`07-sanitized/profile.json`, whitespace runs as one space), citing `resume:/basics/summary`, when the imported profile has one.
- Entries are written with keys in schema order, and sections with no entries are left out. No entry has `x-sources`.
- Any other fact holding a denied term (a codename as a project name) is copied as it is, with a `warning:`: the terms check refuses it at the commit until the wizard records a replacement value at that path.

**Bullets.** Each bullet goes under the entry for its place (`rcore.places.place`, as resume-write defines it), in `07-sanitized/bullets.json` order, as `{"bullet_id", "text", "sources"}` with the bullet's ID, text and sources, and `highlights` holds the same texts:

| Bullet | Goes under |
|---|---|
| `work_ref` `i` | the entry copied from the profile's `work[i]` |
| `work_ref` null, a `resume:` or `wizard:` pointer into `/projects/<i>` | the entry copied from `projects[i]` |
| `work_ref` null, no such pointer | nowhere: left out, with a `warning:` |
| a place past the end of the profile's `work` or `projects` | nowhere: left out, with a `warning:` that `07-sanitized` is out of date |

When a version is redrafted, its `report.json` and `flags.json` are removed from the draft, since the commit writes them. A job keeps its `jd.txt`, and every version keeps its `keywords.json`, unless `--jd` starts the job over from a new posting.

## Placement

The commit checks each `x-highlights` item of each `work` and `projects` entry:

- `bullet_id` is a bullet of `07-sanitized/bullets.json`, used once in the resume.
- `sources` are the bullet's sources, the same set. A rewrite changes wording, never what the bullet rests on.
- The bullet's place is in the same section, and the entry copies the profile entry at that index: every fact it has matches that entry (`rcore.facts.matches`, the fact check's rule for one entry).
- A bullet with no place is not in the resume.

```
08-ats.tmp/general/resume.json: /work/1/x-highlights/0: b_1 goes under /work/0 (Senior Software Engineer, Northwind Payments); this entry copies /work/1
08-ats.tmp/general/resume.json: /projects/0/x-highlights/1: b_7 has no place (its project falls in no job of the profile); leave it out
08-ats.tmp/general/resume.json: /work/0/x-highlights/2: sources must be b_2's sources ["ev_cbf558fa"]
```

The model may leave out any bullet or entry, and reorder entries and bullets. Two entries that copy the same profile entry are a lint error.

## Keywords

The model writes each version's `keywords.json`, a JSON list of strings (`ats-keywords.schema.json`):

- **General:** the keywords an ATS would match for `config.json` `target_role`: skills, technologies and practices, spelled as postings spell them. Required unless the target role is empty.
- **Job:** the posting's keywords, as it spells them. Each must be found in `jd.txt`, and there is at least one.

Each keyword is listed once. A keyword holding a denied term is allowed in this list (it is not rendered), but never on the resume.

### Matching

One rule finds a keyword in a text, for coverage and for the claim diff:

- Both are NFKC-normalized and format characters (category `Cf`) are removed.
- The keyword is split into words at runs of whitespace, `_`, dashes, `/`, `.` and `·`. In the text the words may be joined by any run of those, or by nothing: `Node.js` matches `NodeJS`, `CI/CD` matches `CI CD`.
- It matches whole words: no letter or digit before it, and no letter, digit, `+` or `#` after it, so `C` is not found in `C++` or `C#`, and `Go` is found in `Go-based`.
- A keyword ending in a letter also matches with `s` or `es` added (`API`, `APIs`).
- Case is ignored, except in a keyword of at most three letters and digits that holds a capital letter (`Go`, `AWS`, `SLO`, `US`), which must match its case, so `Go` is not found in `go live`.

### Coverage

`keywords.py` (and the commit, for `report.json`) gives each keyword a status:

| Status | Found in | `where` |
|---|---|---|
| `covered` | the resume's visible text: `basics.label` and `summary`; each entry's `name`, `position`, `location` and bullet texts; `education` `studyType`, `area` and `institution`; `certificates` `name` and `issuer`; `skills` `name` and `keywords` | the resume pointers, in resume order (`/work/0/x-highlights/0/text`, `/skills/0/keywords/0`) |
| `missing_with_evidence` | what the resume could draw on: every sanitized bullet, the title, excerpt and full review text of evidence in a project and of performance reviews, the metrics, and every string of the imported profile and the wizard's answers | bullet IDs, evidence IDs, `metric:` IDs, then `resume:` and `wizard:` pointers |
| `missing_without_evidence` | neither | `[]` |

A keyword missing with evidence can reach the resume two ways. A bullet whose sources hold it can be reworded to use it. Or, if the engineer agrees, the wizard adds it to the skills (`answer.py add /skills/<i>/keywords KEYWORD`), the only way a keyword enters `skills`: the fact check rejects any keyword the effective profile does not list. That answer makes `06-bullets` stale, so write and sanitize apply are recommitted (`write.py --from-current`, then `--commit`, then `apply.py` and `apply.py --commit`) before ats drafts again.

```
keywords for fintech-sre: 5 covered, 1 missing with evidence, 2 missing without evidence
  covered  Go  /work/0/x-highlights/0/text, /work/1/x-highlights/0/text, /skills/0/keywords/0
  covered  Redis  /work/0/x-highlights/0/text, /skills/0/keywords/2
  covered  PostgreSQL  /skills/0/keywords/3
  covered  SLO compliance  /work/0/x-highlights/0/text
  covered  on-call  /work/0/x-highlights/1/text
  missing with evidence  metrics  ev_56410ed1
  missing without evidence  Kubernetes
  missing without evidence  incident response
```

At most three places are printed per keyword (`and 4 more`); `report.json` lists them all.

## Claim diff

The claim diff compares each bullet text in a version, and its `basics.summary`, with what it may rest on. For an `x-highlights` item that is the **known texts**:

- the bullet's text in `07-sanitized/bullets.json` (the original);
- the text of each of its sources (`rcore.citations`: an evidence item's title and excerpt and a review's full text in `01-raw/`, a metric's value and statement, a pointer's value);
- each of those source texts with the denied terms replaced, as sanitize apply would, so `a top-10 US bank` is known wherever the evidence says `Contoso Bank`;
- the `name`, `position` and `location` of the entry it sits under, so a bullet may name its employer.

For the summary it is the texts of `x-summary-sources`, with denied terms replaced. The project a bullet belongs to also counts for scope words (below).

A text is flagged for each of these not in its known texts, in the order they appear, each once:

| Claim | What is compared | Reason |
|---|---|---|
| A keyword | each keyword of the version's `keywords.json` found in the text | `introduces 'SLO compliance', which no cited source mentions` |
| A technical term | each word that has a capital letter after its first character (`PostgreSQL`, `gRPC`, `SLO`); mixes letters and digits, other than a number with a unit (`EC2`, `k8s`, `p99`, but not `40ms` or `2M`); holds `+`, `#`, `_` or an inner `.` (`C++`, `Node.js`); or starts with a capital letter and does not start the text or a sentence, which ends at `.`, `!` or `?` (`Kafka` in `built on Kafka`). Hyphens split words: `Redis-backed` is `Redis` and `backed` | `introduces 'Kafka', which no cited source mentions` |
| A number | `rcore.numbers.unsupported`: each number written with digits | `states the number '12', which no cited source states` |
| A scope word | the words in the table below | `claims 'company-wide', which neither its sources nor its project's role and scope support` |

A term inside a flagged keyword, and a number inside a flagged term, is not reported again. Terms and keywords are found with the [matching](#matching) rule. A text equal to its original has nothing to flag, since the original is known.

| Scope | Words | Also supported by the project's |
|---|---|---|
| leadership | led, lead, leading, spearheaded, headed, directed | role `lead` |
| cross-team | cross-team, cross-functional, multi-team | scope `cross-team`, `org` or `company` |
| organization | org-wide, organization-wide, organisation-wide, department-wide, division-wide | scope `org` or `company` |
| company | company-wide, companywide, enterprise-wide, global, globally, worldwide | scope `company` |

A scope word is supported when any word of its group is in the known texts, or the bullet's project supports it.

**Job versions.** `flags.json` records every examined text: `checked` maps each `bullet_id`, and `summary` for `basics.summary`, to the sha256 of its text, and `flags` lists each flagged text, summary first, then in resume order, with its reasons. `diff_claims.py` writes it into the draft, and the commit writes it again for every job, so a committed `flags.json` always matches its resume. `check_flags.py` then passes a flagged bullet only once the engineer attests it at checkpoint 4, and an attestation for an unchanged text survives a redraft.

**The general resume** may have no flag: rewording is "evidence-bound". `diff_claims.py general` prints each claim and exits 1, and the commit refuses them:

```
08-ats.tmp/general/resume.json: /work/0/x-highlights/0 (b_1): introduces 'SLO', which no cited source mentions
  fix: in the general resume, reword only within what each bullet's sources say, or use the bullet's own text; a job version may go further, and its claims are flagged for checkpoint 4
```

For the fixture, the job's `b_1` rewrite, `…idempotency cache in Go, raising checkout SLO compliance`, is flagged `introduces 'SLO compliance', which no cited source mentions`, the reason the fixture's `flags.json` and attestation carry. `SLO` is inside the keyword, so it is not reported on its own.

## Lint and length

`ats_lint.py` (and the commit) checks each version. Errors stop the commit; warnings go to `report.json`.

| Rule | Kind |
|---|---|
| `basics.name` is missing or empty (render requires it) | error |
| A bullet or the summary holds a line break or tab, or begins or ends with a space | error |
| A bullet begins with a bullet or dash character (`•`, `-`, `–`, `*`, `▪` and the like): render adds its own | error |
| A bullet or the summary holds a character ATS parsers garble: a control or private-use character, an unassigned or surrogate code point, or an emoji or pictograph (U+2600 to U+27BF, U+2B00 to U+2BFF, U+1F000 to U+1FAFF, U+FE0F) | error |
| A `bullet_id` appears twice | error |
| Two entries copy the same profile entry | error |
| The estimate is over the line budget | error |
| No email and no phone | warning |
| Jobs are not most recent first (by end, then start; an ongoing job is most recent) | warning |
| A job of the profile is left out | warning |
| A job has no `startDate` | warning |
| A bullet is longer than 200 characters | warning |
| A project entry has no bullets | warning |
| No skill keywords | warning |

**Experience** is the union of the effective profile's `work` date ranges in whole months, counting the first and last: a year alone runs from January to December, a job without `endDate` runs to the current month, no job counts past the current month, and a job without `startDate` is not counted. Under 96 months (8 years) the budget is 1 page, otherwise 2.

**The estimate** counts lines of the template's body text (10.5 pt at 1.3 line height), following render's classic template, and is rounded up:

| Part | Lines |
|---|---|
| Name | 1.6 |
| Label | 1.3 |
| Contact line: email, phone, url, each profile (url, or `network: username`), and `city, region, countryCode`, joined by ` · ` | 1.3 per 100 characters, rounded up |
| Section heading, for each section with entries (Summary counts as one) | 2.4 |
| Summary | 1 per 100 characters, rounded up |
| Entry title (`position, name` for jobs, `name, position` for projects, `studyType, area, institution`, `name, issuer`) | 1 per 90 characters, rounded up |
| Entry date or detail line (dates, a job's location, a project's or certificate's url, a score) | 1 |
| An entry's bullets | 0.15, and for each bullet 0.15 plus 1 per 95 characters, rounded up |
| Space after each entry | 0.45 |
| Skills line (`name: keyword, keyword`) | 0.15 plus 1 per 100 characters, rounded up |

One page is 50 lines. Measured in Chromium against render's template at A4 width, the narrower paper, the estimate was 4 to 15% above the real height, and every resume estimated at 52 lines or fewer printed on one Letter page, which holds about 51.7. A test renders generated resumes to keep this true. Render reports the real page count and warns above two pages.

```
08-ats.tmp/general/resume.json: estimated 57 lines, over the 1-page budget of 50 lines (88 months of experience); leave out the weakest bullets or entries
```

## `report.json`

The commit writes each version's `report.json` (`ats-report.schema.json`). For the fixture's general resume, abridged:

```json
{
  "length": {"experience_months": 88, "pages": 1, "estimated_lines": 36, "line_budget": 50},
  "keywords": [
    {"keyword": "Go", "status": "covered",
     "where": ["/work/0/x-highlights/0/text", "/work/1/x-highlights/0/text", "/skills/0/keywords/0"]},
    {"keyword": "metrics", "status": "missing_with_evidence", "where": ["ev_56410ed1"]},
    {"keyword": "Kubernetes", "status": "missing_without_evidence", "where": []}
  ],
  "left_out": [],
  "warnings": []
}
```

`left_out` lists every bullet of `07-sanitized/bullets.json` not in the version, in file order, with the reason `no place` or `not selected`. Checkpoint 4 shows the engineer the report of each version.

## Commit

`ats.py --commit` stops, printing every problem with a `fix:` line per kind, when:

- there is no `08-ats.tmp/`, or it holds no version;
- the draft holds a file ats does not write: `08-ats.tmp/` holds only `general/` and `jobs/<slug>/`; `general/` only `resume.json`, `keywords.json` and `report.json`; a job only `jd.txt`, `resume.json`, `keywords.json`, `report.json` and `flags.json`;
- a job's slug is not valid, or its `jd.txt` is missing, empty or not UTF-8;
- `keywords.json` is missing, invalid, lists a keyword twice, is empty (a job, or the general resume with a target role), or a job's keyword is not found in its posting;
- `resume.json` does not match `tailored-resume.schema.json` (the later checks then skip that version);
- the source check fails: `rcore.sources.check_file`, which is `check_sources.py` with its fact fields and `basics.label` rule, run on the written file, as render will;
- the terms check fails: `rcore.terms.check_file`, which is `check_terms.py`;
- a [placement](#placement) rule fails;
- the general resume has a [claim](#claim-diff);
- a [lint](#lint-and-length) error.

Before the checks, the commit rewrites each `resume.json` with keys in schema order and `highlights` set to the `x-highlights` texts, so the model edits only `x-highlights`. Then it writes `report.json` and `flags.json` and commits `08-ats` with its [inputs](#inputs) and `extra` `{"versions": ["general", "fintech-sre"], "flagged": {"fintech-sre": 1}}`. Every version is checked against the current inputs, kept ones included, so the recorded inputs hold for the whole stage.

## Inputs

`ats.py` reads, and the commit records, each of these that exists: `07-sanitized/bullets.json` (required), `07-sanitized/profile.json` (the summary), `03-profile/profile.json` and `decisions/profile.json` (facts and places), `decisions/terms.json` (required: denied keywords, the terms check, replaced source texts), `decisions/metrics.json`, `04-projects/projects.json`, `02-evidence/evidence.jsonl` and `01-raw` (source texts and evidence for keywords), and `config.json` (the target role). A term decision therefore makes `08-ats` stale, directly and through `07-sanitized`. `decisions/attestations.json` is never an input: ats does not read it, and attesting at checkpoint 4 leaves `08-ats` fresh.

## What ats.py prints

Drafting the fixture's general resume, with the fixture's `08-ats/` committed:

```
ats: drafted general in 08-ats.tmp/general/ (a copy of the committed 08-ats/ with general, fintech-sre)
target role: Senior Backend Engineer
experience: 88 months: 1 page, 50 lines
places:
  /work/0  Senior Software Engineer, Northwind Payments  2023-01 to present
    b_1  pj_da2a2b53  xyz_quantified  Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency cache for real-time fraud-detection platform in Go
    b_2  xyz  Mentored two new engineers through on-call onboarding
  /work/1  Software Engineer, Tailspin Toys  2019-06 to 2022-12
    b_3  xyz  Migrated the order service from PHP to Go, serving 2M requests per day
  /projects/0  ledger-lint  2021-04 to present
    b_4  xyz  Built ledger-lint, an open-source linter for double-entry ledger files with 300 GitHub stars
08-ats.tmp/general/resume.json: every fact from the profile and 4 bullets in their places, estimated 36 of 50 lines
kept 08-ats.tmp/general/keywords.json from before; check it still fits
next: write 08-ats.tmp/general/keywords.json (the target role's keywords), run keywords.py general, then select, order and reword the bullets in resume.json and run ats.py --commit
```

`warning:` lines come first: `06-bullets` or `07-sanitized` is stale, a bullet has no place (`warning: b_7 (pj_… 'Ledger export') has no place: no job of the profile overlaps its project; it is left out until the job is added with /resume-builder:wizard`), a place past the end of the profile, a fact holding a denied term (`warning: /projects/0/name 'Falcon' holds the denied term 'Falcon'; facts are copied exactly, so the commit refuses it until the engineer sets a replacement value with /resume-builder:wizard`). Then a `note:` for each keyword left out (`note: /skills/0/keywords/3 'Falcon SDK' holds the denied term 'Falcon'; a keyword cannot be replaced, so it is left out`). A job version also prints its posting's path and first line, and `--revise` prints each bullet with its original text when it differs (`was: …`) and, for a job, its current flags.

With `--commit`, after the checks pass, it prints the warnings of each version (`warning: general: …`) and any review whose full text cannot be read, then:

```
general: 4 of 4 bullets, 36 of 50 lines; keywords: 4 covered, 1 missing with evidence, 1 missing without evidence
fintech-sre: 4 of 4 bullets, 36 of 50 lines; keywords: 5 covered, 1 missing with evidence, 2 missing without evidence; 1 flagged
  b_1  introduces 'SLO compliance', which no cited source mentions
committed 08-ats: general, fintech-sre (1 flagged)
```

## `08-ats/` contents

| File | Written by | Schema |
|---|---|---|
| `general/resume.json`, `jobs/<slug>/resume.json` | `ats.py` drafts it, the model edits it, the commit normalizes it | `tailored-resume.schema.json` |
| `general/keywords.json`, `jobs/<slug>/keywords.json` | the model | `ats-keywords.schema.json` |
| `general/report.json`, `jobs/<slug>/report.json` | the commit | `ats-report.schema.json` |
| `jobs/<slug>/jd.txt` | `ats.py --jd`, the posting's text | none (text) |
| `jobs/<slug>/flags.json` | `diff_claims.py` and the commit | `flags.schema.json` |
| `_stage.json` | the commit through `rcore.stages` | `stage.schema.json` |

## SKILL.md

1. Run `stage.py status`. If `07-sanitized` is missing, stop and suggest `/resume-builder:write` then `/resume-builder:sanitize`. If it or an earlier stage is stale, tell the engineer and offer to rebuild first. If `08-ats.tmp/` exists, a draft is in progress: continue it, or start over with `stage.py begin 08-ats --from-current`.
2. Draft the general resume with `ats.py`. Report its `warning:` and `note:` lines.
3. Write `general/keywords.json` for the target role and run `keywords.py general`. For each keyword missing with evidence, ask the engineer whether it belongs in their skills; record a yes with the wizard, recommit write and sanitize apply, and draft again.
4. Edit `general/resume.json`: leave out and order bullets (strongest first: quantified, matching keywords, recent), reword only within each bullet's sources, keep every fact as drafted (an entry may be left out, a date shortened), optionally add a summary that cites its sources. Never move a bullet, change its `bullet_id` or `sources`, or add one. Run `ats_lint.py general` and `diff_claims.py general` until both pass, then `ats.py --commit`.
5. For each posting: `ats.py --jd FILE`, read `jd.txt`, write the posting's keywords, run `keywords.py <slug>`, then tailor freely: reword to the posting's language, reorder, select. Each new claim is flagged for checkpoint 4, so prefer what the sources support. Run `diff_claims.py <slug>` to see the flags, then `ats.py --commit`.
6. To revert or edit a bullet (checkpoint 4): `ats.py --revise <version>`, change the text in the draft, `ats.py --commit`. Attestations are checkpoint 4's, never ats's.
7. Report each version: bullets used and left out, length, keyword coverage, warnings, and each job's flags. Say that the engineer accepts, reverts or edits every flag at checkpoint 4, and that render comes next.

Never edit `08-ats/` or `decisions/` by hand, and never weaken or skip a check.

## Changes to resume-core, fixtures and the architecture spec

1. New `rcore/citations.py`: `Citations(workspace, evidence, metrics, profile, wizard)` with `texts(ref)` (what a source reference says) and the warnings for reviews whose full text cannot be read. Moved from resume-write's `rwrite/material.py`, which uses it; the rules are unchanged. The claim diff and write's number check read sources the same way.
2. New `rcore/places.py`: `pointer_place(ref)` and `place(bullet)`, moved from resume-write. Write checks places and ats uses them with one rule.
3. `rcore.facts.matches(entry, candidate)`: whether a tailored entry copies one profile entry, the rule the fact check applies.
4. `rcore.numbers.spans(text)`: each number with its position in the text. `numbers()` uses it.
5. New schemas `ats-keywords.schema.json` and `ats-report.schema.json`, mapped in `FILE_SCHEMAS` for `08-ats/general/` and `08-ats/jobs/*/`.
6. Fixture: `08-ats/general/keywords.json` and `report.json`, and `08-ats/jobs/fintech-sre/jd.txt` (a made-up posting), `keywords.json` and `report.json`. The `education` and `certificates` entries of both resumes take schema key order. With the current month fixed at 2026-09, drafting the general resume, applying the fixture's edit (`b_1` loses `for real-time fraud-detection platform`) and committing, then drafting the job from its posting, applying its edit and committing, rebuilds every saved `08-ats/` file byte for byte, and render's gate passes.
7. `pytest.ini` adds `skills/resume-ats/scripts` to `pythonpath`. The test command and CI do not change: ats uses only the standard library.
8. resume-core `SKILL.md`: the new helpers, and `keywords.json`, `report.json` and `jd.txt` beside the tailored resumes.
9. The architecture spec: the plugin layout lists `ats.py`; the workspace lists `keywords.json`; "Tailored resume" describes `report.json`, `keywords.json` and the claim diff's rules; the resume-ats section points here.

## Error handling

| Case | Behavior |
|---|---|
| No sanitized bullets, or no `decisions/terms.json` | Exit 1 naming `/resume-builder:sanitize` or `init_workspace.py`. Nothing begun. |
| An invalid input | Exit 1 naming the file and the command that fixes it. Nothing begun. |
| A bad slug, `general` as a slug, an unreadable or empty posting | Exit 1. The draft is unchanged. |
| A bullet with no place | Left out of every version, with a warning, and listed in `left_out`. |
| A keyword holding a denied term | Left out of `skills`, with a note. The terms check refuses it if put back. |
| A problem in the draft | Exit 1, one line per problem and a `fix:` line. The draft stays in `08-ats.tmp/` to fix. |
| A kept version that no longer passes (its bullets changed) | The commit names it. Redraft it (`ats.py --job <slug>` or `ats.py`), or remove it (`ats.py --remove <slug>`). |
| A flagged job bullet | Committed. Render refuses it until checkpoint 4 attests, reverts or edits it. |
| Commit fails | Exit 1. The previous `08-ats/` stays. |

## Testing

- **Matching:** separators and joined words (`Node.js`, `CI/CD`), whole words (`C`, `C++`, `C#`, `Go-based`), plurals, case rules for short capitalized keywords (`Go` and `go live`, `US` and `us`), NFKC and format characters.
- **Claim diff:** each kind of technical term, and words that are not (a sentence's first word, `40ms`, `2M`); keywords and the terms inside them; numbers and numbers inside a term; each scope group, supported by a source or by the project's role or scope; denied terms replaced in source texts; the entry's employer; an unchanged text; the summary; `checked` holds every bullet and the summary; the fixture's flag.
- **Keywords:** each status and its `where`; a job keyword not in the posting; duplicates; empty lists; a keyword added with the wizard is covered after a redraft, and the fact check refuses it in `skills` before.
- **Drafts:** facts copied exactly (address left out, schema key order, no `x-sources`); the label; bullets from `07-sanitized`, not `06-bullets`; each kind of place; no place and a place past the end left out with warnings; a denied keyword left out with a note; the summary.
- **Placement:** a bullet moved to another entry or section, an unknown bullet, changed sources, a bullet twice, a bullet with no place.
- **Lint and length:** each rule; experience from overlapping, year-only, ongoing and undated jobs; the 96-month boundary; the estimate's parts; and, with Chromium, generated resumes estimated within budget print within it on Letter and A4.
- **CLIs:** exit codes; drafting general and a job, the slug from a file name, `--job` from the saved posting, `--jd` over an existing job, `--revise`, `--remove`; continuing a draft and beginning from the committed stage; `--commit` without a draft, with an unexpected file and with a broken kept version; the commit's inputs and `extra`; the checkers on the draft.
- **Must promises:** facts copied from the effective profile with no `x-sources` (and the source check passes on every committed resume); bullets read from `07-sanitized`; a keyword with a denied term left out; each bullet in its place, and one with no place left out and reported; bullet IDs as `bullet_id`; `checked` holds every examined bullet and the summary; job slugs; a missing keyword enters `skills` only through the wizard; a term decision makes `08-ats` stale and an attestation does not.
- **Fixture end to end:** the rebuild described above, byte for byte, then `validate.py`, render's gate and `check_flags.py` pass.

## Out of scope for v1

- Rendering to count pages. The estimate decides, and render reports the real count.
- Choosing another page budget than the experience rule gives.
- Reading a posting from a PDF, DOCX or URL: the model saves its text first.
- Synonyms in keyword coverage (`Postgres` for `PostgreSQL`). The engineer records a different wording with the wizard.
- Judging a rewrite's claims beyond terms, keywords, numbers and scope words, such as a stronger verb. The engineer reviews every flag and every bullet at checkpoint 4.
- Writing attestations. Checkpoint 4 (resume-build) records them.
- Cover letters.
