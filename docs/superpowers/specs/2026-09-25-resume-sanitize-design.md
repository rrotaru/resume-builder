# resume-sanitize: Design

- **Date:** 2026-09-25
- **Status:** Approved
- **Scope:** The `resume-sanitize` skill: the scan that proposes sensitive terms before the wizard (`05-terms/`), and the apply step that replaces the engineer's denied terms in bullets, stories and profile prose after resume-write (`07-sanitized/`). Also the resume-core changes both halves need. This is the first half of follow-up spec 6 of the [architecture spec](2026-09-24-resume-builder-architecture-design.md). The [resume-wizard spec](2026-09-25-resume-wizard-design.md) is the second half: it turns candidates into decisions.

## Goal

Keep the engineer's confidential names off the resume. The scan finds codenames, customer names, internal URLs and financial figures in what later stages will write about, and proposes a generalization for each. The engineer decides each term in the wizard (`decisions/terms.json`). After resume-write, apply replaces every denied term in the bullets, the stories and the profile's prose, writes `07-sanitized/`, and lists any term it finds that nobody has decided yet, for checkpoint 4. The terms check at render (`check_terms.py`) is the hard gate. Sanitize exists so that gate passes on text the engineer has approved.

## Gaps

The architecture spec leaves these open:

1. **Who finds candidates, and in what.** "Finds candidate sensitive terms in projects, evidence excerpts and the profile" does not say which texts, which part is a script and which is the model, or how `found_in` is filled in.
2. **Replacing a term is not defined.** The terms check matches normalized text with separator and plural rules, so a match's position in the normalized text is not its position in the original. Nothing says what replaces a match at the start of a sentence, or how allowed terms and overlapping terms apply.
3. **Prose and facts in the profile.** Apply rewrites "the profile's prose (highlights, summary)" and leaves fact fields alone. The fields in each group are not listed.
4. **New terms have no rule.** Nothing says how a new term is detected, what `new-terms.json` must contain, or what happens to a candidate the wizard never decided.
5. **A replacement can hold a denied term.** With `Contoso` denied, a replacement `a Contoso-sized bank` for another term puts a denied term back into the text, and render fails on output apply wrote.
6. **Stage inputs.** If `05-terms` recorded `decisions/terms.json`, every term the wizard decides would make the scan stale.
7. **The halves share one skill.** Nothing says how the skill knows which half to run.

## Decisions

| Topic | Decision |
|---|---|
| What the scan reads | Each project's `internal_name`, `summary` and `rank_reasons`; the `title` and `excerpt` of evidence in a project, and of every performance review; each review's full text from `01-raw/` at its `raw_ref`; and every string in `03-profile/profile.json`. resume-write writes about exactly these (gap 1). |
| Script and model | Scripts gather the texts, print the likely terms their detectors find (codename phrases, URLs, emails, money, capitalized names), check the model's list, and compute `found_in`. The model decides which likely terms are sensitive, adds any the detectors missed, and proposes each replacement (gap 1). |
| `found_in` | The places a term appears, as IDs: `pj_…` (a project), `ev_…` (an evidence item or review), `resume:<pointer>` (the profile), and in `new-terms.json` also `b_…` (a bullet) and `stories.md:<line>`. Computed by the script with the terms check's matching rules. |
| Replacing | A script replaces each denied match with the term's replacement, exactly and repeatably. Matches are found by the terms check's rules on a normalized copy mapped back to the original text. The replacement is written as `decisions/terms.json` gives it, with its first letter capitalized at the start of a sentence or a line (gap 2). |
| Prose | In the profile, `basics.summary` and every entry's `summary`, `description`, `highlights` and `reference` are prose. Everything else is a fact, kept byte for byte, including `x-lines` (gap 3). |
| New terms | `apply.py` prints the likely terms its detectors find in the sanitized text. The model reads the sanitized bullets and stories in full and writes `new-terms.json`. The commit requires every undecided candidate that still appears to be listed (gap 4). |
| Replacement checks | Every replacement, proposed or decided, must contain no denied term and no candidate term. Apply refuses to run on a `decisions/terms.json` that breaks this, and verifies its output with the terms check (gap 5). |
| Inputs | `05-terms` records what it scanned, never `decisions/terms.json`, so deciding terms does not make it stale. `07-sanitized` records `decisions/terms.json`, so a new decision makes it stale (gap 6). |
| Two halves | `scan.py` and `apply.py`, each with `--commit` for its second step, like `match_projects.py`. The skill runs the half the request or resume-build names; otherwise apply when `06-bullets` exists, else the scan (gap 7). |
| Fact fields with denied terms | Apply leaves them and prints a `warning:` naming the path. The wizard asks for a replacement value there. |

