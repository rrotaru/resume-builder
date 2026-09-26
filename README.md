# resume-builder
Discover your most impactful work and prove the value you have delivered.

A Claude Code plugin of portable agent skills that builds an evidence-backed engineering resume.
Design: [architecture spec](docs/superpowers/specs/2026-09-24-resume-builder-architecture-design.md).
Progress and what to build next: [roadmap](docs/ROADMAP.md).

## Development

Requires [uv](https://docs.astral.sh/uv/). Scripts support Python 3.10 and later.

```bash
uv run skills/resume-render/scripts/render.py --install-browser   # once: Chromium for the PDF tests
uv run --with pytest --with-requirements skills/resume-render/scripts/render.py \
  --with-requirements skills/resume-import/scripts/extract_text.py pytest
```

The second command takes the dependencies from the inline metadata of `render.py` and `extract_text.py` (collect's `ingest_reviews.py` pins the same versions). Without them (plain `uv run --with pytest pytest`) the render end-to-end tests and the PDF and DOCX import and review tests are skipped, and tests that need Chromium skip when it is not installed. In CI (`CI` set) they fail instead. The collect tests build small git repositories, so they need `git`.

If `uv run` picks a system Python whose own packages leak in (for example a `pyo3_runtime.PanicException` from `cryptography` while `pypdf` loads), use a uv-managed Python: `uv python install 3.13`, then run both commands with `UV_MANAGED_PYTHON=1` and `--python 3.13`.

Shared workspace conventions, schemas and checks live in `skills/resume-core/` (start with its `SKILL.md`). Collecting work evidence lives in `skills/resume-collect/` ([spec](docs/superpowers/specs/2026-09-25-resume-collect-design.md)), importing an existing resume in `skills/resume-import/` ([spec](docs/superpowers/specs/2026-09-25-resume-import-design.md)), finding the engineer's projects in the evidence (checkpoint 2) in `skills/resume-analyze/` ([spec](docs/superpowers/specs/2026-09-25-resume-analyze-design.md)), keeping confidential terms off the resume in `skills/resume-sanitize/` ([spec](docs/superpowers/specs/2026-09-25-resume-sanitize-design.md)), asking the engineer for metrics, missing profile details and term decisions (checkpoint 3) in `skills/resume-wizard/` ([spec](docs/superpowers/specs/2026-09-25-resume-wizard-design.md)), writing the bullets and STAR stories in `skills/resume-write/` ([spec](docs/superpowers/specs/2026-09-26-resume-write-design.md)), and rendering in `skills/resume-render/` ([spec](docs/superpowers/specs/2026-09-25-resume-render-design.md)).
