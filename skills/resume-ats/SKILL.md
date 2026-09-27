---
name: resume-ats
description: Build the engineer's ATS-friendly resumes in a resume-builder workspace (08-ats/). The general resume selects, orders and rewords the sanitized bullets within what their sources say and fits one or two pages; each job version (--jd, a posting) may rewrite freely, and a script flags every claim a rewrite adds that its sources do not state, for checkpoint 4. Scripts copy every name, title and date from the profile, put each bullet under its job or project, report keyword coverage (covered, missing with evidence, missing without), lint the result and check it as render will. Use when the engineer asks to tailor or target a resume, check it against a job posting or its keywords, or when resume-build reaches the ats step.
---

# resume-ats

Follow `../resume-core/SKILL.md` for workspace conventions.

- Resolve `scripts/...` and `../resume-core/...` against this skill's own folder, not against the current directory.
- Run commands from the engineer's project directory, not from the skill folder.
- Always pass `--workspace` explicitly, preferably as an absolute path.

`08-ats/` holds the versions render prints: `general/` and `jobs/<slug>/`. `scripts/ats.py` drafts one version at a time into `08-ats.tmp/`: every fact (name, contact details, employers, titles, dates, schools, certificates, skills) copied from the profile, and every bullet of `07-sanitized/bullets.json` under the job or project it belongs to. You choose which bullets to keep, their order and their wording, and write each version's keywords. `ats.py --commit` checks every version and commits. Never type a fact yourself: the checks reject anything not copied from the profile.

## Steps

1. Run `uv run ../resume-core/scripts/stage.py --workspace WS status`.
   - If `07-sanitized` is `missing`, stop and suggest `/resume-builder:write`, then `/resume-builder:sanitize`. If it or an earlier stage is `stale`, tell the engineer and offer to rebuild it first.
   - If `08-ats.tmp/` exists, a draft is in progress: every `ats.py` command continues it. To start over from the committed stage instead, run `uv run ../resume-core/scripts/stage.py --workspace WS begin 08-ats --from-current`.
2. Draft the general resume: `uv run scripts/ats.py --workspace WS`. It prints:
   - `warning:` lines: a stale stage, a bullet with no place (its project falls in no job; it is left out until the engineer adds the job with the wizard). `note:` lines: a skill keyword holding a denied term, which is left out.
   - The target role, the engineer's experience and the page budget (under 8 years, 1 page; otherwise 2, at 50 estimated lines a page).
   - Each job (`/work/<i>`) and profile project (`/projects/<i>`) with the bullets drafted under it.
3. Write `08-ats.tmp/general/keywords.json`, a JSON list of the keywords an ATS would match for the target role: skills, technologies and practices, spelled as postings spell them (`["Go", "PostgreSQL", "Kubernetes", "incident response"]`). Then run `uv run scripts/keywords.py --workspace WS general`:
   - `covered`: on the resume already.
   - `missing with evidence`: a bullet, an evidence item, a review, a metric or the profile mentions it. A bullet whose sources hold it can be reworded to use it. Or ask the engineer whether it belongs in their skills; if yes, record it with the wizard (`answer.py add /skills/<i>/keywords KEYWORD`). That makes `06-bullets` stale: recommit write (`write.py --from-current`, then `write.py --commit`) and sanitize apply (`apply.py`, then `apply.py --commit`), and draft again. Never add a keyword to `skills` in the resume: only the profile's keywords pass.
   - `missing without evidence`: nothing supports it. Leave it out.
