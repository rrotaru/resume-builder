# resume-wizard: Design

- **Date:** 2026-09-25
- **Status:** Approved
- **Scope:** The `resume-wizard` skill (checkpoint 3): one session that asks the engineer for metric values, missing profile fields and term decisions, including replacement values for fact fields that hold a denied term, and fixes answers that a re-import or a regrouping left behind. Also the resume-core changes it needs. This is the second half of follow-up spec 6 of the [architecture spec](2026-09-24-resume-builder-architecture-design.md). The [resume-sanitize spec](2026-09-25-resume-sanitize-design.md) is the first half: it proposes the terms the wizard asks about.

## Goal

Collect what only the engineer knows, once, and keep it correct from run to run. The wizard writes only to `decisions/`. Later stages rely on three of its files: `decisions/metrics.json` (the numbers `xyz_quantified` bullets cite), `decisions/profile.json` (profile answers the fact-field check accepts as fact) and `decisions/terms.json` (what sanitize replaces and render blocks). Each answer must land exactly where the overlay rules and the checks read it. A question answered in an earlier run is not asked again, unless what it was answered about has changed.

## Gaps

The architecture spec and the roadmap leave these open:

1. **Nothing writes decisions exactly.** Hand-written JSON can put a profile answer at the wrong index, add an empty entry past the imported end (the overlay adds it as a new, empty entry), or use a field name the overlay copies but nothing reads.
2. **"Already answered" is undefined for a no.** An engineer with no phone number on their resume, or no metric for a project, is asked again on every run, because nothing records the answer.
3. **Moved answers are reported only once.** `check_profile.py --commit` prints a warning when a re-import moves an answered entry. The wizard owns the fix, but the warning is gone by the next session, and the answer keeps merging into the wrong job.
4. **A metric cannot find its project again.** `match_projects.py` warns when a metric's project is gone, but a metric records no evidence, so nothing can say which current project it belongs to.
5. **"Missing profile fields" is not a list.** Nothing says which fields the wizard asks about.
6. **Term decisions can break later stages.** An allowed term that contains a denied term makes `decisions/terms.json` invalid, and a replacement that contains a denied term makes sanitize's output fail the terms check.
7. **Fact fields with denied terms.** The wizard must ask for a replacement value, but not every fact field can take one: `keywords` combine rather than replace in the overlay.
8. **New terms at checkpoint 4 have no writer.** `07-sanitized/new-terms.json` lists terms for the engineer to decide, and only the wizard and checkpoints write `decisions/terms.json`.

## Decisions

