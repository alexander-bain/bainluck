"""Ruling 241: A — tests-only timing quarantine (`backend/tests/timing_quarantine.json`).

A timing test that fails on master, passes on the alarm's automatic re-run, and
was not touched by the batch is moved within the hour to `flaky-canary` via a
tests-only PR adding an entry here, with an issue and at most 7 days to repair
or delete it.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

from tests import conftest

ROOT = Path(__file__).resolve().parents[2]
CANARY_SCRIPT = ROOT / ".github" / "scripts" / "flaky-canary.sh"


def test_shipped_timing_quarantine_entries_are_valid_and_within_seven_days():
    assert conftest.TIMING_QUARANTINE_FILE.exists()
    entries = json.loads(conftest.TIMING_QUARANTINE_FILE.read_text(encoding="utf-8"))
    assert isinstance(entries, list)
    today = dt.date.today()
    seen: set[str] = set()
    for entry in entries:
        assert isinstance(entry, dict)
        nodeid = entry.get("nodeid")
        assert isinstance(nodeid, str) and nodeid.startswith("tests/") and "::" in nodeid
        assert nodeid not in seen, f"duplicate timing_quarantine entry: {nodeid}"
        seen.add(nodeid)
        issue = entry.get("issue")
        assert isinstance(issue, int) and not isinstance(issue, bool) and issue > 0
        added = dt.date.fromisoformat(entry["added"])
        expires = dt.date.fromisoformat(entry["expires"])
        span = (expires - added).days
        assert 0 <= span <= conftest.MAX_TIMING_QUARANTINE_DAYS, (
            f"{nodeid}: quarantine window is {span} days (cap {conftest.MAX_TIMING_QUARANTINE_DAYS})"
        )
        assert today <= expires, (
            f"{nodeid} (issue #{issue}) expired on {expires.isoformat()} — repair or delete it"
        )
        assert isinstance(entry.get("reason"), str) and entry["reason"].strip()


def test_timing_quarantine_activates_until_expiry_and_rejects_over_seven_days(tmp_path):
    qfile = tmp_path / "timing_quarantine.json"
    t_ok = "tests/test_example_timing.py::test_active"
    t_over = "tests/test_example_timing.py::test_too_long"
    t_bad = "tests/test_example_timing.py::test_no_issue"
    qfile.write_text(
        json.dumps(
            [
                {
                    "nodeid": t_ok,
                    "issue": 12392,
                    "added": "2025-05-01",
                    "expires": "2025-05-08",
                    "reason": "failed on master, passed on rerun, untouched by batch",
                },
                {
                    "nodeid": t_over,
                    "issue": 12393,
                    "added": "2025-05-01",
                    "expires": "2025-05-09",
                    "reason": "8-day window must be refused",
                },
                {
                    "nodeid": t_bad,
                    "issue": 0,
                    "added": "2025-05-01",
                    "expires": "2025-05-05",
                    "reason": "missing real issue",
                },
            ]
        ),
        encoding="utf-8",
    )
    assert conftest.timing_quarantined_tests(qfile, today=dt.date(2025, 5, 1)) == frozenset({t_ok})
    assert conftest.timing_quarantined_tests(qfile, today=dt.date(2025, 5, 8)) == frozenset({t_ok})
    assert conftest.timing_quarantined_tests(qfile, today=dt.date(2025, 5, 9)) == frozenset()


def test_quarantined_tests_merges_env_and_timing_file_and_canary_still_reports(
    tmp_path, monkeypatch
):
    qfile = tmp_path / "timing_quarantine.json"
    t_env = "tests/test_env.py::test_from_issue"
    t_file = "tests/test_timing.py::test_from_file"
    qfile.write_text(
        json.dumps(
            [
                {
                    "nodeid": t_file,
                    "issue": 12392,
                    "added": "2025-05-01",
                    "expires": "2025-05-08",
                    "reason": "ruling 241-A",
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CI_QUARANTINE", json.dumps([t_env]))
    monkeypatch.setattr(conftest, "TIMING_QUARANTINE_FILE", qfile)
    monkeypatch.setattr(
        conftest,
        "timing_quarantined_tests",
        lambda path=None, today=None: _real_timing(qfile, dt.date(2025, 5, 4)),
    )
    merged = conftest.quarantined_tests()
    assert merged == frozenset({t_env, t_file})
    rep = SimpleNamespace(when="call", failed=True, nodeid=t_file)
    assert conftest.quarantine_forgives(rep, merged, mode="")
    assert not conftest.quarantine_forgives(rep, merged, mode="canary")


_real_timing = conftest.timing_quarantined_tests


def test_flaky_canary_script_reads_timing_quarantine_file():
    script = CANARY_SCRIPT.read_text(encoding="utf-8")
    assert "tests/timing_quarantine.json" in script
    assert "CI_QUARANTINE_MODE=canary" in script
