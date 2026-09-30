"""Carry offline workflow-tool behavior checks in ordinary backend shards."""

from pathlib import Path
import subprocess
import sys

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("module", ["test_claim_issue", "test_issue_progress"])
def test_workflow_status_tool_behavior(module):
    result = subprocess.run(
        [sys.executable, "-m", "unittest", module],
        cwd=REPO_ROOT / "scripts" / "tests",
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