## Skill layout

```
skills/resume-sanitize/
  SKILL.md
  scripts/
    scan.py                # CLI: begin 05-terms and print likely terms; --commit checks candidates.json and commits
    apply.py               # CLI: begin 07-sanitized and replace denied terms; --commit checks new-terms.json and commits
    rsanitize/
      common.py            # errors, workspace files, reading and validating inputs
      texts.py             # the texts each half reads, with their places; where a term occurs
      detect.py            # likely terms: codename phrases, URLs, emails, money, capitalized names
      replace.py           # replacing denied terms, capitals at a sentence start, prose in the profile
      proposals.py         # checks of candidates.json and new-terms.json, found_in
      report.py            # what the scripts print
```

Every script uses only the standard library and imports `rcore` as portability rule 6 allows.

## Command line

```
uv run scripts/scan.py --workspace WS [--commit]
uv run scripts/apply.py --workspace WS [--commit]
```

| Script | Exit | Meaning |
|---|---|---|
| `scan.py` | 0 | `05-terms.tmp/` begun and the likely terms printed; with `--commit`, candidates checked and `05-terms` committed |
| | 1 | Error: `04-projects/projects.json` or `02-evidence/evidence.jsonl` missing, an invalid input or `decisions/terms.json`, a candidate problem, no `05-terms.tmp/` for `--commit`, or a failed commit. Nothing committed. |
| `apply.py` | 0 | `07-sanitized.tmp/` begun with the sanitized files and the likely new terms printed; with `--commit`, new terms checked and `07-sanitized` committed |
| | 1 | Error: `06-bullets/bullets.json` or `06-bullets/stories.md` missing, an invalid input, an unusable `decisions/terms.json`, a denied term left after replacing, a new-terms problem, inputs changed since `apply.py` ran, or a failed commit. Nothing committed. |
| Both | 2 | Usage error |

## Scan

### Pipeline

