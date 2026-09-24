import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURE_WORKSPACE = REPO / "tests" / "fixtures" / "workspace"
CORE_SCRIPTS = REPO / "skills" / "resume-core" / "scripts"


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A private copy of the fixture workspace that a test may modify."""
    target = tmp_path / "ws"
    shutil.copytree(FIXTURE_WORKSPACE, target)
    return target
