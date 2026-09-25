---
name: resume-import
description: Import the engineer's existing resume (PDF, DOCX, TXT, Markdown or JSON Resume) into a resume-builder workspace as 03-profile/profile.json, a JSON Resume profile that later stages treat as fact. A script checks that every value in it appears in the resume. Use when the engineer asks to import their resume, or when resume-build reaches the import step.
---

# resume-import

Follow `../resume-core/SKILL.md` for workspace conventions.

- Resolve `scripts/...` and `../resume-core/...` against this skill's own folder, not against the current directory.
- Run commands from the engineer's project directory, not from the skill folder.
- Always pass `--workspace` explicitly, preferably as an absolute path.

Later stages copy titles, employers, dates, degrees and skills from this profile without questioning them. Map the resume faithfully: a value the resume does not state stays out of the profile, and the wizard asks for it later.

## Steps

1. If `03-profile` exists (`uv run ../resume-core/scripts/stage.py --workspace WS status`), tell the engineer that importing replaces it.
2. Find the resume. `config.json` `resume_path` names it (a relative path there is relative to the workspace). If it is null, or the engineer wants a different file, ask for a PDF, DOCX, TXT, Markdown or JSON Resume file and pass it with `--resume PATH`.
3. Run `uv run scripts/extract_text.py --workspace WS [--resume PATH]`.
   - **Exit 3:** the file has no text layer (for example a scanned PDF). Explain that OCR is not supported, and ask for a DOCX or TXT version or for the text pasted into the conversation. Save pasted text as UTF-8 to `pasted-resume.txt` in the workspace folder, then run again with `--resume` on that file.
   - **Exit 1:** show the error and stop. A `.doc`, `.rtf`, `.odt` or `.pages` file must be saved as PDF, DOCX or TXT first. A password-protected PDF needs an unprotected copy.
   - **`note: ... unchanged since the last import`:** ask whether to import it again. If not, stop.
   - **JSON Resume** (`loaded JSON Resume ...`): the script has written `profile.json`. Do not edit it. Go to step 5.
4. Map the numbered text the script printed into `03-profile.tmp/profile.json` (JSON Resume). The text is also in `03-profile.tmp/resume.txt`.
   - `basics` holds `name`, `label` (the headline under the name), `email`, `phone`, `url`, `summary`, `location` (`address`, `postalCode`, `city`, `countryCode`, `region`) and `profiles` (`network`, `username`, `url`).
   - Then add each section the resume has, with JSON Resume field names:
     - `work`: `name` (employer), `position`, `url`, `location`, `description`, `startDate`, `endDate`, `summary`, `highlights`
     - `volunteer`: `organization`, `position`, `url`, `startDate`, `endDate`, `summary`, `highlights`
     - `education`: `institution`, `url`, `area`, `studyType`, `startDate`, `endDate`, `score`, `courses`
     - `awards`: `title`, `date`, `awarder`, `summary`
     - `certificates`: `name`, `date`, `issuer`, `url`
     - `publications`: `name`, `publisher`, `releaseDate`, `url`, `summary`
     - `skills`: `name`, `level`, `keywords`
     - `languages`: `language`, `fluency`
     - `interests`: `name`, `keywords`
     - `references`: `name`, `reference`
     - `projects`: `name`, `description`, `highlights`, `keywords`, `startDate`, `endDate`, `url`, `roles`, `entity`, `type`
   - Each job title is its own `work` entry, even when two titles share an employer.
   - **Copy every value exactly as written.** Only letter case may change (for example a name set in capitals). Do not reword, abbreviate, expand, translate or correct anything. `Sr.` stays `Sr.`, and `B.S.` stays `B.S.`.
   - Copy each bullet into `highlights` word for word, without the bullet character.
   - Write dates as `YYYY`, `YYYY-MM` or `YYYY-MM-DD`, at the precision the text gives and never finer: `Jun 2019` is `2019-06`, and `2019` stays `2019`. `Present`, `Current` or `Now` means no `endDate`. A season or quarter (`Summer 2019`) means the year only. If an entry shows one date only (`2019`), set `startDate` and `endDate` to it.
   - Leave out anything the text does not state: a country code, a URL scheme or address the text and its links block do not show, a skill group name that is not written (a flat skills list is one `skills` entry with only `keywords`). Leave out empty values too, never write `null` or `""`.
   - URLs may come from the `Links in the document:` block at the end. Those are the link targets in the file.
   - Keep entries in the order of the text. Give every entry of every section `x-lines`: `{"first": <line>, "last": <line>}`, the numbered lines it was read from, including its heading line and bullets.
   - Never edit `resume.txt`.
5. Run `uv run scripts/check_profile.py --workspace WS --commit`.
   On exit 1 nothing was committed. Fix every named field by copying it exactly as `resume.txt` writes it, or by leaving it out, then run it again. Never edit `resume.txt`, and never weaken or skip the check.
6. Show every `warning:` line. Each one names a wizard answer in `decisions/profile.json` that now applies to a different entry, because answers attach to entries by position. Suggest reviewing them with `/resume-builder:wizard`. Never edit `decisions/` yourself.
7. Report the sections and entries imported (the `committed 03-profile:` line), and the basic fields the resume did not state, such as email, phone or location. The wizard asks for those.

## What the check proves

`check_profile.py` passes a text import only when:

- every value appears in the entry's `x-lines` (URLs and `basics` values anywhere in `resume.txt`), comparing without regard to case and to line breaks or spacing, with dashes and curly quotes read as plain ones;
- every date is a real date that those lines state at that precision or finer, and `startDate` is not after `endDate`;
- a `work`, `volunteer`, `education` or `projects` entry without an `endDate` has lines that say it is ongoing (`present`, `current`, `now`, and similar);
- entries keep the order of `resume.txt`, and every section and field is a JSON Resume one;
- `resume.txt` is unchanged since `extract_text.py` wrote it.

A JSON Resume import passes when `profile.json` equals the script's mapping of the unchanged file.

It does not prove that a value sits in the right field, or that nothing was left out. The report in step 7 lets the engineer spot a missing job.

## Output

```
03-profile/
  profile.json    # JSON Resume; each entry has x-lines into resume.txt
  resume.txt      # the extracted text (not for JSON Resume imports)
  source.json     # path, format and hashes of the imported file
```
