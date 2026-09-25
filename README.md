# resume-builder
Discover your most impactful work and prove the value you have delivered.

A Claude Code plugin of portable agent skills that builds an evidence-backed engineering resume.
Design: [architecture spec](docs/superpowers/specs/2026-09-24-resume-builder-architecture-design.md).

## Development

Requires [uv](https://docs.astral.sh/uv/). Scripts support Python 3.10 and later.

```bash
uv run skills/resume-render/scripts/render.py --install-browser   # once: Chromium for the PDF tests
uv run --with pytest --with-requirements skills/resume-render/scripts/render.py pytest
```

The second command takes the render dependencies from `render.py`'s inline metadata. Without them (plain `uv run --with pytest pytest`) the render end-to-end tests are skipped, and tests that need Chromium skip when it is not installed. In CI (`CI` set) both fail instead.

Shared workspace conventions, schemas and checks live in `skills/resume-core/` (start with its `SKILL.md`). Rendering lives in `skills/resume-render/` ([spec](docs/superpowers/specs/2026-09-25-resume-render-design.md)).
