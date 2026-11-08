"""#12278 — Guard tests for tools/ios_stack_frame_guard_12278.py and release archive scripts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_SCRIPT = REPO_ROOT / "tools" / "ios_stack_frame_guard_12278.py"
WATCH_ARCHIVE_SH = REPO_ROOT / "tools" / "watch-companion-archive.sh"
NATIVE_RELEASE_SH = REPO_ROOT / "tools" / "native-release-check.sh"


def test_ios_stack_frame_guard_12278_self_check():
    """Verify the prologue sub sp parser fails on parent commit d8f7c15e59 (338,912 B) and passes on HEAD."""
    proc = subprocess.run(
        [sys.executable, str(GUARD_SCRIPT), "--self-check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"stderr={proc.stderr}\nstdout={proc.stdout}"
    assert "OVER: 338,912 B" in proc.stdout
    assert "RESULT: PASS" in proc.stdout


def test_release_archive_scripts_invoke_stack_frame_guard_12278():
    """Both native Release archive gates call tools/ios_stack_frame_guard_12278.py."""
    assert "ios_stack_frame_guard_12278.py" in WATCH_ARCHIVE_SH.read_text()
    assert "ios_stack_frame_guard_12278.py" in NATIVE_RELEASE_SH.read_text()
