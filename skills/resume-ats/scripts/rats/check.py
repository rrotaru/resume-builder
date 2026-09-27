"""The commit's checks on the draft: its files, keywords.json, and each bullet's place.

The source, fact-field and terms checks are resume-core's (rcore.sources,
rcore.terms), run on the written files as render runs them. The claim diff is
claims.py and the lint lint.py.
"""
from __future__ import annotations

from pathlib import Path

from rcore import schema, wsio
from rcore.profile import describe

from . import lint, match
from .common import FLAGS, GENERAL, JD, KEYWORDS, REPORT, RESUME, TMP, AtsError, Version, draft_versions, slug_error
from .common import version as named
from .material import SECTIONS, Material

ALLOWED = {False: {RESUME, KEYWORDS, REPORT}, True: {JD, RESUME, KEYWORDS, REPORT, FLAGS}}


def files(workspace: Path) -> tuple[list[Version], list[str]]:
    """The versions in the draft, and a line for each file or folder ats does not write."""
    root = Path(workspace) / TMP
    versions, problems = [], []
    for path in sorted(root.iterdir()):
        if path.name == GENERAL and path.is_dir():
            versions.append(Version(GENERAL))
        elif path.name == "jobs" and path.is_dir():
            for job in sorted(path.iterdir()):
                error = slug_error(job.name) if job.is_dir() else None
                if not job.is_dir():
                    problems.append(f"{TMP}/jobs/{job.name}: not a job folder; remove it")
                elif error:
                    problems.append(f"{TMP}/jobs/{job.name}: {error}")
                else:
                    versions.append(Version(job.name))
        else:
            problems.append(f"{TMP}/{path.name}: not a file resume-ats writes; remove it")
    for version in versions:
        folder = root / version.folder
        for path in sorted(folder.iterdir()):
            if path.name not in ALLOWED[version.is_job] or not path.is_file():
                problems.append(f"{version.draft(path.name)}: not a file resume-ats writes; remove it")
        for name in (RESUME, KEYWORDS) + ((JD,) if version.is_job else ()):
            if not (folder / name).is_file():
                problems.append(f"{version.draft(name)}: not found" + _missing_hint(name, version))
    return versions, problems


def _missing_hint(name: str, version: Version) -> str:
    if name == KEYWORDS:
        what = "the posting's keywords" if version.is_job else "the target role's keywords"
        return f"; write {what} (see SKILL.md)"
    if name == JD:
        return f"; draft the job again with ats.py --jd FILE --job {version.name}"
    return f"; draft it again with ats.py{' --job ' + version.name if version.is_job else ''}"


def posting(workspace: Path, version: Version) -> tuple[str | None, str | None]:
    """(the posting's text, None), or (None, why it cannot be used)."""
    text, error = wsio.load(workspace, version.draft(JD), "text")
    if error:
        return None, error
    if not text.strip():
        return None, f"{version.draft(JD)}: the posting is empty"
    return text, None


def keywords(workspace: Path, version: Version, target_role: str) -> tuple[list[str], list[str]]:
    """(keywords, problems) for a version's keywords.json."""
    rel = version.draft(KEYWORDS)
    data, error = wsio.load(workspace, rel)
    if error:
        return [], [error]
    problems = [f"{rel}: {p}" for p in schema.validate(data, schema.load_schema("ats-keywords"))]
    if problems:
        return [], problems
    seen: dict[str, str] = {}
    for keyword in data:
        if match.key(keyword) in seen:
            problems.append(f"{rel}: {keyword!r} is listed twice (as {seen[match.key(keyword)]!r})")
        seen.setdefault(match.key(keyword), keyword)
    if version.is_job:
        if not data:
            problems.append(f"{rel}: no keywords; list the posting's keywords as it spells them")
        text, error = posting(workspace, version)
        if text is not None:
            text = match.normalize(text)
            problems += [f"{rel}: {k!r} is not in the posting ({version.draft(JD)}); list only the posting's "
                         "keywords, as it spells them" for k in data if not match.mentions(text, k)]
    elif not data and target_role:
        problems.append(f"{rel}: no keywords; list the keywords an ATS would match for the target role "
                        f"{target_role!r}")
    return data, problems


def placement(resume: dict, material: Material, rel: str) -> list[str]:
    """Each x-highlights item: a known bullet, used once, with its sources, under the entry for its place."""
    problems = []
    for section in SECTIONS:
        for i, entry in enumerate(resume.get(section, [])):
            copied = lint.copies(entry, material.entries(section))
            for j, highlight in enumerate(entry.get("x-highlights", [])):
                where = f"{rel}: /{section}/{i}/x-highlights/{j}"
                bullet_id = highlight["bullet_id"]
                bullet = material.by_id.get(bullet_id)
                if bullet is None:
                    problems.append(f"{where}: {bullet_id} is not a bullet of 07-sanitized/bullets.json; use only "
                                    "the drafted bullets")
                    continue
                if sorted(set(highlight["sources"])) != sorted(set(bullet["sources"])) \
                        or len(highlight["sources"]) != len(set(highlight["sources"])):
                    problems.append(f"{where}: sources must be {bullet_id}'s sources {bullet['sources']}")
                place = material.place(bullet)
                if place is None:
                    problems.append(f"{where}: {bullet_id} has no place ({material.homeless[bullet_id]}); leave it "
                                    "out")
                elif place[0] != section or place[1] not in copied:
                    target = material.entries(place[0])[place[1]]
                    here = (f"this entry copies /{section}/{copied[0]}" if copied
                            else "this entry copies no entry of the profile")
                    problems.append(f"{where}: {bullet_id} goes under /{place[0]}/{place[1]} "
                                    f"({describe(place[0], target)}); {here}")
    return problems


def resume(workspace: Path, version: Version) -> tuple[dict | None, list[str]]:
    """(the draft resume, []) when it matches tailored-resume.schema.json, else (None, problems)."""
    rel = version.draft(RESUME)
    data, error = wsio.load(workspace, rel)
    if error:
        return None, [error]
    problems = [f"{rel}: {p}" for p in schema.validate(data, schema.load_schema("tailored-resume"))]
    return (None, problems) if problems else (data, [])


def chosen(workspace: Path, names: list[str]) -> list[Version]:
    """The draft's versions a checker reads: those named, or all. Raises AtsError."""
    if not (Path(workspace) / TMP).is_dir():
        raise AtsError(f"{TMP}/ not found: there is no draft; draft a version with ats.py first (the committed "
                       "results are each version's report.json and flags.json)")
    present = draft_versions(workspace)
    if not names:
        if not present:
            raise AtsError(f"{TMP}/ holds no version; draft one with ats.py")
        return present
    wanted = [named(n) for n in dict.fromkeys(names)]
    missing = [v.name for v in wanted if v not in present]
    if missing:
        raise AtsError([f"{name}: not in the draft ({TMP}/)" for name in missing])
    return wanted
