---
name: resume-render
description: Render the tailored resumes in a resume-builder workspace to PDF, DOCX and plain text, after running every hard check (schema, sources, fact fields, confidential terms, job flags). Use when the engineer asks to render, export or produce the final resume files, or after resume-ats has written 08-ats.
---

# resume-render

Follow `../resume-core/SKILL.md` for workspace conventions.

- Resolve `scripts/...` and `../resume-core/...` against this skill's own folder, not against the current directory.
- Run commands from the engineer's project directory, not from the skill folder.
- Always pass `--workspace` explicitly, preferably as an absolute path.

## Steps

1. Run `uv run ../resume-core/scripts/stage.py --workspace WS status`.
   If `08-ats` is `missing`, stop and suggest `/resume-builder:ats`.
   If it is `stale`, tell the engineer and offer to rebuild it first. Rendering a stale stage is allowed, because the checks decide what may render.
2. Run `uv run scripts/render.py --workspace WS`.
   It renders every tailored resume in `08-ats/`: `general` and each job in `08-ats/jobs/`.
   - To render only some, add `--target general` or `--target <slug>` (repeatable). `out/` then holds only those.
   - The paper size is US Letter. If the engineer is outside the US and Canada, ask whether they want A4 and add `--paper a4`.
   - To run the checks without writing anything, add `--check`.
3. If it exits 1, a check failed and nothing was written. `out/` still holds the previous render.
   Show the engineer every problem line with the `fix:` line under it, then stop.
   Never edit `08-ats/`, `decisions/` or any other stage folder to make a check pass, and never skip or weaken a check.
   Render again after the engineer has run the fixes.
4. If it exits 3, Chromium is not installed and nothing was written. Tell the engineer that installing downloads about 150 MB into Playwright's browser cache, outside the workspace, and offer two choices:
   - Install: `uv run scripts/render.py --install-browser`, then render again.
   - Continue without a PDF: add `--no-pdf` to write only the DOCX and TXT files.
   If Chromium is installed but fails to start on Linux, try `--install-browser --with-deps`, which also installs the system libraries (it may ask for an administrator password).
5. Show every `notice:` line the render printed. Each names an allowed term that looks like a denied term. Ask the engineer to confirm that each allowed term is a different word.
6. On success, report the files written, the page count of each PDF, any warning, and whether stories were copied.

## What render checks

`render.py` runs the checks itself, in this order, before it writes anything:

1. **Schema.** Every file it reads is validated (`validate.py`). If anything fails, the other checks do not run.
2. **Name.** Each resume has a `basics.name`.
3. **Sources and facts** (`check_sources.py`). Every bullet and the summary cite sources that resolve. Every other field (name, contact details, employer, title, dates, degree, certificate, skill keywords) is copied from the profile.
4. **Terms** (`check_terms.py`). No denied term appears in a resume or in `07-sanitized/stories.md`.
5. **Flags** (`check_flags.py`). Every job version's rewrites passed the claim diff or were attested.

Checks 2 to 5 all run, so one render reports every problem.
After rendering, it checks that the text of each PDF, DOCX and TXT still holds the name, every heading and every bullet, and contains no denied term.

## Output

```
out/
  general/resume.pdf, resume.docx, resume.txt
  jobs/<slug>/resume.pdf, resume.docx, resume.txt
  stories.md          # copied from 07-sanitized/stories.md when it exists
```

Only these sections render, always in this order: Summary (only when it has sources), Experience, Projects, Skills, Education, Certifications.
Stories are copied from `07-sanitized/stories.md` only, never from `06-bullets/stories.md`, which is written before sanitizing.
