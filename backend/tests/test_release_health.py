"""Run release-health behavior and workflow guards in the ordinary backend CI."""
from pathlib import Path
import subprocess
import sys


def test_release_health_guards():
    subprocess.run(
        [sys.executable, '-m', 'unittest', 'discover', '-s', 'tools/release/tests'],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
    )
