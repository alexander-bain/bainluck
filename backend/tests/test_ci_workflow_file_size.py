"""GitHub refuses a workflow file over ~512,000 bytes, silently.

Measured twice: #11305's ci.yml at 512,135 bytes and #10090 attempt190's at
513,260 each got a "workflow file issue" run with zero jobs and NO CI run on
the pull request at all, while 511,542 ran (and #13212 hit 514,322 on
Nov 20, 2026 with the same silent 0-job failure). Nothing reddens; the CI row is
simply absent, which notice 28 reads as a STOP only if someone looks.

This guard fails above 508,000 bytes (4,000 bytes of headroom before GitHub's
512,000-byte cliff) so any branch pushing ci.yml near the limit turns red
locally before push.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
JUNIT_GATE_SCRIPT = REPO_ROOT / ".github" / "scripts" / "run-pg-junit-gate.sh"

GITHUB_REFUSES_ABOVE = 512_000
CI_YML_MAX_BYTES = 508_000


def test_ci_workflow_stays_under_githubs_file_size_limit():
    size = CI_YML.stat().st_size
    assert size <= CI_YML_MAX_BYTES, (
        f"ci.yml is {size:,} bytes (limit {CI_YML_MAX_BYTES:,}; GitHub refuses "
        f"above ~{GITHUB_REFUSES_ABOVE:,} with zero CI jobs). Move inline steps "
        "into .github/scripts/."
    )


def test_run_pg_junit_gate_script_enforces_count_skip_and_grep(tmp_path):
    """Guard the shared JUnit gate script extracted from ci.yml."""
    good_test = tmp_path / "test_sample_ok.py"
    good_test.write_text(
        "def test_one():\n"
        "    print('\\n#SAMPLE PASS')\n"
        "    assert True\n\n"
        "def test_two():\n"
        "    assert 1 + 1 == 2\n",
        encoding="utf-8",
    )
    skip_test = tmp_path / "test_sample_skip.py"
    skip_test.write_text(
        "import pytest\n\n"
        "@pytest.mark.skip(reason='skipped')\n"
        "def test_skipped():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    junit = tmp_path / "out.xml"
    log = tmp_path / "out.txt"

    # 1. Exact count + required grep passes
    ok = subprocess.run(
        [
            "bash",
            str(JUNIT_GATE_SCRIPT),
            "--label",
            "#sample",
            "--junit",
            str(junit),
            "--log",
            str(log),
            "--expected",
            "2",
            "--require-grep",
            "^#SAMPLE PASS",
            "--",
            str(good_test),
            "-s",
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "#sample GREEN on all 2 tests" in ok.stdout

    # 2. Wrong expected count fails closed
    wrong_count = subprocess.run(
        [
            "bash",
            str(JUNIT_GATE_SCRIPT),
            "--label",
            "#sample",
            "--junit",
            str(junit),
            "--log",
            str(log),
            "--expected",
            "3",
            "--",
            str(good_test),
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
    )
    assert wrong_count.returncode != 0
    assert "expected 3" in (wrong_count.stdout + wrong_count.stderr)

    # 3. Skipped test fails closed
    skipped = subprocess.run(
        [
            "bash",
            str(JUNIT_GATE_SCRIPT),
            "--label",
            "#sample",
            "--junit",
            str(junit),
            "--log",
            str(log),
            "--expected",
            "1",
            "--",
            str(skip_test),
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
    )
    assert skipped.returncode != 0
    assert "SKIPPED 1 test(s)" in (skipped.stdout + skipped.stderr)