1. `scan.py` reads and validates `04-projects/projects.json`, `02-evidence/evidence.jsonl`, `03-profile/profile.json` (when it exists) and `decisions/terms.json`. A missing projects or evidence file names the command that writes it. A missing or invalid `decisions/terms.json` is an error, as in the terms check.
2. It gathers the [texts](#texts), runs the [detectors](#likely-terms) on them, begins `05-terms` (a fresh `05-terms.tmp/`) and prints the projects and the likely terms that `decisions/terms.json` does not decide yet.
3. The model reads the printed projects and likely terms, and the evidence of each project as far as it needs, and writes `05-terms.tmp/candidates.json` (see [Candidates](#candidates)).
4. `scan.py --commit` checks the candidates, fills in `found_in`, writes the file back and commits `05-terms` with inputs `04-projects/projects.json`, `02-evidence/evidence.jsonl` and, when they exist, `01-raw` and `03-profile/profile.json`, and `extra` `{"candidates": 2}`.

`scan.py` without `--commit` always begins a fresh `05-terms.tmp/`, which discards a draft. When `05-terms.tmp/candidates.json` exists, a scan is in progress: continue it with `scan.py --commit`.

### Texts

The scan reads what resume-write will write about, in this order:

| Place | Texts |
|---|---|
| `pj_…` | Each project in `04-projects/projects.json`, in rank order: `internal_name`, `summary`, each of `rank_reasons` |
| `ev_…` | In evidence order, each item in a project's `evidence_ids`, and each performance review: `title` and `excerpt` (optional in the evidence schema, so an item without one is read by its title). For a review, also its full text: `text` of the raw record at `raw_ref`, since `excerpt` holds only 500 characters. A raw record that cannot be read gives a `warning:`, and the excerpt stands in. |
| `resume:<pointer>` | Every string in `03-profile/profile.json` |

Evidence in no project is left out: resume-write cites a project's evidence and performance reviews (roadmap piece 7), and apply's new-term check covers anything else that reaches a bullet. `decisions/profile.json` is left out too: it holds the engineer's own answers, and the wizard checks them against the denied terms. `signals.json` and `groups.json` repeat titles and names from before the engineer's renames, but nothing renders them.

### Likely terms

`rsanitize/detect.py` finds likely terms in a text. It is a hint for the model, not a decision, so it favours recall over precision:

| Kind | Found |
|---|---|
| `codename` | `Project`, `Operation`, `Codename`, `Code name`, `Program` or `Initiative` followed by one or two capitalized words: `Project Falcon` |
| `url` | `http://` and `https://` URLs (shown without the scheme and trailing punctuation), `www.` hosts, and hosts ending in `.internal`, `.corp`, `.local`, `.lan` or `.intranet` |
| `email` | Email addresses |
| `money` | A currency sign or code with a number: `$1.2M`, `€300k`, `2 million USD` |
| `name` | A run of one to four capitalized words, separated by single spaces, that does not overlap one of the above. Words of two or three capital letters (`PR`, `API`), a word followed by `-<digits>` (the `PAY` of `PAY-42`) and `I` end a run, and leading function words (`The`, `For`) are dropped. At the [start of a sentence](#sentence-start) the position may be what capitalizes the first word, so a run there also counts without it (`Fix Falcon cache` gives `Fix Falcon` and `Falcon`), and a single word there does not count. |

Names are looked for only in prose of the profile, not in its fact fields: those hold the engineer's own titles, employers and schools, which are rarely confidential and would drown the list. The other kinds are looked for everywhere.

Hits are grouped by term (the terms check's normalized words, so `Contoso Bank` and `contoso-bank` are one term), keeping the first spelling seen. The scan prints only terms `decisions/terms.json` does not decide, grouped by kind in the table's order, most places first:

For the fixture before any term is decided except the allowed `Go`:

```
scanned: 1 project, 3 evidence items in projects, 1 performance review, 03-profile/profile.json
 1. pj_da2a2b53  Project Falcon checkout latency
    Idempotency cache that cut checkout latency for Contoso Bank.
    reasons: authored the core PR and owned the epic; customer-facing latency impact
likely terms not in decisions/terms.json: 7
  codename  'Project Falcon'  3 places: pj_da2a2b53, ev_99a74656, ev_191cc8ce
  url       'github.com/jrivera'  1 place: resume:/basics/profiles/0/url
  url       'github.com/jrivera/ledger-lint'  1 place: resume:/projects/0/url
  name      'Contoso Bank'  3 places: pj_da2a2b53, ev_99a74656, ev_191cc8ce
  name      'Add Redis'  1 place: ev_191cc8ce
  name      'GitHub'  1 place: resume:/projects/0/description
  name      'Redis'  1 place: ev_191cc8ce
1 likely term decided in decisions/terms.json already
began 05-terms.tmp/: write 05-terms.tmp/candidates.json, then run scan.py --commit
```

A term is listed with at most three places, then `and N more`.

### Candidates

The model writes `05-terms.tmp/candidates.json`, a list in `term-candidates.schema.json` form without `found_in`:

```json
[{"term": "Project Falcon", "kind": "codename", "proposed_replacement": "real-time fraud-detection platform"},
 {"term": "Contoso Bank", "kind": "customer", "proposed_replacement": "a top-10 US bank"}]
```

A candidate is a name the engineer may not be allowed to publish: an internal codename, a customer or partner, an unreleased product, an internal URL or host, or a financial figure. The replacement is a true generalization that reads well in a sentence, never a guess at something more specific. [SKILL.md](#skillmd) gives the rules.

`scan.py --commit` stops with one line per problem and a `fix:` line when:

- `candidates.json` is missing, not JSON, or does not match the schema with `found_in` optional;
- a term appears in none of the texts (matched by the terms check's rules, with the allowed terms in `decisions/terms.json` exempting as they do there, except an allowed decision for the term itself);
- two candidates are the same term (the same normalized words);
- a `proposed_replacement` is empty, or contains a candidate term or a denied term.

```
05-terms.tmp/candidates.json: /2/term: 'Falcon Pay' appears in none of the scanned texts
05-terms.tmp/candidates.json: /3/term: 'contoso bank' is the same term as /1 ('Contoso Bank')
05-terms.tmp/candidates.json: /0/proposed_replacement: 'Falcon-based platform' contains the term 'Falcon' (/4)
05-terms.tmp/candidates.json: /5/proposed_replacement: 'the Tailspin client' contains the term 'Tailspin' (decisions/terms.json)
  fix: list each term once, spelled as the scanned text spells it, with a non-empty generalization that contains no candidate or denied term
```

It prints a `note:` for a candidate `decisions/terms.json` already decides: the wizard does not ask about it again. Then it writes `found_in` (places in text order, each once) and commits. The file keeps the model's order. The last lines list each candidate with its places and whether the wizard will ask about it, then `committed 05-terms: 2 candidates (0 to decide in the wizard)`.

## Apply

### Pipeline

1. `apply.py` reads and validates `06-bullets/bullets.json`, `06-bullets/stories.md`, `decisions/terms.json`, and when they exist `03-profile/profile.json`, `decisions/profile.json` and `05-terms/candidates.json`.
2. It stops if `decisions/terms.json` is unusable: missing or invalid (as in the terms check), a denied term listed twice with different replacements, or a replacement that contains a denied term (`rcore.terms.replacement_conflicts`).
3. It [replaces](#replacing) every denied match in each bullet's `text`, in `stories.md` as a whole, and in the profile's [prose](#prose-and-facts). Other bullet fields are copied unchanged.
4. It runs the terms check on the result: every bullet `text`, `stories.md`, and the profile's prose. A match left over stops it, and nothing is begun: `b_1: contains denylisted term '…' after replacing` and a `fix:` line. This can happen only for text whose pieces normalize differently from the whole, such as conjoining Hangul jamo that NFKC composes only across pieces.
5. It begins `07-sanitized` and writes `bullets.json`, `profile.json` and `stories.md`, then prints what changed, a `warning:` for each [fact field that holds a denied term](#fact-fields-with-denied-terms), the allowed-term notices, and the [likely new terms](#new-terms).
6. The model reads the sanitized bullets and stories in full and writes `07-sanitized.tmp/new-terms.json`.
7. `apply.py --commit` repeats steps 1 to 4, stops if the result differs from the files in `07-sanitized.tmp/` (`inputs changed since apply.py ran; run apply.py again and review the new text`), checks `new-terms.json`, writes it with `found_in`, and commits `07-sanitized` with inputs `06-bullets/bullets.json`, `06-bullets/stories.md`, `decisions/terms.json` and, when they exist, `03-profile/profile.json` and `05-terms/candidates.json`, and `extra` `{"bullets": 4, "changed_bullets": 1, "replacements": 4, "new_terms": 0}`.

Without `03-profile/profile.json`, `07-sanitized/profile.json` is `{}`.

### Replacing

`rcore.terms.find(text, patterns)` returns the denied matches in `text` as spans of the original string. It normalizes the text in pieces (a character with the combining marks after it), recording where each normalized character came from, and runs the terms check's patterns on the result. A match inside an allowed term's match is not returned, as in the check. Overlapping matches keep the leftmost, then the longest, so with `Contoso` and `Contoso Bank` both denied, `Contoso Bank` is replaced as one.

Each match, including a plural ending and any separators or invisible characters inside it, is replaced by the term's `replacement` as written. The first letter is capitalized at a sentence start. Nothing is ever lowercased.

#### Sentence start

A position is at the start of a sentence when either:

- the text of its line before it, ignoring spaces and the Markdown markers `#`, `>`, `-`, `+`, `*`, `•`, `_`, backticks, quotes and opening brackets, is a list number such as `1.`; or it is empty and the line has a marker (`## `, `- `), is the first line, or follows a blank line;
- or the text before it, ignoring the same characters and line breaks at its end, is empty or ends with `.`, `!`, `?` or `:`.

So `## Project Falcon checkout latency` becomes `## Real-time fraud-detection platform checkout latency`, and `- **Task:** Contoso Bank asked` becomes `- **Task:** A top-10 US bank asked`, while `for Contoso Bank` becomes `for a top-10 US bank`, also when a wrapped line breaks between `for` and the term. The same rule decides where the `name` detector treats a first word as capitalized by position.

For the fixture, `b_1` `Cut p99 checkout latency 40% for Contoso Bank by building a Redis-backed idempotency cache for Project Falcon in Go` becomes `Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency cache for real-time fraud-detection platform in Go`. Resume bullets often drop articles, so the replacement reads as the engineer's decision wrote it.

Mechanical replacement can read awkwardly, for example `the a top-10 US bank team`. The engineer sees every changed text at checkpoint 4 and fixes it by rewording the replacement in the wizard or the bullet in resume-write, never by editing `07-sanitized/`.

### Prose and facts

`rcore.profile.PROSE_FIELDS` names the prose: `basics.summary`, and `summary`, `description`, `highlights` (each string) and `reference` in every entry of every top-level section. Apply rewrites only these. Every other value in `03-profile/profile.json` is copied unchanged, key order included: names, titles, employers, dates, URLs, contact details, degrees, skills and `x-lines`. The fact-field check proves a tailored resume copied its facts from the effective profile, and a replacement written for prose ("a top-10 US bank") reads wrongly as a name ([render spec](2026-09-25-resume-render-design.md#confidential-values)).

### Fact fields with denied terms

A fact field holding a denied term is fixed by a wizard answer at that path in `decisions/profile.json`. Apply lays `decisions/profile.json` over the profile (`rcore.profile.effective_profile`) and prints a warning for each fact field a tailored resume may copy (`rcore.facts.fact_values`) that still holds a denied term:

```
warning: /projects/0/name 'Falcon' holds the denied term 'Falcon'; set a replacement value with /resume-builder:wizard
warning: /skills/0/keywords/3 'Falcon SDK' holds the denied term 'Falcon'; a keyword cannot be replaced, so resume-ats leaves it out
```

Warnings never block: the render gate fails on such a field only if a tailored resume uses it.

### New terms

`apply.py` prints, before `began 07-sanitized.tmp/`:

- each candidate from `05-terms/candidates.json` that `decisions/terms.json` does not decide and that appears in the sanitized text, marked `must list`;
- the detectors' likely terms in the sanitized bullets, stories and profile that are neither decided nor candidates.

The model then reads every sanitized bullet and the whole of `stories.md`, and writes `07-sanitized.tmp/new-terms.json` in the candidates' form, `[]` when there is nothing new. `apply.py --commit` checks it like candidates, against the sanitized text, and also stops when:

- a term is decided in `decisions/terms.json` already (`/0/term: 'Contoso Bank' is decided in decisions/terms.json; leave it out`);
- an undecided candidate from `05-terms/candidates.json` appears in the sanitized text but is not listed (`'Fabrikam' from 05-terms/candidates.json is not decided and appears in b_2; list it`).

`found_in` for new terms uses `b_…`, `stories.md:<line>` and `resume:<pointer>` (the same pointer in `07-sanitized/profile.json` and `03-profile/profile.json`). Checkpoint 4 shows the new terms. The engineer decides each in the wizard, which asks about `07-sanitized/new-terms.json` as well, and apply runs again.

### What apply.py prints

For the fixture:

```
replaced 5 matches: 'Project Falcon' 3, 'Contoso Bank' 2
06-bullets/bullets.json: 1 of 4 bullets changed
  b_1: Cut p99 checkout latency 40% for a top-10 US bank by building a Redis-backed idempotency cache for real-time fraud-detection platform in Go
06-bullets/stories.md: 3 lines changed
  3: ## Real-time fraud-detection platform checkout latency
  5: - **Situation:** Checkout for a top-10 US bank missed its p99 latency target at peak traffic.
  6: - **Task:** Jordan led the fix for the real-time fraud-detection platform checkout path.
03-profile/profile.json: 0 prose fields changed
likely new terms not in decisions/terms.json: 4
  url       'github.com/jrivera'  1 place: resume:/basics/profiles/0/url
  url       'github.com/jrivera/ledger-lint'  1 place: resume:/projects/0/url
  name      'GitHub'  2 places: b_4, resume:/projects/0/description
  name      'Redis'  2 places: b_1, stories.md:7
began 07-sanitized.tmp/: read the sanitized bullets and stories, write 07-sanitized.tmp/new-terms.json, then run apply.py --commit
```

Warnings and `notice:` lines come after the changes. An undecided candidate prints as `  must list  'Fabrikam' (a 05-terms/candidates.json candidate not yet decided)  2 places: b_2, stories.md:5`. With `--commit`, the last line is `committed 07-sanitized: 1 of 4 bullets changed, 5 replacements, 0 new terms`.

## `07-sanitized/` contents

| File | Written by | Schema |
|---|---|---|
| `bullets.json` | `apply.py` | `bullets.schema.json` |
| `profile.json` | `apply.py` | `resume.schema.json` |
| `stories.md` | `apply.py` | none (text) |
| `new-terms.json` | the model, then `apply.py --commit` adds `found_in` | `term-candidates.schema.json` |
| `_stage.json` | `apply.py --commit` through `rcore.stages` | `stage.schema.json` |

## SKILL.md

1. Choose the half: the one the request or resume-build names. Otherwise run apply when `06-bullets` exists, and the scan when it does not.
2. Run `stage.py status`.
   - **Scan:** if `04-projects` is missing, stop and suggest `/resume-builder:analyze`; if it is stale, offer to analyze again first. If `05-terms.tmp/candidates.json` exists, a scan was interrupted: go to step 4.
   - **Apply:** if `06-bullets` is missing, stop and suggest `/resume-builder:write`; if it is stale, offer to write again first. If `07-sanitized.tmp/new-terms.json` exists, go to step 7.
3. **Scan.** Run `scan.py`. Read the printed projects and likely terms, and the titles and excerpts of each project's evidence in `02-evidence/evidence.jsonl` where a name needs context.
4. Write `05-terms.tmp/candidates.json`:
   - A candidate is something the engineer's employer may not want published: an internal codename or project name, a customer or partner, an unreleased product, an internal URL, host or tool name, or a financial figure (revenue, budget, deal size). Public technology (`Redis`, `Kubernetes`), the engineer's own name and contact details, public employers and public open-source projects are not candidates.
   - Copy each term exactly as the text spells it, and list it once. Prefer the full name (`Contoso Bank`) and add a shorter form only when the text also uses it alone.
   - `kind`: `codename`, `customer`, `product`, `url`, `financial` or `other`.
   - `proposed_replacement`: a true generalization that fits where the term stood in a sentence, such as `a top-10 US bank` or `real-time fraud-detection platform`. Never name another company or product, never add a number the text does not state, and never reuse a candidate or denied term.
   - Do not write `found_in`.
5. Run `scan.py --commit`. On exit 1, fix the file as each line says and run it again. Report the candidates and say the wizard asks the engineer about each.
6. **Apply.** Run `apply.py`. On exit 1, show the lines. A replacement that contains a denied term, or a denied term that could not be replaced, is fixed in the wizard (`/resume-builder:wizard`) or by rewording the bullet (`/resume-builder:write`).
7. Read every sanitized bullet in `07-sanitized.tmp/bullets.json` and the whole of `07-sanitized.tmp/stories.md`. Write `07-sanitized.tmp/new-terms.json` as in step 4, listing every `must list` term and any other name that the engineer has not decided and that step 4 would count as a candidate. Write `[]` when there are none.
8. Run `apply.py --commit`. On exit 1, fix `new-terms.json` as each line says. If the inputs changed, start again at step 6.
9. Report the replacements, every changed bullet and story line (the engineer reviews them at checkpoint 4), every `warning:` and `notice:` line, and the new terms. New terms and warnings are resolved in the wizard, then apply runs again.

Never edit `decisions/`, `06-bullets/` or `07-sanitized/` by hand, and never weaken or skip the terms check.

## Changes to resume-core, fixtures and the architecture spec

1. `rcore/terms.py` gains:
   - `find(text, patterns)`: denied matches as `(start, end, term)` spans of the original text, allowed terms exempting, overlaps resolved leftmost-longest.
   - `terms_in(text, patterns)`: the denied terms the check finds in one string.
   - `key(term)`: the normalized words of a term, for comparing terms.
   - `read_entries(workspace)`: the validated `decisions/terms.json` entries, or the errors the check would print.
   - `replacement_conflicts(entries)`: one line for each replacement that contains a denied term.
2. `rcore/profile.py` gains the JSON Resume vocabulary resume-import's check used (`BASICS`, `LOCATION`, `PROFILE_ITEM`, `SECTIONS`, `ARRAY_FIELDS`, `DATE_FIELDS`), `PROSE_FIELDS`, and the entry identities that re-import warnings compare (`IDENTITY`, `identity`, `describe`, `merged_arrays`). resume-import imports them from there. See the [resume-wizard spec](2026-09-25-resume-wizard-design.md) for the rest of its changes.
3. `rcore/facts.py` gains `fact_values(profile)`: `(pointer, value)` for each fact field of a profile that a tailored resume may copy, derived from `tailored-resume.schema.json`.
4. Fixture: `05-terms/candidates.json` gains `found_in` as `scan.py --commit` computes it, `07-sanitized/new-terms.json` is `[]`, and `07-sanitized/bullets.json` `b_1` is the mechanical replacement (it had an article the replacement does not write). From the fixture's projects, evidence and profile, with its candidates as the draft, `scan.py --commit` writes the saved `candidates.json` byte for byte. From the fixture's bullets, stories, profile and terms, `apply.py --commit` writes the saved `07-sanitized/` files byte for byte.
5. `pytest.ini` adds `skills/resume-sanitize/scripts` to `pythonpath`. The test command and CI do not change: sanitize uses only the standard library.
6. The architecture spec: the plugin layout lists `scan.py` and `apply.py`; the resume-sanitize section points here and states the texts scanned, the replacement rule, prose and facts, new terms and the stage inputs.

## Error handling

| Case | Behavior |
|---|---|
| No projects or evidence | `scan.py` exits 1 naming `/resume-builder:analyze` or `/resume-builder:collect`. Nothing begun. |
| No bullets or stories | `apply.py` exits 1 naming `/resume-builder:write`. Nothing begun. |
| Missing or invalid `decisions/terms.json` | Exit 1, as in the terms check. |
| A replacement holds a denied term, or one term has two replacements | `apply.py` exits 1 naming the entries. The wizard changes them. |
| A candidate or new-term problem | Exit 1, one line per problem and a `fix:` line. The draft stays in the `.tmp/` folder to fix. |
| A denied term left after replacing | `apply.py` exits 1 naming each place. Nothing begun. |
| Inputs changed between `apply.py` and `--commit` | Exit 1. Run `apply.py` again and review the new text. |
| A raw review record cannot be read | Warning. The excerpt stands in for the full text. |
| Fact field holds a denied term | Warning. The wizard sets a replacement value. |
| Commit fails | Exit 1. The previous stage stays. |

## Testing

- **Detectors:** each kind on made-up text, the sentence-start rule for names (a single word skipped, a run also counted without its first word), two- and three-letter capitals, Jira keys, function words, overlapping hits, grouping by normalized term.
- **Texts:** project fields, only project evidence and reviews, a review's full text from `01-raw/`, a missing raw record (warning, excerpt used), every profile string with its pointer.
- **find and replace:** separators, invisible characters and plurals replaced whole; an allowed term exempting a match; `Contoso` and `Contoso Bank` overlapping; capitals at a text start, after `.` and `:`, after Markdown markers, never mid-sentence; a replacement never lowercased; the exact fixture bullet and stories.
- **Prose and facts:** only prose fields change; fact fields and `x-lines` stay byte for byte.
- **Replacement checks:** a replacement holding a denied term, one term with two replacements.
- **Candidates:** each check failing on its own with its line; the decided-term note; `found_in` in text order.
- **New terms:** an undecided candidate that must be listed, a decided term rejected, a term not in the sanitized text rejected, `found_in` with bullets, story lines and profile pointers.
- **CLIs:** exit codes; `scan.py` begins fresh; `--commit` without a `.tmp/`; inputs changed between `apply.py` and `--commit`; the commit's inputs and `extra`; `05-terms` stays fresh after a term decision while `07-sanitized` goes stale; fact-field warnings; notices.
- **Must promises:** `07-sanitized/stories.md` is written; profile fact fields and `x-lines` are unchanged.
- **Fixture end to end:** `scan.py --commit` and `apply.py --commit` rebuild the saved `05-terms/candidates.json` and `07-sanitized/` byte for byte, the committed stages validate, and render's gate passes on the result.

## Out of scope for v1

- Recognizing names by meaning (a customer spelled in lower case, a person's name). The detectors are hints. The model and the engineer's review decide.
- Rewording a sentence that a replacement makes awkward. The engineer fixes the replacement or the bullet.
- Homoglyphs, which the terms check does not catch either (architecture spec, Known limits).
