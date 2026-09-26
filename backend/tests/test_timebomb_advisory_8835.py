"""#8835 — the scheduled expiring-fixture advisory, proved end to end.

PILLAR TRUTH. SHIP: user fixes stop waiting on test fixtures that expire with
the calendar. `.github/workflows/clock-timebomb-advisory.yml` runs
`scripts/timebomb_confirm.py` over `scripts/timebomb_watch_targets.txt` daily.
This file is what makes that job an instrument rather than a green light:

* a DELIBERATELY expiring fixture is caught while the real clock is still before
  its date, and named by test id and fake instant — and a clock-relative fixture
  beside it is not;
* a harness fault (no target, a hung point) is a different exit and a different
  list from a bomb, and never produces one;
* the workflow cannot conclude `failure` (merge-gate refuses any sha carrying a
  failed check-run, and a scheduled run's check-run lands on master's HEAD), and
  its bounds add up.

The canaries are GENERATED here with literal dates computed from today, so they
never expire in the repo themselves — a committed canary with a literal date
would be red at the real clock one day and stop testifying.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
import yaml

BACKEND = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "timebomb_confirm.py"
TARGETS = BACKEND / "scripts" / "timebomb_watch_targets.txt"
WORKFLOWS = BACKEND.parent / ".github" / "workflows"
WORKFLOW = WORKFLOWS / "clock-timebomb-advisory.yml"


def _literal(dt: datetime) -> str:
    return f"datetime({dt.year}, {dt.month}, {dt.day}, tzinfo=timezone.utc)"


def _oracle(cwd: pathlib.Path, *args: str, timeout: float = 120) -> tuple[int, dict, str]:
    out_json = cwd / "result.json"
    summary = cwd / "summary.md"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--whole-clock",
         "--json", str(out_json), "--summary", str(summary)],
        cwd=cwd, capture_output=True, text=True, timeout=timeout,
    )
    result = json.loads(out_json.read_text()) if out_json.is_file() else {}
    text = summary.read_text() if summary.is_file() else ""
    return proc.returncode, result, text + "\n" + proc.stdout + proc.stderr


# --------------------------------------------------------------------------
# The target list is real
# --------------------------------------------------------------------------


def _watched() -> list[str]:
    return [
        ln.strip() for ln in TARGETS.read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    ]


def test_the_watch_list_is_populated_and_every_target_exists():
    """A renamed target would turn the scheduled run into a baseline FAULT every
    day; fail it here, in PR CI, where the rename happens."""
    watched = _watched()
    assert len(watched) >= 10, watched
    missing = [t for t in watched if not (BACKEND / t).is_file()]
    assert missing == [], f"watched fixtures moved or deleted: {missing}"
    assert len(set(watched)) == len(watched), "duplicate target"


# --------------------------------------------------------------------------
# The oracle: bomb caught, relative passes, fault kept apart
# --------------------------------------------------------------------------


@pytest.fixture
def canaries(tmp_path):
    real_now = datetime.now(timezone.utc)
    expires = (real_now + timedelta(days=20)).replace(hour=0, minute=0, second=0, microsecond=0)
    (tmp_path / "test_canary_expiring.py").write_text(
        "from datetime import datetime, timezone\n"
        f"EXPIRES = {_literal(expires)}  # the dated fixture\n"
        "def test_fixture_still_current():\n"
        "    assert datetime.now(timezone.utc) < EXPIRES\n"
    )
    # The same expiry living in a FIXTURE: it raises in setup, which pytest
    # reports as ERROR, not FAILED. `-rf` alone dropped that line.
    (tmp_path / "test_canary_setup_expiring.py").write_text(
        "import pytest\n"
        "from datetime import datetime, timezone\n"
        f"EXPIRES = {_literal(expires)}\n"
        "@pytest.fixture\n"
        "def specimen():\n"
        "    assert datetime.now(timezone.utc) < EXPIRES, 'specimen expired'\n"
        "    return 1\n"
        "def test_uses_specimen(specimen):\n"
        "    assert specimen == 1\n"
    )
    (tmp_path / "test_canary_relative.py").write_text(
        "from datetime import datetime, timedelta, timezone\n"
        "NOW = (datetime.now(timezone.utc) - timedelta(minutes=1)).replace(microsecond=0)\n"
        "def test_relative_fixture():\n"
        "    assert NOW + timedelta(days=30) > datetime.now(timezone.utc)\n"
    )
    return tmp_path, real_now, expires


def test_an_expiring_fixture_is_caught_before_its_date_and_a_relative_one_passes(canaries):
    cwd, real_now, expires = canaries
    code, result, text = _oracle(
        cwd, "test_canary_expiring.py", "test_canary_setup_expiring.py",
        "test_canary_relative.py", "--offsets", "1,32",
    )
    assert code == 1, text
    assert result["verdict"] == "BOMB"
    assert result["faults"] == []
    assert set(result["bombs"]) == {
        "test_canary_expiring.py::test_fixture_still_current",
        "test_canary_setup_expiring.py::test_uses_specimen",
    }, text
    # Caught BEFORE its real date: the real clock is still short of the literal.
    assert real_now < expires
    for nodeid, instants in result["bombs"].items():
        # Only the +32d point is past the literal; +1d must stay green, or the
        # oracle is reporting a target that fails everywhere, not a boundary.
        assert len(instants) == 1, (nodeid, instants)
        first_red = datetime.fromisoformat(instants[0])
        assert first_red > expires
        assert first_red - datetime.fromisoformat(result["real_now"]) == timedelta(days=32)
    # The job summary names the exact test and the fake instant.
    assert "test_canary_expiring.py::test_fixture_still_current" in text
    assert result["bombs"]["test_canary_expiring.py::test_fixture_still_current"][0] in text
    assert "Harness faults — points that produced no readable result (0)" in text


def test_a_relative_fixture_alone_is_clean(canaries):
    cwd, _, _ = canaries
    code, result, text = _oracle(cwd, "test_canary_relative.py", "--offsets", "1,32")
    assert code == 0, text
    assert result["verdict"] == "CLEAN"
    assert result["bombs"] == {} and result["faults"] == []
    assert [p["label"] for p in result["points"]] == ["PASS", "PASS", "PASS"]


def test_a_missing_target_is_a_harness_fault_not_a_bomb(tmp_path):
    code, result, text = _oracle(tmp_path, "test_does_not_exist.py", "--offsets", "32")
    assert code == 2, text
    assert result["verdict"] == "HARNESS FAULT"
    assert result["bombs"] == {}
    assert len(result["faults"]) == 1 and result["faults"][0].startswith("baseline"), result
    assert "exit 4" in result["faults"][0]


def test_a_hung_point_is_a_bounded_harness_fault(tmp_path):
    hang_after = datetime.now(timezone.utc) + timedelta(days=10)
    (tmp_path / "test_canary_hangs.py").write_text(
        "import time\n"
        "from datetime import datetime, timezone\n"
        f"HANG_AFTER = {_literal(hang_after)}\n"
        "def test_hangs_in_the_future():\n"
        "    if datetime.now(timezone.utc) > HANG_AFTER:\n"
        "        time.sleep(120)\n"
    )
    code, result, text = _oracle(
        tmp_path, "test_canary_hangs.py", "--offsets", "32", "--timeout-per-point", "4",
        timeout=90,
    )
    assert code == 2, text
    assert result["bombs"] == {}
    assert len(result["faults"]) == 1 and "TIMED OUT after 4s" in result["faults"][0], result
    assert result["points"][-1]["label"] == "FAULT"
    assert result["points"][-1]["elapsed_s"] < 30


def test_a_malformed_offset_is_a_usage_error_not_a_bomb(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "x.py", "--offsets", "abc"],
        cwd=tmp_path, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 2, proc.stderr


# --------------------------------------------------------------------------
# The workflow: advisory, bounded, unstackable, invisible to other consumers
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def wf():
    return yaml.safe_load(WORKFLOW.read_text())


def test_the_workflow_runs_only_on_schedule_or_by_hand(wf):
    triggers = wf[True]  # YAML 1.1 reads the bare key `on` as True
    assert set(triggers) == {"schedule", "workflow_dispatch"}, triggers
    assert len(triggers["schedule"]) == 1, "more than one cron is a frequency change (#8835)"


def test_runs_cannot_stack(wf):
    assert wf["concurrency"]["group"] == "clock-timebomb-advisory"
    assert wf["concurrency"]["cancel-in-progress"] is False


def test_no_step_can_turn_the_check_run_red(wf):
    """merge-gate.sh refuses any sha with a `failure` check-run (notice 32)."""
    steps = wf["jobs"]["timebomb"]["steps"]
    offenders = [s.get("name") or s.get("uses") for s in steps if s.get("continue-on-error") is not True]
    assert offenders == [], f"steps that can fail the advisory job: {offenders}"
    assert "continue-on-error" not in wf["jobs"]["timebomb"], (
        "job-level continue-on-error still leaves the job's check-run `failure`"
    )


def test_the_bounds_add_up(wf):
    """A job timeout concludes `failure`; the oracle's own caps must fire first."""
    job = wf["jobs"]["timebomb"]
    oracle = next(s for s in job["steps"] if s.get("id") == "oracle")
    run = oracle["run"]
    per_point = float(re.search(r"--timeout-per-point\s+(\d+)", run).group(1))
    default_offsets = wf[True]["workflow_dispatch"]["inputs"]["offsets"]["default"]
    assert default_offsets in oracle["env"]["OFFSETS"]
    n_points = 1 + len(default_offsets.split(","))  # +0 control + offsets
    sys.path.insert(0, str(SCRIPT.parent))
    from timebomb_confirm import SELF_CHECK_TIMEOUT_S

    worst_s = (1 + n_points) * per_point + n_points * SELF_CHECK_TIMEOUT_S  # + baseline
    assert worst_s < oracle["timeout-minutes"] * 60, (worst_s, oracle["timeout-minutes"])
    step_caps = sum(s.get("timeout-minutes", 0) for s in job["steps"])
    assert step_caps < job["timeout-minutes"], (step_caps, job["timeout-minutes"])


