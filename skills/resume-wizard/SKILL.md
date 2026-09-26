---
name: resume-wizard
description: Ask the engineer, in one session, for what only they know in a resume-builder workspace (checkpoint 3), and record it in decisions/. Measurable results (metrics) for the top projects, missing profile details (name, contact details, location, links, job dates, education, certifications), decisions on each proposed confidential term, a replacement value for any name or title that holds a denied term, and fixes for answers that a re-import or a project regrouping left pointing at the wrong entry. Skips what was answered in earlier runs. Use when the engineer asks to run the wizard, fill in missing details or metrics, decide confidential terms, or when resume-build reaches checkpoint 3 or the new terms at checkpoint 4.
---

# resume-wizard

Follow `../resume-core/SKILL.md` for workspace conventions.

- Resolve `scripts/...` and `../resume-core/...` against this skill's own folder, not against the current directory.
- Run commands from the engineer's project directory, not from the skill folder.
- Always pass `--workspace` explicitly, preferably as an absolute path.

The wizard writes only to `decisions/`, and only through `scripts/answer.py`. Later stages rely on these answers: bullets cite metrics by ID, the resume copies names, titles and dates from the profile with these answers laid over it, and sanitize and render use the term decisions. `questions.py` works out what is still open; `answer.py` records one answer per command and refuses anything the later checks would reject.

## Steps

1. Run `uv run ../resume-core/scripts/stage.py --workspace WS status`. Tell the engineer about any stage that is `stale`.
   - If `04-projects` is `missing`, say there will be no metric questions and suggest `/resume-builder:analyze`.
   - If `05-terms` is `missing`, say there will be no term questions and suggest the sanitize scan (`/resume-builder:sanitize`).
2. Run `uv run scripts/questions.py --workspace WS`. It prints `note:` and `notice:` lines, then each open question as its key, a description, and the `answer:` commands that resolve it, then a count. If it prints `wizard: no open questions`, report that and stop.
3. Ask the questions in the printed order, a few at a time, and record each answer with one `answer.py` command as soon as the engineer gives it, so an interrupted session loses nothing. Every command is `uv run scripts/answer.py --workspace WS ...`.
   - **`moved:`** An answer no longer sits on the entry it was given for, usually because a re-import changed the order of jobs. Show the answer, the entry it was given for and the entry it now merges into. Then, as the engineer says: `move ENTRY TO` (the question suggests where), `confirm ENTRY` (it is right where it is), or `unset ENTRY` (drop it).
   - **`metric-gone:`** A metric's project was excluded, merged or regrouped at checkpoint 2. Show the reason and the closest project. Then `relink-metric M PJ` or `remove-metric M`.
   - **`term:`** Show the term, its kind, where it appears and the proposed replacement. Ask whether to use the proposal, a different generalization, or allow the term as it is. Record `term "TERM" --replacement "TEXT"` or `term "TERM" --allow`. A replacement must be true and generic, read well where the term stood in a sentence (`a top-10 US bank`), and name no other company or product.
   - **`fact:`** A name, title or other fact field holds a denied term. Explain that facts are copied exactly onto the resume, so it needs a replacement value for that field, for example a generic project name. Record `profile POINTER "VALUE"` at the printed pointer. The engineer may instead decide to allow the term (`term "TERM" --allow`).
   - **`profile:`** Ask for the missing detail and record exactly what the engineer says: `profile POINTER "VALUE"`, with dates as `YYYY`, `YYYY-MM` or `YYYY-MM-DD`. For a new entry use `-` as the index (`/certificates/-/name`), then the number the script prints for the entry's other fields. If the engineer declines, `skip QUESTION`.
   - **`metric:`** Show the project. Suggest kinds of measurable result that fit it, such as latency, error rate, cost, throughput, adoption or time saved, but never a value. Ask for the value, its unit and one sentence stating it: `metric PJ --value N --unit UNIT --statement "TEXT"`. Write the value as plain digits (`40`, `2.5`), give a unit (`%`, `ms`, `requests/s`), and write the same number in the statement. If the engineer has none, `skip QUESTION`.
4. Run `questions.py` again: deciding a term can turn a fact field into a question. Repeat until no questions are open.
5. Report what was recorded and what was skipped, every `note:` line (a keyword holding a denied term is left out of the resume), every `notice:` line (an allowed term that looks like a denied one; the engineer confirms it is a different word), and the stages `stage.py status` now shows as `stale`.

Never edit `decisions/` by hand. Never invent a metric or a profile value, and never record an answer the engineer did not give.

## Other answer.py commands

- `add POINTER VALUE` adds one item to a list field, such as a skill keyword (`add /skills/0/keywords Kafka`).
- `unset POINTER` removes a profile answer, so the imported value applies again.
- `remove-term TERM` removes a term decision.
- `unskip QUESTION` asks a skipped question again. `questions.py --all` lists the skipped ones.

## What the scripts guarantee

- Profile answers follow the overlay rules: an answer for the second job is written as `"work": [{}, {"endDate": "2022-12"}]`, which fills in that job and leaves the first unchanged. An entry number may be at most one past the end, so no empty entry is added. Only JSON Resume fact fields are accepted, never prose.
- No answer contains a denied term, and `decisions/terms.json` stays valid: no allowed term contains a denied one, and no replacement contains a denied term.
- Each answer inside a job, school, certificate or profile link remembers which imported entry it was given for, so a re-import that moves the entry makes it a question again instead of silently changing another entry.
- Metrics are asked for only for projects marked for metric prompts, get IDs `m_1`, `m_2` and so on, keep the project's evidence so a regrouped project can be found again, and state their value in their statement.
- A question answered or skipped in an earlier run is not asked again. A skip inside an entry lapses if the entry changes.

## Output

```
decisions/
  profile.json   # profile answers, laid over 03-profile/profile.json
  terms.json     # term decisions: a replacement denies a term, null allows it
  metrics.json   # confirmed metrics for the top projects
  wizard.json    # which entry each profile answer was given for, and skipped questions
```