| Topic | Decision |
|---|---|
| Two scripts | `questions.py` lists the open questions, in a fixed order, from the current workspace. `answer.py` records one answer per command in `decisions/`, checked, and replaces the file atomically. The model asks and records. It never edits `decisions/` by hand (gap 1). |
| Profile answers | `answer.py profile POINTER VALUE` writes a fact at a JSON Pointer under the overlay rules: arrays of objects are padded with `{}` up to the index, the index may be at most one past the effective array, and only JSON Resume fact fields are accepted. Prose fields are refused (gap 1). |
| Bookkeeping | A new file, `decisions/wizard.json`, records skipped questions and which imported entry each profile answer was given for. It is written only by `answer.py` and read only by the wizard. No stage records it as an input (gaps 2 and 3). |
| Skips | The engineer may decline a missing profile field or a metric. `answer.py skip` records it, and it is not asked again. A skip inside an entry is kept only while the imported entry is the same one (gap 2). |
| Moved answers | Every answer inside an array of objects has an anchor: the identity of the imported entry it was given for (`rcore.profile.identity`, the fields resume-import's warnings compare), or null for an entry the wizard added. When the imported entry at that index no longer matches, the answer is a question again: move it, confirm it, or remove it (gap 3). |
| Metric evidence | `metrics.json` records gain optional `evidence_ids`: the project's evidence when the metric was recorded, as `decide.py` stores for project decisions. A metric whose project is gone is shown with the reason from `decisions/projects.json` and the current project sharing the most of its evidence (gap 4). |
| Profile questions | A fixed list: name, email, phone, location, links, each job's employer, title and start date, education, and certifications ([Missing profile fields](#missing-profile-fields)) (gap 5). |
| Term checks | `answer.py term` validates the whole of `decisions/terms.json` before writing: the schema, allowed terms that contain a denied term (`rcore.terms.allowed_conflicts`), and replacements that contain a denied term (`rcore.terms.replacement_conflicts`) (gap 6). |
| Fact fields | Every fact field a tailored resume may copy (`rcore.facts.fact_values`) that holds a denied term is a question, answered with `answer.py profile` at that path. A keyword cannot be replaced, so a keyword holding a denied term is a `note:`: resume-ats leaves it out (gap 7). |
| New terms | The wizard asks about undecided terms from `05-terms/candidates.json` and from `07-sanitized/new-terms.json`, so checkpoint 4 decides new terms by running the wizard (gap 8). |
| Which questions can be skipped | Missing profile fields (except the name, which render needs) and metrics. A moved answer, a metric whose project is gone, a term and a fact field holding a denied term must be resolved, because each would otherwise leave a wrong or blocked value in a later stage. |

## Skill layout

```
skills/resume-wizard/
  SKILL.md
  scripts/
    questions.py           # CLI: list the open questions
    answer.py              # CLI: record one answer in decisions/
    rwizard/
      common.py            # errors, workspace files, atomic writes
      state.py             # decisions/wizard.json: anchors and skips
      profile.py           # profile answers: pointers, overlay padding, fact fields, moved answers
      terms.py             # term decisions and their checks
      metrics.py           # metrics: IDs, the value in the statement, projects that are gone
      questions.py         # computing the open questions and how each is answered
skills/resume-core/schemas/
  wizard-state.schema.json # new: decisions/wizard.json
```

Every script uses only the standard library and imports `rcore` as portability rule 6 allows.

## Command line

```
uv run scripts/questions.py --workspace WS [--all]
uv run scripts/answer.py --workspace WS profile POINTER VALUE
uv run scripts/answer.py --workspace WS add POINTER VALUE
uv run scripts/answer.py --workspace WS unset POINTER
uv run scripts/answer.py --workspace WS confirm ENTRY
uv run scripts/answer.py --workspace WS move ENTRY TO
uv run scripts/answer.py --workspace WS term TERM (--replacement TEXT | --allow) [--kind KIND]
uv run scripts/answer.py --workspace WS remove-term TERM
uv run scripts/answer.py --workspace WS metric PJ --value N --unit UNIT --statement TEXT
uv run scripts/answer.py --workspace WS relink-metric M PJ
uv run scripts/answer.py --workspace WS remove-metric M
uv run scripts/answer.py --workspace WS skip QUESTION
uv run scripts/answer.py --workspace WS unskip QUESTION
```

| Script | Exit | Meaning |
|---|---|---|
| `questions.py` | 0 | Questions listed (possibly none) |
| | 1 | Error: an invalid decisions file or input. The line names it. |
| `answer.py` | 0 | Answer recorded (or nothing to change, said so) |
| | 1 | Rejected: the named rule. Every file is left unchanged. |
| Both | 2 | Usage error |

## Questions

`questions.py` reads `03-profile/profile.json`, `03-profile/source.json`, `04-projects/projects.json`, `05-terms/candidates.json` and `07-sanitized/new-terms.json` when they exist, and `decisions/profile.json`, `decisions/terms.json`, `decisions/metrics.json`, `decisions/projects.json` and `decisions/wizard.json`. A missing decisions file counts as empty. It validates each file it reads, and stops on an invalid one. It lists the open questions in this order, because each group can change the next:

| Order | Question key | Asked when | Resolved by |
|---|---|---|---|
| 1 | `moved:/work/1` | An answer inside an array of objects whose anchor no longer matches the imported entry at that index, or that has no anchor | `move`, `confirm` or `unset` |
| 2 | `metric-gone:m_1` | A metric whose `project_id` is not in `04-projects/projects.json` | `relink-metric` or `remove-metric` |
| 3 | `term:Contoso Bank` | A term in `05-terms/candidates.json` or `07-sanitized/new-terms.json` that `decisions/terms.json` does not decide (compared by `rcore.terms.key`) | `term` |
| 4 | `fact:/projects/0/name` | A fact field of the effective profile that a tailored resume may copy and that holds a denied term, except keywords | `profile` at that path, or a changed term decision |
| 5 | `profile:/basics/phone` | A [missing profile field](#missing-profile-fields) | `profile`, `add` or `skip` |
| 6 | `metric:pj_da2a2b53` | A project with `metric_prompt: true` that has no metric | `metric` or `skip` |

A question already skipped is not listed, unless `--all` is given, when it is listed with `(skipped)`. Nothing is asked about a project without `metric_prompt`. The last line counts the open questions: `wizard: 3 open questions` or `wizard: no open questions`, followed by `, 1 skipped (questions.py --all lists them)` when there are skips.

Each question prints as its key, a description, and the commands that resolve it:

```
moved:/work/1  {"endDate": "2022-12"} was answered for 'Software Engineer, Tailspin Toys'; /work/1 is now 'Engineer, Contoso'
  answer: answer.py move /work/1 /work/2 ('Software Engineer, Tailspin Toys' is now /work/2), answer.py confirm /work/1 or answer.py unset /work/1
metric-gone:m_1  'p99 checkout latency reduced 40%': pj_da2a2b53 was merged into pj_77e0a1c3 by decision 2; closest is pj_77e0a1c3 'Ledger export retries' (3 of its 3 items)
  answer: answer.py relink-metric m_1 PJ or answer.py remove-metric m_1
term:Contoso Bank  customer, proposed 'a top-10 US bank'; in 3 places: pj_da2a2b53, ev_99a74656, ev_191cc8ce
  answer: answer.py term 'Contoso Bank' --replacement TEXT or answer.py term 'Contoso Bank' --allow
fact:/projects/0/name  'Falcon' holds the denied term 'Falcon'
  answer: answer.py profile /projects/0/name VALUE
profile:/basics/phone  phone number
  answer: answer.py profile /basics/phone VALUE or answer.py skip profile:/basics/phone
metric:pj_da2a2b53  rank 1 'Project Falcon checkout latency' [lead, cross-team, 2025-02 to 2025-05]
    Idempotency cache that cut checkout latency for Contoso Bank.
    reasons: authored the core PR and owned the epic; customer-facing latency impact
  answer: answer.py metric pj_da2a2b53 --value N --unit UNIT --statement TEXT or answer.py skip metric:pj_da2a2b53
wizard: 6 open questions
```

Before the questions it prints a `note:` for each input that is missing (`04-projects/projects.json not found: no metric questions; run /resume-builder:analyze`), each keyword holding a denied term, and the allowed-term notices from `rcore.terms.allowed_notices`.

### Missing profile fields

On the effective profile (`rcore.profile.effective_profile`):

| Key | Asked when | Answered by |
|---|---|---|
| `profile:/basics/name` | no name (render needs one, so it cannot be skipped) | `/basics/name` |
| `profile:/basics/email` | no email | `/basics/email` |
| `profile:/basics/phone` | no phone | `/basics/phone` |
| `profile:/basics/location` | no `location.city` | `/basics/location/city`, and `region` and `countryCode` when the engineer gives them |
| `profile:/basics/profiles` | no `profiles` and no `url` | `/basics/profiles/-/network`, `username` and `url`, or `/basics/url` |
| `profile:/work/1/name`, `/position`, `/startDate` | a job without an employer, a title or a start date | that path |
| `profile:/work/1/endDate` | a job without an end date, when the resume was a JSON Resume file (`source.json` `format: json`) | `/work/1/endDate`, or `skip` when the job is current. A text import proves an open job is ongoing, so it is not asked. |
| `profile:/education` | no education | `/education/-/institution` and the rest, or `skip` |
| `profile:/education/0/institution`, `/studyType`, `/area`, `/endDate` | an education entry without it | that path |
| `profile:/certificates` | no certificates | `/certificates/-/name` and the rest, or `skip` |
| `profile:/certificates/0/name`, `/issuer`, `/date` | a certificate without it | that path |

## Recording answers

`answer.py` reads the files it changes, validates them, applies one change, validates the result against its schema and the rules below, and replaces each changed file through a temporary file. On any error it prints `error:` lines and `decisions/ unchanged`, and exits 1.

### Profile answers

`answer.py profile POINTER VALUE` records a fact in `decisions/profile.json`:

- `POINTER` is one of `/basics/<name|label|email|phone|url>`, `/basics/location/<address|postalCode|city|countryCode|region>`, `/basics/profiles/<i>/<network|username|url>`, or `/<section>/<i>/<field>` for a JSON Resume section and one of its fields. Prose (`summary`, `description`, `highlights`, `reference`) is refused: the wizard records facts. So are array fields (`keywords`, `courses`, `roles`), which `add` records.
- The index `i` may be any existing entry of the effective profile, or one past the end to add an entry. `-` means one past the end, and the script prints the resolved pointer so the next field of the same entry uses the number.
- The value is trimmed and must not be empty. A date field (`startDate`, `endDate`, `date`, `releaseDate`) must be `YYYY`, `YYYY-MM` or `YYYY-MM-DD` naming a real date. The value must not contain a denied term.
- The wizard's arrays are padded with `{}` up to the index, so `answer.py profile /work/1/endDate 2022-12` on an empty file writes `{"work": [{}, {"endDate": "2022-12"}]}`, which fills in the second job's end date and leaves the first unchanged.
- An entry whose answer is waiting for `move` or `confirm` is refused until that is done.
- The first answer inside an entry records its anchor in `decisions/wizard.json`: the identity of the imported entry at that index, or null when the index is past the imported end.

`answer.py add POINTER VALUE` adds one item to an array field (`/skills/0/keywords`), which the overlay combines with the imported items. A value already in the effective array is left alone (`already in the profile; nothing recorded`).

`answer.py unset POINTER` removes a wizard answer, so the imported value applies again. `unset /work/1` removes the whole answer for that entry. Trailing `{}` entries, and objects and arrays left empty, are removed, and so is the anchor of an entry with no answer left. A pointer with no answer is an error.

### Moved answers

An answer inside an array of objects (`decisions/profile.json` `/work/1`, `/basics/profiles/0` and so on) carries an anchor in `decisions/wizard.json`:

```json
{"anchors": [{"entry": "/work/1", "answered_for": {"position": "Software Engineer", "name": "Tailspin Toys"}},
             {"entry": "/certificates/0", "answered_for": null}],
 "skipped": [{"question": "profile:/basics/phone"}]}
```

`answered_for` holds the identity fields of the imported entry the answer was given for (`rcore.profile.IDENTITY`: `position` and `name` for `work`, `studyType`, `area` and `institution` for `education`, and so on), or null for an entry the wizard added past the imported end. When `03-profile/profile.json` changes so that the entry at that index has a different identity, or an imported entry now sits where the wizard added one, the answer is a `moved:` question. A non-empty answer with no anchor, such as one written before the wizard existed, is a `moved:` question too, asked once.

- `answer.py confirm ENTRY` keeps the answer where it is and anchors it to the current imported entry.
- `answer.py move ENTRY TO` moves the answer to `TO` in the same array, which must hold no answer yet and follow the index rule above. `ENTRY` becomes `{}` (or is trimmed), and the anchor moves with it. The question suggests `TO`: the index of the imported entry the answer was given for, or one past the imported end for an answer that added an entry.
- `answer.py unset ENTRY` drops the answer.

### Terms

`answer.py term TERM --replacement TEXT` denies a term, and `answer.py term TERM --allow` allows it (`replacement: null`). `--kind` defaults to the candidate's kind when `TERM` is a candidate or a new term, and is required otherwise. The term must be at least two characters, and a replacement must not be empty. An entry for the same term (`rcore.terms.key`) is replaced in place, otherwise the entry is added.

The whole resulting file must pass the checks the terms check and sanitize apply rely on, or nothing is written:

```
error: decisions/terms.json: allowed term 'Contoso Bank' contains denied term 'Contoso'; remove it or reword
error: decisions/terms.json: the replacement for 'Project Falcon' ('Contoso-grade platform') contains the denied term 'Contoso'
decisions/ unchanged
```

After recording, it prints the allowed-term notices and, when a fact field holds a denied term, `1 fact field of the profile holds a denied term: questions.py lists them as fact: questions`. `answer.py remove-term TERM` removes a decision. It needs only a JSON list to work on, so it can repair a file the checks reject.

### Metrics

`answer.py metric PJ --value N --unit UNIT --statement TEXT` adds a metric:

- `PJ` is a project in `04-projects/projects.json`. The wizard asks only about projects with `metric_prompt: true`, but a metric the engineer volunteers for another current project is accepted.
- `N` is written as digits the way a statement writes it (`40`, `-3`, `2.5`). It is stored as an integer when written without a decimal point. An exponent (`1e6`), thousands separators, `inf` and `nan` are refused, so the value can always be found in the statement.
- `UNIT` must not be empty (`%`, `ms`, `requests/s`, `incidents`). A metric without one would be incomplete and would silence the project's question.
- The statement is one sentence that states the value: a number in it, with thousands separators removed, equals `N` (`p99 checkout latency reduced 40%` for 40). This keeps the statement and the value the bullet cites the same number.
- The ID is `m_<n>`, one more than the highest numbered metric ID.
- `evidence_ids` stores the project's evidence IDs, sorted.

`answer.py relink-metric M PJ` sets the metric's project and evidence snapshot to a current project's. `answer.py remove-metric M` removes it. A bullet that cites a removed metric fails the source check until resume-write runs again, which `stage.py status` shows as a stale `06-bullets`.

A `metric-gone:` question names what happened to the project where `decisions/projects.json` says so (the last `exclude` of it, or the last `merge` naming it in `merge_with`), and the current project sharing the most of the metric's `evidence_ids`, if any does.

### Skips

`answer.py skip QUESTION` records a `profile:` or `metric:` question the engineer declines. It must be an open question. A skip inside an entry (`profile:/work/1/startDate`) stores the entry's identity like an anchor and applies only while the imported entry is the same. `answer.py unskip QUESTION` asks it again.

## `decisions/` files

| File | Written by the wizard | Schema |
|---|---|---|
| `profile.json` | `profile`, `add`, `unset`, `move` | `resume.schema.json` |
| `terms.json` | `term`, `remove-term` | `terms.schema.json` |
| `metrics.json` | `metric`, `relink-metric`, `remove-metric` | `metrics.schema.json` (gains optional `evidence_ids`) |
| `wizard.json` | every command that changes an anchor or a skip | `wizard-state.schema.json` (new) |

Stages record `decisions/profile.json`, `terms.json` and `metrics.json` as inputs where they read them, so an answer makes them stale and `stage.py status` shows what to run again. No stage records `wizard.json`.

## SKILL.md

1. Run `stage.py status`. Tell the engineer about any stage that is stale. If `04-projects` is missing, say there will be no metric questions and suggest `/resume-builder:analyze`. If `05-terms` is missing, say there will be no term questions and suggest the sanitize scan.
2. Run `questions.py`. If it prints `wizard: no open questions`, report that and stop.
3. Ask the questions in the printed order, a few at a time, and record each answer with one `answer.py` command as soon as the engineer gives it, so an interrupted session loses nothing:
   - **Moved answers.** Show the answer, the entry it was given for and the entry it now merges into. Move it where the question suggests, confirm it, or remove it, as the engineer says.
   - **Metrics whose project is gone.** Re-link to the suggested or another project, or remove.
   - **Terms.** Show the term, its kind, where it was found and the proposed replacement. Ask whether to use the proposal, a different generalization, or allow the term as it is. A replacement must be true and generic, fit where the term stood in a sentence, and name no other company or product.
   - **Fact fields.** Explain that names, titles and dates are copied exactly onto the resume, so a denied term there needs a replacement value for that field, for example a generic project name. Or the engineer may decide to allow the term instead.
   - **Missing profile fields.** Ask for each. Record exactly what the engineer says, with dates as `YYYY`, `YYYY-MM` or `YYYY-MM-DD`. Skip what they decline.
   - **Metrics.** Show the project. Suggest kinds of measurable results that fit it (latency, error rate, cost, throughput, adoption, time saved), but never a value. Ask for the value, the unit and one sentence stating it. Skip when the engineer has none.
4. Run `questions.py` again, because deciding a term can make a fact field a question. Repeat until none are open.
5. Report what was recorded, what was skipped, every `note:` (keywords that resume-ats will leave out) and `notice:` line, and the stages `stage.py status` now shows as stale.

Never edit `decisions/` by hand, never invent a metric value or a profile value, and never record an answer the engineer did not give.

## Changes to resume-core, fixtures and the architecture spec

1. New `wizard-state.schema.json`, mapped in `FILE_SCHEMAS` as `decisions/wizard.json`. `init_workspace.py` creates it as `{"anchors": [], "skipped": []}`.
2. `metrics.schema.json` gains optional `evidence_ids`.
3. `rcore/profile.py` gains the JSON Resume vocabulary, `PROSE_FIELDS`, the identity functions and `is_date`, and `resume-import` imports its field lists and identities from there ([resume-sanitize spec](2026-09-25-resume-sanitize-design.md#changes-to-resume-core-fixtures-and-the-architecture-spec)). `rcore/terms.py` gains `key`, `read_entries` and `replacement_conflicts`, and `rcore/facts.py` gains `fact_values`.
4. Fixture: `decisions/wizard.json` anchors the certificate answer (`/certificates/0`, added past the imported end) and records the skipped phone question, so `questions.py` finds no open questions. `decisions/metrics.json` `m_1` gains the project's `evidence_ids`.
5. `pytest.ini` adds `skills/resume-wizard/scripts` to `pythonpath`.
6. The architecture spec: the plugin layout lists `questions.py` and `answer.py`; the workspace tree and the Decisions table list `wizard.json` and the metric's `evidence_ids`; the resume-wizard section points here.

## Error handling

| Case | Behavior |
|---|---|
| Invalid decisions file or input | `questions.py` and `answer.py` exit 1 naming it. `remove-term` still works on a `decisions/terms.json` that the checks reject, as long as it is a JSON list. |
| A pointer that is not a fact field, an index past the end, a bad date, a denied term in a value | Rejected, file unchanged. |
| A term decision that would make `terms.json` invalid or a replacement that holds a denied term | Rejected, file unchanged. |
| A metric statement that does not state its value, a value that is not plain digits, an empty unit, an unknown project | Rejected, file unchanged. |
| An answer waiting for `move` or `confirm` | Other answers in that entry are rejected until it is resolved. |
| Missing `04-projects` or `05-terms` | A `note:`. The other questions are still asked. |

## Testing

- **Pointers and the overlay:** `/work/1/endDate` on an empty file gives `{"work": [{}, {"endDate": "2022-12"}]}` and the effective profile fills the second job only; `-` resolves past the end; an index two past the end, a prose field, an array field, an unknown field and a bad date are rejected; `add` combines keywords; `unset` trims trailing `{}` and empty objects.
- **Anchors:** the first answer in an entry records it; a re-import that moves the entry makes a `moved:` question with the right suggestion; `move`, `confirm` and `unset` resolve it; an answer with no anchor is asked once; an answer waiting for a move blocks other answers there.
- **Skips:** a skipped question is not listed; `--all` lists it; a skip inside an entry lapses when the entry changes; only open `profile:` and `metric:` questions can be skipped.
- **Terms:** a candidate and a new term become questions until decided; replacing an existing decision; `--kind` from the candidate; an allowed term containing a denied one and a replacement holding a denied term are rejected; `remove-term` repairs an invalid file.
- **Fact fields:** a denied term in a project name is a question; recording a replacement resolves it; a replacement holding a denied term is rejected; a keyword gives a note.
- **Metrics:** questions only for `metric_prompt` projects; the statement rule; values as digits only; an empty unit; IDs; the evidence snapshot; `metric-gone` with the exclude and merge reasons and the closest project; relink and remove.
- **Profile questions:** each row of the table, including the JSON Resume end-date rule.
- **CLIs:** exit codes, every file unchanged on error, atomic replacement.
- **Must promises:** answers follow the overlay rules; a fact field holding a denied term gets a replacement at that path; a moved answer is fixed by the wizard; metrics are asked only for `metric_prompt` projects and re-linked or removed when their project is gone.
- **Fixture:** `questions.py` reports no open questions; with the phone skip removed it asks exactly for the phone; the fixture's decisions still validate and render's gate still passes.

## Out of scope for v1

- Removing an imported value. The overlay cannot remove one; a tailored resume may leave a non-date fact field out.
- Prose answers, such as a summary. Summaries and bullets are written by later stages from sources.
- Suggesting metric values. The model may suggest kinds of metrics, never numbers.
