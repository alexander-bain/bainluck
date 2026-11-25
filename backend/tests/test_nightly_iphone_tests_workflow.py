"""Contract tests for the nightly hosted full iPhone suite proposal."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "nightly-iphone-tests.yml"
SCRIPT_PATH = REPO_ROOT / "tools" / "nightly-iphone-tests.sh"
ISSUE_FORMATTER_PATH = REPO_ROOT / "tools" / "nightly_iphone_issue.py"

_SPEC = importlib.util.spec_from_file_location("nightly_iphone_issue", ISSUE_FORMATTER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
ISSUE_FORMATTER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ISSUE_FORMATTER)


def test_nightly_iphone_workflow_triggers_only_on_schedule_and_dispatch():
    wf = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    on = wf.get("on", wf.get(True))
    assert set(on) == {"schedule", "workflow_dispatch"}
    assert "pull_request" not in on
    assert "push" not in on
    assert isinstance(on["schedule"], list) and len(on["schedule"]) == 1
    assert "cron" in on["schedule"][0]

    assert wf["concurrency"] == {
        "group": "nightly-iphone-tests",
        "cancel-in-progress": False,
    }
    assert wf["permissions"] == {"contents": "read", "issues": "write"}

    job = wf["jobs"]["iphone-full-suite"]
    assert job["runs-on"] == "xcode-27"
    assert job["timeout-minutes"] <= 120
    wf_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "$0.00" in wf_text
    assert "2:30 AM PT in winter, 3:30 AM in summer" in wf_text
    assert "5:00 AM PT" in wf_text
    assert "24-61 minutes" in wf_text
    run_blobs = "\n".join(s.get("run", "") for s in job["steps"])
    assert "tools/nightly-iphone-tests.sh" in run_blobs
    assert "tools/nightly_iphone_issue.py" in run_blobs
    assert "Failed check: nightly iPhone test suite (" in run_blobs
    assert "Flaky:" not in run_blobs
    assert "Rig:" not in run_blobs
    upload_step = next(
        s for s in job["steps"] if s.get("uses", "").startswith("actions/upload-artifact")
    )
    assert upload_step.get("if") == "always()"


def test_nightly_iphone_runner_script_runs_whole_scheme_with_cleanup():
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    proc = subprocess.run(["bash", "-n", str(SCRIPT_PATH)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    non_comment = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    assert "-scheme BainLuckTests" in non_comment
    assert "-only-testing" not in non_comment
    assert "-skip-testing" not in non_comment
    assert "xcrun simctl create" in non_comment
    assert "xcrun simctl delete" in non_comment
    assert "trap cleanup EXIT" in non_comment
    assert "watch_iphone_receipt.py" in non_comment
    assert "--min-tests 7800" in non_comment
    assert "--min-tests 1\n" not in non_comment


def test_nightly_iphone_issue_formatter_tracks_first_night_diffs_and_incomplete_runs():
    night1_receipt = {
        "sha": "aaa1111",
        "exit_code": 65,
        "verdict": "UNPAID",
        "tests": 8763,
        "passed": 8759,
        "failed": 3,
        "timed_out": 1,
        "min_tests": 7800,
        "below_min_tests": False,
        "failed_tests": [
            "AlphaTests.testOld1",
            "BetaTests.testOld2",
            "GammaTests.testFixedA",
        ],
        "timed_out_tests": ["ThemeCollectionReaderTests.testFixedTimeout"],
    }
    night1_md = ISSUE_FORMATTER.format_issue_comment(
        night1_receipt,
        run_date="2026-06-15",
        sha="aaa1111",
        run_url="https://example.invalid/runs/1",
        prior_bodies=(),
    )
    n1_lines = night1_md.splitlines()
    assert n1_lines[0] == "Jun 15: 8,763 run, 3 failed, 1 timed out"
    assert n1_lines[1] == "first night"
    assert "<details>" in night1_md
    assert "- `AlphaTests.testOld1`" in night1_md
    assert "- `ThemeCollectionReaderTests.testFixedTimeout` (timed out)" in night1_md

    night2_receipt = {
        "sha": "bbb2222",
        "exit_code": 65,
        "verdict": "UNPAID",
        "tests": 8800,
        "passed": 8795,
        "failed": 5,
        "timed_out": 0,
        "min_tests": 7800,
        "below_min_tests": False,
        "failed_tests": [
            "AlphaTests.testOld1",
            "BetaTests.testOld2",
            "DeltaTests.testNew1",
            "EpsilonTests.testNew2",
            "ZetaTests.testNew3",
        ],
        "timed_out_tests": [],
    }
    night2_md = ISSUE_FORMATTER.format_issue_comment(
        night2_receipt,
        run_date="2026-06-16",
        sha="bbb2222",
        run_url="https://example.invalid/runs/2",
        prior_bodies=[night1_md],
    )
    n2_lines = night2_md.splitlines()
    assert n2_lines[0] == "Jun 16: 8,800 run, 5 failed, 0 timed out"
    assert n2_lines[1] == "3 new, 2 now pass"
    assert "**New failures:**" in night2_md
    assert "- `DeltaTests.testNew1`" in night2_md
    assert "**Now passing:**" in night2_md
    assert "- `GammaTests.testFixedA`" in night2_md
    assert "- `ThemeCollectionReaderTests.testFixedTimeout`" in night2_md

    # Early crash (<7800 tests) reports floor breach and never becomes baseline for Night 3.
    early_crash_receipt = {
        "sha": "ccc3333",
        "exit_code": 65,
        "verdict": "UNPAID",
        "tests": 500,
        "passed": 498,
        "failed": 2,
        "timed_out": 0,
        "min_tests": 7800,
        "below_min_tests": True,
        "min_tests_reason": "Executed 500 tests, below minimum floor of 7800",
        "failed_tests": ["AlphaTests.testOld1", "CrashTests.testEarlyCrash"],
        "timed_out_tests": [],
    }
    crash_md = ISSUE_FORMATTER.format_issue_comment(
        early_crash_receipt,
        run_date="2026-06-17",
        sha="ccc3333",
        run_url="https://example.invalid/runs/3",
        prior_bodies=[night1_md, night2_md],
    )
    crash_lines = crash_md.splitlines()
    assert crash_lines[0] == "Jun 17: 500 run (below 7,800 floor), 2 failed, 0 timed out"
    assert crash_lines[1].startswith("1 new (incomplete run below 7,800 floor")
    assert "**Now passing:**" not in crash_md
    assert "Executed 500 tests, below minimum floor of 7800" in crash_md

    night4_md = ISSUE_FORMATTER.format_issue_comment(
        night2_receipt,
        run_date="2026-06-18",
        sha="ddd4444",
        run_url="https://example.invalid/runs/4",
        prior_bodies=[night1_md, night2_md, crash_md],
    )
    assert night4_md.splitlines()[1] == "0 new, 0 now pass"