4. Edit `08-ats.tmp/general/resume.json`:
   - **Select.** Leave out the weakest bullets until the draft fits the page budget. Keep the bullets with measured results, those matching the keywords, and recent work. You may leave out a whole entry (an old job, a project), but every job left out is a gap in the dates.
   - **Order.** Strongest bullet first in each entry. Keep jobs most recent first.
   - **Reword** only within what each bullet's sources say: shorter, clearer, the target role's vocabulary. Add no technology, number, keyword or claim of scope (`led`, `cross-team`, `company-wide`) that the bullet's text, its sources or its job's name and title do not state. The general resume may have no claim; the commit refuses one.
   - **Summary** (optional): `basics.summary`, two or three sentences drawn from the bullets, with `basics.x-summary-sources` citing their sources. The same claim rule applies.
   - Edit only `x-highlights` texts: the commit writes `highlights` from them. Never change a `bullet_id` or `sources`, move a bullet to another entry, add a bullet, or retype a fact. Leave facts as drafted; you may shorten a date (`2023-01-15` to `2023-01`).
   - Run `uv run scripts/ats_lint.py --workspace WS general` and `uv run scripts/diff_claims.py --workspace WS general` until both pass.
5. Run `uv run scripts/ats.py --workspace WS --commit`. On exit 1 nothing was committed: fix the draft as each line and its `fix:` line say, and commit again.
6. For each job posting the engineer gives:
   - Save it as UTF-8 text if it is a PDF or a web page. Run `uv run scripts/ats.py --workspace WS --jd /abs/path/posting.txt`. The slug comes from the file name; give `--job SLUG` to choose it (lower-case letters, digits and `-`, not `general`). `--jd` over an existing job starts it over; `--job SLUG` alone redrafts it from its saved posting and keeps its keywords.
   - Read `08-ats.tmp/jobs/<slug>/jd.txt`. Write `08-ats.tmp/jobs/<slug>/keywords.json` with the posting's keywords, exactly as it spells them: each must be in the posting. Run `keywords.py <slug>` and handle missing keywords as in step 3.
   - Tailor `resume.json` to the posting: select and order as in step 4, and reword freely into the posting's language. Every technology, keyword, number or scope word a rewrite adds beyond its sources is flagged, and the engineer must accept, revert or edit each flag at checkpoint 4, so prefer what the sources support. Run `diff_claims.py <slug>` to see the flags, and `ats_lint.py <slug>`.
   - Run `ats.py --commit`.
7. To revert or edit a bullet after the commit (checkpoint 4, or the engineer asks): `uv run scripts/ats.py --workspace WS --revise <version>` prints each bullet with its original text (`was:`); change the text in the draft (the original text reverts it) and run `ats.py --commit`, which runs the claim diff again. To drop a job version: `ats.py --remove <slug>`, then `ats.py --commit`. Attestations are checkpoint 4's; never write `decisions/`.
8. Report each version: bullets used and left out, estimated lines against the budget, keyword coverage, each `warning:`, and each job's flags. Say that the engineer accepts, reverts or edits every flag at checkpoint 4, and that render (`/resume-builder:render`) comes next.

Never edit `08-ats/` or `decisions/` by hand, and never weaken or skip a check.

## What the scripts guarantee

- Every fact on a resume is copied exactly from the effective profile (the imported resume with the wizard's answers), dates shortened at most, with no `x-sources`: the source check (`check_sources.py`) passes on every committed resume, as render requires.
- Bullets come from `07-sanitized/bullets.json`, never `06-bullets/`, and keep their IDs as `bullet_id` and their sources. Each sits under the entry for its place: `work_ref` `i` under the job copied from the profile's `work[i]`, a profile-project pointer under the project copied from `projects[i]`. A bullet with no place is left out and reported.
- A skill keyword holding a denied term is left out, and the terms check passes on every resume.
- The general resume says nothing its bullets' sources do not. Each job's `flags.json` records the hash of every bullet and the summary it examined in `checked`, and lists the rewrites that add a claim in `flags`.
- Each version fits its page budget by the estimate, and `report.json` records the length, keyword coverage, the bullets left out and the lint warnings.

## Output

```
08-ats/
  general/        resume.json, keywords.json, report.json
  jobs/<slug>/    jd.txt, resume.json, keywords.json, report.json, flags.json
```

Render prints each `resume.json`. It refuses a job version while a flag is not attested.
