# resume-import: Design

- **Date:** 2026-09-25
- **Status:** Draft, awaiting approval
- **Scope:** The `resume-import` skill: reading the engineer's existing resume (PDF, DOCX, TXT, Markdown or JSON Resume) and writing `03-profile/`. It also covers the check that keeps the profile faithful to the file, and the resume-core changes that check needs. This is follow-up spec 3 of the [architecture spec](2026-09-24-resume-builder-architecture-design.md).

## Goal

Turn the engineer's resume into `03-profile/profile.json`, a JSON Resume document that later stages treat as fact. The render gate copies titles, employers, dates, degrees and skills from this profile and does not question them. The [render spec](2026-09-25-resume-render-design.md#what-the-check-does-not-prove) says so: the fact-field check "proves that a fact came from the profile. It does not prove the profile is right." Import must therefore map the resume faithfully, and a script must be able to show that it did.

## Gaps

1. **Nothing checks the model's reading.** The model maps extracted text into JSON. If it writes `Staff Engineer` for `Senior Engineer`, or moves a date from one job to another, the error becomes a checked fact in every later stage.
2. **`x-sources` in the profile carries no information.** The architecture spec gives each profile entry an `x-sources` array such as `["resume:/work/2"]`. A `resume:` pointer resolves into `03-profile/profile.json`, so each entry points at itself. No check reads it, and it cannot say where in the resume the entry came from.
3. **Entry order has no rule.** Wizard answers in `decisions/profile.json` merge into imported entries by index, and `resume:` pointers address entries by index. If the model sorted jobs by date on one import and kept the file's order on the next, a wizard answer such as `"work": [{}, {"endDate": "2022-12"}]` would move to a different job without anyone noticing.
4. **Where `resume_path` is relative to is not defined.** The fixture's `config.json` has `"resume_path": "old-resume.pdf"`. The same question applies to `reviews_dir`, `local_repos` and `export_path`.

