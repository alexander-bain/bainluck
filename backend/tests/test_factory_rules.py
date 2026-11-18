"""Run the Factory's dependency-free rules in the existing backend CI check."""

from pathlib import Path
import subprocess
import sys


def test_factory_rules():
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "scripts/factory/tests",
            "-v",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
