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

Shared workspace conventions, schemas and checks live in `skills/resume-core/` (start with its `SKILL.md`). Collecting work evidence lives in `skills/resume-collect/` ([spec](docs/superpowers/specs/2026-09-25-resume-collect-design.md)), importing an existing resume in `skills/resume-import/` ([spec](docs/superpowers/specs/2026-09-25-resume-import-design.md)), and rendering in `skills/resume-render/` ([spec](docs/superpowers/specs/2026-09-25-resume-render-design.md)).