[Faithfulness check](#faithfulness-check) closes gaps 1 and 3, [Line ranges](#line-ranges) closes gap 2, and [Resume path](#resume-path) closes gap 4.

## Decisions

| Topic | Decision |
|---|---|
| Formats | PDF (`pypdf`), DOCX (`python-docx`), TXT and Markdown (UTF-8 or UTF-16 with BOM), and JSON Resume (`.json`). Anything else, such as `.doc`, `.rtf`, `.odt` or `.pages`, is refused with a request to save as one of these. |
| Extracted text | `extract_text.py` writes the plain text to `03-profile/resume.txt` and prints it with line numbers, so the model can cite lines in any harness. The text stays in the stage so anyone can re-run the check later. |
| Link targets | Link targets in the file (PDF link annotations, DOCX hyperlinks) are appended to `resume.txt` under a `Links in the document:` line. A resume often shows `GitHub` and hides the URL in the link, and the URL is part of the file. |
| Mapping | Done by the model for text formats. Done by a script for JSON Resume, and the model does not edit that result. |
| Faithfulness | `check_profile.py` (standard library only) proves that every value in the profile appears in `resume.txt`, inside the lines of the entry it belongs to. It also checks that dates are dates the text states, that an entry left open (no `endDate`) is marked as ongoing in the text, and that entries keep the text's order. For JSON Resume, it proves the profile equals the script's mapping of the file. |
| Line ranges | Each entry of a top-level array records `x-lines: {"first": n, "last": m}` in `resume.txt`. `x-lines` replaces `x-sources` in profile files. |
| Missing values | A value the text does not state is left out. The model never guesses, and the wizard asks for missing fields later. The check therefore never blocks import, because leaving a value out always passes it. |
| Commit | `check_profile.py --commit` runs the check and commits `03-profile` in the same process, as `render.py` does with its gate. The skill never commits `03-profile` any other way. |
| Stage inputs | None. The resume file is outside the workspace, so `stage.py commit` cannot hash it. `03-profile/source.json` records its path and hash instead. |
| Re-import | When a re-import moves an entry that a wizard answer is attached to, `check_profile.py` prints a warning naming both entries. The skill shows it to the engineer. |
| Scanned PDF | Exit code 3 with an explanation. The skill asks for DOCX, TXT or pasted text. No OCR in v1. |

## Skill layout

```
skills/resume-import/
  SKILL.md
  scripts/
    extract_text.py        # CLI: resolve the file, begin 03-profile, extract or load
    check_profile.py       # CLI: faithfulness check, index-shift warnings, commit
    rimport/
      extract.py           # PDF, DOCX, TXT and Markdown text (pypdf and python-docx imported here only)
      jsonresume.py        # JSON Resume loading and cleanup
      dates.py             # dates a text states
      match.py             # whether a value appears in a text
      check.py             # the faithfulness check
      shifts.py            # which wizard answers a re-import moves
skills/resume-core/schemas/
  profile-source.schema.json   # new: 03-profile/source.json
```

`extract_text.py` declares pinned `pypdf==6.19.0` and `python-docx==1.2.0` in its PEP 723 block. These are the versions `render.py` pins. Only `rimport/extract.py` imports them. `check_profile.py` and every other `rimport` module use only the standard library, so the check and its tests run without the dependencies. Both scripts import `rcore` as portability rule 6 allows.

## Command line

```
uv run scripts/extract_text.py --workspace WS [--resume PATH]
uv run scripts/check_profile.py --workspace WS [--commit | --committed]
```

| Script | Exit | Meaning |
|---|---|---|
| `extract_text.py` | 0 | Extracted to `03-profile.tmp/resume.txt`, or loaded into `03-profile.tmp/profile.json` |
| | 1 | Error: no resume path, file missing, unsupported format, unreadable or password-protected file, invalid JSON Resume, or no `config.json` |
| | 2 | Usage error |
| | 3 | No text found (for example a scanned PDF). Nothing is written to `config.json`. |
| `check_profile.py` | 0 | Check passed, and with `--commit` the stage is committed |
| | 1 | The check or the commit failed. Nothing committed. |
| | 2 | Usage error |

`check_profile.py` checks `03-profile.tmp/` by default and `03-profile/` with `--committed`, which is for tests and for re-checking an existing import.

## Resume path

- `--resume PATH` is resolved against the current directory. After a successful extraction, `extract_text.py` stores the absolute path in `config.json` `resume_path`, and says so. On exit 1 or 3 it leaves `config.json` unchanged.
- Without `--resume`, the path comes from `config.json` `resume_path`. If that is null, the script exits 1 with `no resume file: pass --resume PATH`, and the skill asks the engineer.
- **Relative paths in `config.json` resolve against the workspace folder**, not against the current directory, so the meaning of a path does not depend on where a command runs. This rule covers every path in `config.json` (`resume_path`, `reviews_dir`, `local_repos`, `export_path`). Scripts that write these paths write them as absolute paths.

## Pipeline

### extract_text.py

1. Resolve the path, read the file's bytes once, and hash them. Parsing uses those bytes, so the hash is the hash of what was read.
2. Choose the format by extension: `.pdf`, `.docx`, `.txt`, `.md` or `.markdown`, `.json`. A PDF must start with `%PDF-` and a DOCX with `PK`. A mismatch is an error, not a guess.
3. `stages.begin(ws, "03-profile")`.
4. For a text format, extract the text (see [Extraction](#extraction)), write `resume.txt`, and write `source.json`. Then print a one-line summary and the numbered text.
5. For JSON Resume, load it (see [JSON Resume](#json-resume)), write `profile.json` and `source.json`, and print a summary with each dropped item.
6. If `03-profile/source.json` exists and names the same path and hash, print `note: <path> is unchanged since the last import`. The skill asks whether to re-import.
7. On success with `--resume`, update `config.json`.

### check_profile.py

1. Read `source.json`, `profile.json` and, for text formats, `resume.txt` from the folder being checked. Validate `profile.json` and `source.json` against their schemas. If validation fails, stop and report only that.
2. Run the [faithfulness check](#faithfulness-check). On any problem, print every problem line and one `fix:` line, and exit 1.
3. With `--commit`: print the [re-import warnings](#re-import), then `stages.commit(ws, "03-profile", [])`, then print the sections and entry counts.

### `03-profile/` contents

| File | Written by | Schema |
|---|---|---|
| `profile.json` | the model (text formats) or `extract_text.py` (JSON Resume) | `resume.schema.json` (open) |
| `resume.txt` | `extract_text.py`, text formats only | none (text) |
| `source.json` | `extract_text.py` | `profile-source.schema.json` (new) |
| `_stage.json` | `stage.py` | `stage.schema.json` |

`source.json`:

```json
{"path": "/home/jordan/resume-workspace/old-resume.pdf", "format": "pdf",
 "sha256": "sha256:…", "text_sha256": "sha256:…"}
```

`format` is `pdf | docx | txt | md | json`. `sha256` is the hash of the source file's bytes. `text_sha256` is the hash of `resume.txt`, or null for JSON Resume. The object is closed.

The stage records no inputs, so `stage.py status` always reports `03-profile` as fresh once it exists. Downstream stages record `03-profile/profile.json`, so a re-import still makes them stale. A changed resume file shows up as a different `sha256` in `source.json`. resume-build (roadmap piece 9) compares that hash and `config.json` `resume_path` with the file before it offers to reuse `03-profile`.

## Extraction

`rimport/extract.py` returns the text, the link targets and the page count (PDF only).

- **PDF:** `pypdf.PdfReader` with plain text extraction, page by page, with pages joined by a blank line. An encrypted file is decrypted with an empty password (many PDFs are "encrypted" only to restrict printing). If that fails, the error is `<path> is password-protected; save an unprotected copy`. Link targets are the `/URI` of each `/Link` annotation's action.
- **DOCX:** every `w:p` in document order: headers of the first section first (contact details often live there), then the body including table cells and text boxes, then footers. A paragraph's text is its `w:t` runs, with `w:tab` as a space and `w:br` as a line break, excluding text in nested paragraphs (text boxes are visited separately), text hidden with `w:vanish`, and `mc:Fallback` copies of text boxes. Link targets are the external relationships of `w:hyperlink` elements.
- **TXT and Markdown:** decoded as UTF-8 (a UTF-8 BOM is dropped) or as UTF-16 when it starts with a UTF-16 BOM. Anything else fails with `<path> is not UTF-8 text; save it as UTF-8`. Markdown is kept as written, and the model strips the markup when mapping.

Then the text is normalized so that `str.splitlines()` and a plain line count agree, because the model cites lines by number:

- `\r\n`, `\r`, and every other character `str.splitlines()` breaks on (`\v`, `\f`, `\x1c` to `\x1e`, `\x85`, U+2028, U+2029) become `\n`. Tabs become spaces. Other control characters are removed.
- Trailing spaces are removed. Runs of blank lines become one blank line. Leading and trailing blank lines are removed.
- If there are link targets (`http`, `https` or `mailto`, deduplicated, in document order), a blank line, the line `Links in the document:` and one target per line are appended.
- The file ends with a newline.

If the text before the links holds fewer than 50 letters, the file has no usable text, and the script exits 3. For a PDF the message is `no text found in <path> (<n> pages). It looks like a scanned PDF, and OCR is not supported. Provide a DOCX or TXT version, or paste the text.`

## JSON Resume

JSON Resume is mapped by a script, so the result is exact and repeatable:

- The file must be a JSON object (UTF-8, BOM allowed).
- At the top level, `$schema` and `meta` are dropped: they describe the file, not the engineer.
- Every key starting with `x-`, at any depth, is dropped, so a file cannot bring its own `x-lines` or `x-highlights`. Each one is reported.
- Keys whose value is `""` or `null` are dropped (JSON Resume templates use them for "no value"), and the count is reported.
- Date fields (`startDate`, `endDate`, `date`, `releaseDate`) must be `YYYY`, `YYYY-MM` or `YYYY-MM-DD` naming a real date. A full timestamp (`2019-06-01T00:00:00Z`) is cut to its date. Anything else is an error naming the pointer, such as `/work/1/endDate: 'June 2019' is not YYYY, YYYY-MM or YYYY-MM-DD; fix it in the file`. A date is never dropped, because a job whose `endDate` is dropped would render as current.
- Order, other sections and unknown fields are kept as they are. The result must match `resume.schema.json`.

A JSON Resume profile has no `resume.txt` and no `x-lines`. `check_profile.py` maps the file again from `source.json` `path`. It fails if the file's hash differs from `source.json` (`<path> changed since extract_text.py ran; run it again`) or if `profile.json` differs from the mapping (`profile.json differs from the JSON Resume mapping; do not edit it, run extract_text.py again`).

## Line ranges

Every object in a top-level array (`work`, `volunteer`, `education`, `awards`, `certificates`, `publications`, `skills`, `languages`, `interests`, `references`, `projects`) carries `x-lines`: `{"first": 12, "last": 15}`. The numbers are 1-based and inclusive, and they count lines in `resume.txt`. They mark the lines the entry was read from, including its heading line and its bullets. `basics` has no `x-lines` and is checked against the whole text.

`x-lines` is metadata. It is never rendered, and the tailored-resume schema does not allow it. Sanitize apply copies it into `07-sanitized/profile.json` unchanged. `resume.schema.json` gains `x-lines` on those entries and loses `x-sources`, which nothing wrote or read.

## Faithfulness check

### Structure (text formats)

- `resume.txt`'s hash must equal `source.json` `text_sha256`, so the text cannot be edited to fit the profile: `resume.txt was changed after extraction; run extract_text.py again`.
- The top level holds only `basics` and the JSON Resume sections listed above.
- Each object holds only JSON Resume fields for its section (for example `work`: `name`, `position`, `url`, `location`, `description`, `startDate`, `endDate`, `summary`, `highlights`, plus `x-lines`). An unknown field is an error that lists the allowed fields, so `company` instead of `name` is caught before an employer silently goes missing.
- Every value is a non-empty string, or an array or object of them. `null` is an error: leave the field out instead.
- Every entry has `x-lines` with `1 <= first <= last <= <line count>`.
- **Order:** within each section, `first` never decreases from one entry to the next. The profile keeps the order of the text.

### Values

Each string in the profile, other than `x-lines`, must appear in its *scope*. The scope of a value inside an entry is the entry's lines. The scope of a `basics` value, and of any URL, is the whole text. URLs can sit in the appended links block, away from their entry.

Text and value are compared after the same normalization: Unicode NFKC, format characters (category `Cf`) removed, dashes (category `Pd` and U+2212) read as `-`, curly quotes read as straight ones, and case folded. Then:

| Field | Appears when |
|---|---|
| Any text field | The value's characters, with whitespace ignored, occur in order in the scope with nothing between them but whitespace. The match must start and end at a word boundary (no letter or digit just outside it) wherever the value starts or ends with a letter or digit. So `Senior Software Engineer` matches `Senior Software\nEngineer` and `SeniorSoftware Engineer`, `Go` does not match inside `Google`, and a highlight must be copied word for word. |
| `url`, `image` | The same, after `http://`, `https://`, `mailto:`, a leading `www.` and a trailing `/` are removed from the value. `https://github.com/jrivera` matches `github.com/jrivera`. |
| `phone` | The value's digits occur in order, separated only by spaces, `(`, `)`, `.`, `-`, `+` or `/`, with no digit just before or after them. `(555) 123-4567` matches `555.123.4567`. |
| `startDate`, `endDate`, `date`, `releaseDate` | The value is a real date, and the scope [states it](#dates-the-text-states) at that precision or finer. |

Only letter case may differ from the text. That allows `JORDAN RIVERA` to become `Jordan Rivera`. Everything else, such as `Sr.` for `Senior`, `BS` for `B.S.`, `US` added to `Denver, CO`, or a guessed URL, fails. The engineer can make those changes through the wizard.

### Dates the text states

`rimport/dates.py` lists the dates a text states, each at the precision written (English month names only, as the architecture spec keeps v1 English-only):

| Written | Yields |
|---|---|
| `2019` (a 4-digit year from 1900 to 2099 with no digit next to it) | `2019` |
| `Jun 2019`, `June 2019`, `Jun. 2019`, `June, 2019`, `Sept 2019` | `2019-06`, `2019` |
| `Jun '19`, `Jun ’19` | `2019-06`, `2019`, `1919-06`, `1919` (both centuries, so the rule does not depend on today's date) |
| `06/2019`, `6/2019`, `06-2019`, `06.2019`, `2019-06`, `2019/06` | `2019-06`, `2019` |
| `06/19` | `2019-06`, `1919-06` and their years |
| `2019-06-03`, `2019/06/03`, `June 3, 2019`, `3 June 2019` | `2019-06-03`, `2019-06`, `2019` |
| `03/06/2019`, `03.06.2019` | both readings that are real dates (`2019-03-06` and `2019-06-03`) and their months and years |

Seasons and quarters (`Summer 2019`, `Q3 2019`) yield only the year. A profile date passes when it is in the set for its scope. So `June 2019` supports `2019-06` and `2019` but not `2019-06-01`, and a date from another entry's lines does not count. Where an entry has both, `startDate` may not be after `endDate`, compared at the precision they share.

### Open entries

A `work`, `volunteer`, `education` or `projects` entry with a `startDate` and no `endDate` renders as ongoing ("Present"). The check requires the entry's lines to say so with one of `present`, `current`, `currently`, `now`, `today`, `ongoing`, `to date` or `since`. Otherwise it reports `/work/1: no endDate, but lines 10-12 do not say it is ongoing`. The fix is the end date the text gives. If the text gives only one date for the entry (`2019`), the model sets `startDate` and `endDate` to it.

### Error lines

Every line names the file and a JSON Pointer:

```
03-profile.tmp/profile.json: /work/0/position: 'Staff Engineer' is not in resume.txt lines 7-9
03-profile.tmp/profile.json: /work/1/startDate: '2019-05' is not a date resume.txt lines 11-13 give (they give 2019-06, 2022-12)
03-profile.tmp/profile.json: /work/0: no endDate, but resume.txt lines 7-9 do not say it is ongoing
03-profile.tmp/profile.json: /work/1: x-lines 3-4 come before /work/0 (lines 7-9); keep entries in the order of resume.txt
03-profile.tmp/profile.json: /work/0/company: not a work field (allowed: name, position, url, location, description, startDate, endDate, summary, highlights, x-lines)
03-profile.tmp/profile.json: /basics/email: 'jordan@example.com' is not in resume.txt
  fix: copy each value exactly as resume.txt writes it (only letter case may change), or leave it out for the wizard to ask. Never edit resume.txt.
```

Long values are shortened to 60 characters in messages.

### What the check does not prove

- **The right field within an entry.** A value copied from the right lines into the wrong field, such as the employer written as the title, passes. The engineer reviews the profile summary the skill prints.
- **Completeness.** A dropped job, bullet or skill is not detected. The skill's summary lists the entries per section so the engineer can spot a gap.
- **Visibility.** Text that a PDF hides (for example white keyword text) extracts like visible text. DOCX hidden text is skipped.
- **Reading order.** In a two-column PDF, text extraction can interleave the columns, so an entry's lines may include some from the other column. The value rules still hold. Only the scope is wider.
- **Ongoing words** anywhere in an entry's lines satisfy the open-entry rule, even inside a bullet.

## Re-import

Wizard answers attach to imported entries by index. Before committing, `check_profile.py --commit` compares the new profile with the committed `03-profile/profile.json` (an empty profile if there is none). It looks at each index *i* of a section where `decisions/profile.json` has a non-empty object. If the entry at *i* is not the same entry as before, it prints a warning:

```
warning: decisions/profile.json /work/1 was answered for 'Software Engineer, Tailspin Toys'; after this import /work/1 is 'Engineer, Contoso'. Review it with /resume-builder:wizard.
warning: decisions/profile.json /certificates/0 added a certificates entry; after this import it merges into 'AWS Certified Developer'. Review it with /resume-builder:wizard.
```

"The same entry" compares identity fields: `work` compares `name` and `position`, `volunteer` compares `organization` and `position`, `education` compares `institution`, `studyType` and `area`, `certificates` compares `name` and `issuer`, and each other section compares `name` (`title` for `awards`, `language` for `languages`). Warnings never block the commit. Only the wizard writes `decisions/`, so import reports the shift and does not repair it. The skill shows every warning to the engineer.

## SKILL.md

1. If `03-profile` exists, tell the engineer that importing replaces it.
2. Find the resume: `config.json` `resume_path`, or ask the engineer for a PDF, DOCX, TXT, Markdown or JSON Resume file and pass it with `--resume`.
3. Run `extract_text.py`.
   - On exit 3, explain that the file has no text layer and that OCR is not supported. Ask for a DOCX or TXT version, or for the text pasted into the conversation. Save pasted text as UTF-8 to `pasted-resume.txt` in the workspace, then run again with `--resume` on that file.
   - On a `note:` that the file is unchanged, ask whether to import it again. If not, stop.
   - For JSON Resume, go to step 5.
4. Map the numbered text into `03-profile.tmp/profile.json`:
   - Use JSON Resume fields: `basics` (`name`, `label`, `email`, `phone`, `url`, `summary`, `location`, `profiles`), then the sections the resume has. Each job title is its own `work` entry, even at the same employer.
   - Copy every value exactly as written. Only letter case may change. Do not reword, abbreviate, expand, translate or correct anything.
   - Write dates as `YYYY`, `YYYY-MM` or `YYYY-MM-DD`, at the precision the text gives and no finer. `Present` or `Current` means no `endDate`. A season or quarter means the year only.
   - Leave out anything the text does not state, such as a country code, a URL scheme the link targets do not show, or a skill group name that is not written. The wizard asks for missing fields later.
   - Keep entries in the order of the text, and give each entry `x-lines` covering its lines.
   - Copy bullets into `highlights` word for word, without the bullet character.
   - Never edit `resume.txt`.
5. Run `check_profile.py --commit`. On exit 1, fix every named field by copying it exactly or leaving it out, then run it again. Never edit `resume.txt` and never weaken the check.
6. Show every `warning:` line and explain that the named wizard answers now apply to different entries.
7. Report the sections and entries imported, and the basic fields left out (for example no email or location). The wizard will ask for these.

## Changes to resume-core, fixtures and the architecture spec

1. `resume.schema.json`: adds `x-lines` to every entry type and lists the other JSON Resume sections as arrays of objects. Removes `x-sources` from the entry and top-level definitions.
2. New `profile-source.schema.json`, mapped in `FILE_SCHEMAS` as `03-profile/source.json`.
3. Fixture: `03-profile/resume.txt` (the made-up engineer's old resume as extracted text) and `03-profile/source.json`. `03-profile/profile.json` and `07-sanitized/profile.json` replace `x-sources` with `x-lines`. The fixture profile passes `check_profile.py --committed`.
4. resume-core `SKILL.md`, "The profile": `03-profile/profile.json` is a faithful reading of `03-profile/resume.txt`, each entry carries `x-lines`, and entries keep the resume's order.
5. The architecture spec:
   - The workspace tree lists `03-profile/` as `profile.json`, `resume.txt` and `source.json`.
   - "Profile" in Data contracts describes `x-lines` instead of `x-sources`.
   - The resume-import section points to this spec.
   - Relative paths in `config.json` resolve against the workspace folder.
6. The test command, CI and README add `--with-requirements skills/resume-import/scripts/extract_text.py`. `pytest.ini` adds `skills/resume-import/scripts` to `pythonpath`.

## Error handling

| Case | Behavior |
|---|---|
| No `resume_path` and no `--resume` | Exit 1. The skill asks for the file. |
| File missing, unsupported extension, or content that does not match the extension | Exit 1 naming the file and the formats accepted. |
| Password-protected PDF | Exit 1. Ask for an unprotected copy. |
| No text (scanned PDF, empty file) | Exit 3. Ask for DOCX, TXT or pasted text. `config.json` unchanged. |
| Invalid JSON Resume | Exit 1 with each problem by pointer. Nothing to commit. |
| Faithfulness check fails | Exit 1, nothing committed, one line per problem and a `fix:` line. The previous `03-profile/` stays. |
| `resume.txt` or the JSON file changed after extraction | Exit 1. Run `extract_text.py` again. |
| Re-import moves an answered entry | Warning. The commit goes ahead. The engineer reviews it with the wizard. |

## Testing

- **Dates:** every row of the table above, including invalid dates (`2019-02-30`), numbers that are not years, a year range `2019-2022` (two years, not `2019-20`), and both readings of `03/06/2019`.
- **Matching:** case, whitespace inside and between words, word boundaries (`Go` against `Google`, `C` against `C++`), dashes and curly quotes, URL forms, phone formats, and a highlight split across lines.
- **Check:** the fixture profile passes. Each rule fails on its own with the expected line: an invented title, a degree that is not written, a date finer than the text, a date taken from another entry, `startDate` after `endDate`, a missing ongoing word, missing or out-of-range `x-lines`, entries out of order, an unknown section, an unknown field, a `null`, and an edited `resume.txt`.
- **JSON Resume:** `$schema`, `meta` and `x-` keys dropped and reported, empty values dropped, a timestamp cut to its date, a non-ISO date rejected, a non-object rejected, and an edited profile or a changed file rejected at commit.
- **Extraction** (needs the dependencies, skipped locally without them and failing in CI, like the render tests): a PDF built in the test with text and a link annotation, a PDF with only an empty page (exit 3), an encrypted PDF with and without an empty password, a DOCX with a header, a table, a text box with its fallback, hidden text and a hyperlink, TXT in UTF-8, UTF-8 with BOM and UTF-16, a non-UTF-8 TXT, Markdown, an unsupported extension, a `.pdf` that is not a PDF, and line normalization (`\f`, U+2028, control characters, blank-line runs).
- **CLI:** `--resume` updates `config.json` only on success, a relative `resume_path` resolves against the workspace, the unchanged-file note, `--commit` writes `03-profile/` with `source.json` and leaves the previous stage on failure, and the re-import warnings.
- **Contract:** the fixture profile still validates, and the fixture's tailored resumes still pass the fact-field check against the effective profile.

## Out of scope for v1

- OCR, `.doc`, `.rtf`, `.odt`, `.pages` and LinkedIn exports.
- Non-English month names and resumes.
- Detecting hidden text in PDFs.
- Repairing wizard answers after a re-import. The wizard owns `decisions/`.
