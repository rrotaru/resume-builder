# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "jinja2==3.1.6",
#     "playwright==1.56.0",
#     "pypdf==6.19.0",
#     "python-docx==1.2.0",
# ]
# ///
"""Render the tailored resumes in 08-ats/ to PDF, DOCX and plain text, after every hard check.

Usage:
  uv run render.py --workspace WS [--target general|SLUG]... [--paper letter|a4] [--no-pdf] [--check]
  uv run render.py --install-browser [--with-deps]

Exit codes: 0 rendered (or --check passed); 1 a check failed or there is
nothing to render, and nothing was written; 2 usage error; 3 Chromium is not
installed or did not start, and nothing was written.
"""
from __future__ import annotations

import argparse
import contextlib
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-core" / "scripts"))
from rcore import stages, terms, wsio  # noqa: E402
from rrender import gate, model, outcheck, txt  # noqa: E402

CHECK_FAILED, NO_CHROMIUM = 1, 3
PAGE_WARNING = 2  # resume-ats aims for one or two pages


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workspace", default="resume-workspace", type=Path)
    parser.add_argument("--target", action="append", default=[],
                        help="general or a job slug; repeat for more (default: every tailored resume)")
    parser.add_argument("--paper", choices=("letter", "a4"), default="letter")
    parser.add_argument("--no-pdf", action="store_true", help="write DOCX and TXT only")
    parser.add_argument("--check", action="store_true", help="run the checks and write nothing")
    parser.add_argument("--install-browser", action="store_true",
                        help="install the Chromium build this script's Playwright needs")
    parser.add_argument("--with-deps", action="store_true",
                        help="with --install-browser, also install Linux system libraries")
    return parser.parse_args(argv)


def _install_browser(with_deps: bool) -> int:
    command = [sys.executable, "-m", "playwright", "install", *(["--with-deps"] if with_deps else []),
               "chromium"]
    return subprocess.call(command)


def _hashes(workspace: Path, rels: list[str]) -> dict[str, str | None]:
    return {rel: stages.hash_path(workspace / rel) if (workspace / rel).exists() else None for rel in rels}


def _report(problems: list[gate.Problem]) -> None:
    groups: dict[str, list[gate.Problem]] = {}
    for problem in problems:
        groups.setdefault(problem.group, []).append(problem)
    for group, items in groups.items():
        print(f"[{group}]")
        for problem in items:
            print(problem.line)
            print(f"  fix: {problem.fix}")


def _no_chromium(message: str, installed: bool) -> int:
    if installed:
        print(f"Chromium did not start:\n{message}", file=sys.stderr)
        print("On Linux, install its system libraries with: render.py --install-browser --with-deps",
              file=sys.stderr)
    else:
        print("Chromium is not installed. Install it (about 150 MB, into Playwright's browser cache "
              "outside the workspace) with: render.py --install-browser", file=sys.stderr)
    print("Or render DOCX and TXT only with --no-pdf. Nothing was written.", file=sys.stderr)
    return NO_CHROMIUM


def _write_target(target, doc, folder: Path, chromium, paper: str) -> tuple[dict[str, str], int | None, list[str]]:
    """Write one target's files. Returns (label -> extracted text, page count, problems)."""
    from rrender import docx

    label = f"out/{target.folder}"
    folder.mkdir(parents=True)
    text = txt.render(doc)
    (folder / "resume.txt").write_bytes(text.encode("utf-8"))
    docx.write(doc, folder / "resume.docx")
    texts = {f"{label}/resume.txt": text, f"{label}/resume.docx": docx.text(folder / "resume.docx")}
    if chromium is None:
        return texts, None, []

    from rrender import html, pdf

    raw, blocked = chromium.print_pdf(html.render(doc), paper)
    problems = [f"{label}/resume.pdf: the page requested {url}; requests are never allowed" for url in blocked]
    data, pages = pdf.finish(raw, f"{doc.name} resume", doc.name)
    (folder / "resume.pdf").write_bytes(data)
    texts[f"{label}/resume.pdf"] = pdf.text(folder / "resume.pdf")
    return texts, pages, problems