def test_the_oracle_step_reads_the_watch_list_on_the_whole_clock(wf):
    oracle = next(s for s in wf["jobs"]["timebomb"]["steps"] if s.get("id") == "oracle")
    assert "scripts/timebomb_watch_targets.txt" in oracle["run"]
    assert "--whole-clock" in oracle["run"], "datetime-only is candidates, not a verdict"
    assert "--json" in oracle["run"] and "--summary" in oracle["run"]
    # Inputs reach the shell through env, never interpolated into the script.
    assert "${{" not in oracle["run"]


def test_the_record_is_retained_whatever_happened(wf):
    upload = next(s for s in wf["jobs"]["timebomb"]["steps"]
                  if str(s.get("uses", "")).startswith("actions/upload-artifact"))
    assert upload["if"] == "always()"
    assert upload["with"]["retention-days"] >= 14


def test_no_other_workflow_listens_to_this_one(wf):
    """`workflow_run` listeners (alert-intake, heavy-sync, shard-hints) key on
    workflow NAME; this one must stay out of their lists."""
    name = wf["name"]
    assert name != "CI"
    listeners = []
    for path in WORKFLOWS.glob("*.yml"):
        other = yaml.safe_load(path.read_text()) or {}
        wr = (other.get(True) or {}).get("workflow_run") if isinstance(other.get(True), dict) else None
        if wr and name in (wr.get("workflows") or []):
            listeners.append(path.name)
    assert listeners == [], listeners
