"""Contract tests for the nightly hosted full iPhone suite proposal."""

from __future__ import annotations

from pathlib import Path
import subprocess

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "nightly-iphone-tests.yml"
SCRIPT_PATH = REPO_ROOT / "tools" / "nightly-iphone-tests.sh"


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
    run_blobs = "\n".join(s.get("run", "") for s in job["steps"])
    assert "tools/nightly-iphone-tests.sh" in run_blobs
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