def _copy_stories(workspace: Path, tmp: Path, checked: bool) -> tuple[bool, str]:
    """Copy the stories only if the gate checked them (they existed when it ran).

    If they changed or vanished since, the input hash check aborts the render.
    """
    if checked and (workspace / gate.STORIES).is_file():
        shutil.copyfile(workspace / gate.STORIES, tmp / "stories.md")
        return True, f"stories: copied {gate.STORIES} to out/stories.md"
    reason = f"{gate.STORIES} not found; /resume-builder:sanitize writes it"
    if (workspace / gate.UNSANITIZED_STORIES).is_file():
        reason += f" ({gate.UNSANITIZED_STORIES} is never copied: it is written before sanitizing)"
    return False, f"stories: not copied, {reason}"


def _render(workspace: Path, targets, rels: list[str], watched: list[str], before: dict, args) -> int:
    documents = {t.name: model.build(wsio.read_json(workspace / t.resume)) for t in targets}
    patterns, _ = terms.load_patterns(workspace)  # the gate has checked terms.json
    with contextlib.ExitStack() as stack:
        chromium = None
        if not args.no_pdf:
            from rrender import pdf
            try:
                chromium = stack.enter_context(pdf.Chromium())
            except pdf.ChromiumMissing as exc:
                return _no_chromium(str(exc), installed=False)
            except pdf.ChromiumFailed as exc:
                return _no_chromium(str(exc), installed=True)

        tmp = stages.begin(workspace, "out")
        try:
            pages, problems, messages = {}, [], []
            for target in targets:
                texts, count, found = _write_target(target, documents[target.name], tmp / target.folder,
                                                    chromium, args.paper)
                problems += found + outcheck.check(documents[target.name], texts, patterns)
                if count is not None:
                    pages[target.name] = count
            copied, message = _copy_stories(workspace, tmp, gate.STORIES in rels)
            messages.append(message)
            if problems:
                for line in problems:
                    print(line)
                    print("  fix: a rendering problem, not a data problem; report it with this output")
                print(f"output check failed: {len(problems)} problem(s); nothing written", file=sys.stderr)
                return CHECK_FAILED
            if _hashes(workspace, watched) != before:
                print("inputs changed during render; run render again. Nothing written.", file=sys.stderr)
                return CHECK_FAILED
            extra = {"targets": [t.name for t in targets], "pdf": chromium is not None,
                     "pages": pages, "stories": copied}
            errors = stages.commit(workspace, "out", rels, extra)
            if errors:
                for line in errors:
                    print(line)
                return CHECK_FAILED
        finally:
            shutil.rmtree(tmp, ignore_errors=True)  # gone after a successful commit

    for target in targets:
        files = ["resume.docx", "resume.txt"]
        if target.name in pages:
            count = pages[target.name]
            files.insert(0, f"resume.pdf ({count} page{'s' if count != 1 else ''})")
            if count > PAGE_WARNING:
                messages.append(f"warning: out/{target.folder}/resume.pdf has {count} pages; "
                                "resume-ats aims for one or two")
        print(f"rendered {target.name}: out/{target.folder}/ {', '.join(files)}")
    for message in messages:
        print(message)
    print("render passed")
    return 0


def main(argv=None) -> int:
    args = _parse(argv)
    if args.install_browser:
        return _install_browser(args.with_deps)
    workspace = args.workspace
    targets, errors = gate.discover(workspace, args.target)
    if errors:
        for line in errors:
            print(line)
        return CHECK_FAILED
    if stages.status(workspace).get("08-ats") == "stale":
        print("warning: 08-ats is stale (its inputs changed since it was built); "
              "the checks still decide what may render", file=sys.stderr)

    rels = gate.inputs(workspace, targets)
    # Also watch the optional files that were absent, so one appearing mid-render aborts it too.
    watched = list(dict.fromkeys([*rels, *gate.SHARED_INPUTS, gate.STORIES]))
    before = _hashes(workspace, watched)
    problems = gate.run(workspace, targets)
    for notice in terms.allowed_notices(workspace):
        print(notice, file=sys.stderr)
    if problems:
        _report(problems)
        print(f"render check failed: {len(problems)} problem(s); nothing written", file=sys.stderr)
        return CHECK_FAILED
    if args.check:
        print("render check passed")
        return 0
    return _render(workspace, targets, rels, watched, before, args)


if __name__ == "__main__":
    sys.exit(main())
