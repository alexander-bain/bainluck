"""The full CI shards execute the release-loop selector and workflow guards."""
import subprocess
import sys
from pathlib import Path


def test_release_loop_live_path_guards():
    root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [sys.executable, '-m', 'unittest', 'discover', '-s', 'tools/release/tests', '-p', 'test_live*.py'],
        cwd=root,
        check=True,
    )
