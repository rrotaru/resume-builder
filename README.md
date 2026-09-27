# resume-builder
Discover your most impactful work and prove the value you have delivered.

A Claude Code plugin of portable agent skills that builds an evidence-backed engineering resume.
Design: [architecture spec](docs/superpowers/specs/2026-09-24-resume-builder-architecture-design.md).
Progress and what to build next: [roadmap](docs/ROADMAP.md).

## Install

The scripts need [uv](https://docs.astral.sh/uv/), which supplies Python 3.10 or later itself (`/resume-builder:init` checks for it and shows how to install it). In Claude Code, add this repository as a plugin marketplace and install the plugin:

```
/plugin marketplace add rrotaru/resume-builder
/plugin install resume-builder@resume-builder
```

From a shell, the same is `claude plugin marketplace add rrotaru/resume-builder`, then `claude plugin install resume-builder@resume-builder`. The plugin has no pinned version, so an update follows the repository's latest commit. Other harnesses that read [Agent Skills](https://agentskills.io) can load the folders in `skills/`, copied as a set, since each uses `../resume-core/`.

## Use

`/resume-builder:build` runs the whole workflow in `./resume-workspace` (or `--workspace PATH`), one checkpoint at a time, and continues an interrupted run where it stopped. Give it job postings to tailor for with `--jd FILE`. Each step also has its own command:

| Command | What it does |
|---|---|
| `/resume-builder:build [--workspace PATH] [--jd FILE ...]` | The whole run: shows where it stands, reuses fresh stages, runs checkpoints 1 to 4 and renders |
| `/resume-builder:init` | Creates the workspace, `config.json` and the decision files |
| `/resume-builder:collect` | Checkpoint 1: confirms the sources and the data notice, then collects pull requests, reviews, tickets, commits and performance reviews |
| `/resume-builder:import` | Reads your existing resume (PDF, DOCX, TXT, Markdown or JSON Resume) into the profile |
| `/resume-builder:analyze` | Checkpoint 2: finds your projects and their role, scope and rank, for you to review |
| `/resume-builder:wizard` | Checkpoint 3: asks for metrics, missing profile details and decisions on confidential terms |
| `/resume-builder:write` | Writes the bullets and STAR stories, each citing its sources |
| `/resume-builder:sanitize [scan\|apply]` | Finds confidential terms, or replaces the denied ones |
| `/resume-builder:ats [--jd FILE]` | Builds the general resume, or a version tailored to a posting |
| `/resume-builder:render` | Checks every resume and renders PDF, DOCX and plain text to `out/` |

Everything stays in the workspace folder. Your choices are kept in its `decisions/` folder, so a later run rebuilds the resume from new evidence without asking again.

## Development

Requires [uv](https://docs.astral.sh/uv/). Scripts support Python 3.10 and later.

```bash
uv run skills/resume-render/scripts/render.py --install-browser   # once: Chromium for the PDF tests
uv run --with pytest --with-requirements skills/resume-render/scripts/render.py \
  --with-requirements skills/resume-import/scripts/extract_text.py pytest
```

The second command takes the dependencies from the inline metadata of `render.py` and `extract_text.py` (collect's `ingest_reviews.py` pins the same versions). Without them (plain `uv run --with pytest pytest`) the render end-to-end tests, the PDF and DOCX import and review tests and resume-ats's length check against real renders are skipped, and tests that need Chromium skip when it is not installed. In CI (`CI` set) they fail instead. The collect tests build small git repositories, so they need `git`.

If `uv run` picks a system Python whose own packages leak in (for example a `pyo3_runtime.PanicException` from `cryptography` while `pypdf` loads), use a uv-managed Python: `uv python install 3.13`, then run both commands with `UV_MANAGED_PYTHON=1` and `--python 3.13`.

Shared workspace conventions, schemas and checks live in `skills/resume-core/` (start with its `SKILL.md`). Collecting work evidence lives in `skills/resume-collect/` ([spec](docs/superpowers/specs/2026-09-25-resume-collect-design.md)), importing an existing resume in `skills/resume-import/` ([spec](docs/superpowers/specs/2026-09-25-resume-import-design.md)), finding the engineer's projects in the evidence (checkpoint 2) in `skills/resume-analyze/` ([spec](docs/superpowers/specs/2026-09-25-resume-analyze-design.md)), keeping confidential terms off the resume in `skills/resume-sanitize/` ([spec](docs/superpowers/specs/2026-09-25-resume-sanitize-design.md)), asking the engineer for metrics, missing profile details and term decisions (checkpoint 3) in `skills/resume-wizard/` ([spec](docs/superpowers/specs/2026-09-25-resume-wizard-design.md)), writing the bullets and STAR stories in `skills/resume-write/` ([spec](docs/superpowers/specs/2026-09-26-resume-write-design.md)), building the general resume and the per-job versions, with keyword coverage and the claim diff, in `skills/resume-ats/` ([spec](docs/superpowers/specs/2026-09-27-resume-ats-design.md)), rendering in `skills/resume-render/` ([spec](docs/superpowers/specs/2026-09-25-resume-render-design.md)), and running the whole workflow with its four checkpoints in `skills/resume-build/` ([spec](docs/superpowers/specs/2026-09-27-resume-build-design.md)). The commands are in `commands/` and the plugin and marketplace manifests in `.claude-plugin/`; `claude plugin validate .` checks them.
