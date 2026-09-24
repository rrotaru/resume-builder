---
name: resume-init
description: Set up a resume-builder workspace. Checks that uv is installed and creates the workspace folder, default config.json and empty decision files. Use before any other resume-builder step, or when the engineer asks to start a new resume workspace.
---

# resume-init

Follow `../resume-core/SKILL.md` for workspace conventions.

1. Run `uv --version`. If it fails, show the engineer the install command for their OS and wait for them to confirm it is installed:
   - macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - Homebrew: `brew install uv`
2. Ask where the workspace should live (default `./resume-workspace`) and the target role (for example "Senior Backend Engineer").
3. Run `uv run ../resume-core/scripts/init_workspace.py --workspace <path> --target-role "<role>"`.
   The script never overwrites existing files. If the workspace is inside a git repository it adds the folder to `.git/info/exclude` so work data is not committed by accident.
4. Report the script's output to the engineer. Chromium for PDF rendering is installed later, the first time a resume is rendered.
