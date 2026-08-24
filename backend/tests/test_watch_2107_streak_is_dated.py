"""The #2107 falsifier says SEVEN CONSECUTIVE DAYS. Prove the counter counts days.

WHY THIS TEST EXISTS (LAT-P085).

`summarize()` originally walked the recorded day-windows backwards and
incremented a counter per ROW, with no reference to the calendar at all. Seven
windows run back-to-back in one afternoon therefore printed

    consecutive clean days: 7/7
    VERDICT: CLOSABLE — the 7-day falsifier was not refuted.

and the artifact it appended would have read as closure evidence to every later
reader — including one who had no way to know the seven "days" shared a date.
A falsifier whose unit can be counterfeited by running the instrument faster is
not a falsifier. Nobody did this; the point is that nothing stopped them, and
`docs/PRODUCT-BRAIN.md`'s standing bar is that closure needs measured evidence,
which means the measurement has to mean what it says.

The second case guards the label trap: a window recorded with `is_day=false`
can never bank whatever its verdict, so it must not silently extend a streak
either.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "watch_2107_feed_500s.py"


def _load():
    spec = importlib.util.spec_from_file_location("watch_2107", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _window(started_at: str, *, clean: bool = True, is_day: bool = True) -> str:
    return json.dumps(
        {
            "issue": 2107,
            "label": "day" if is_day else "adhoc",
            "is_day": is_day,
            "started_at": started_at,
            "probe": {"samples": 60, "server_errors": 0, "process_ids": {"w1": 1}},
            "sentry": {"count_24h": 0},
            "grade": {"verdict": "CLEAN" if clean else "FAILED"},
            "counts_toward_seven": clean and is_day,
        }
    )


def _streak(tmp_path: Path, lines: list[str], capsys) -> int:
    mod = _load()
    state = tmp_path / "watch.jsonl"
    state.write_text("\n".join(lines) + "\n")
    mod.summarize(state)
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if "consecutive clean days:" in ln)
    return int(line.split(":")[1].strip().split("/")[0])


def test_seven_windows_on_one_date_are_one_day(tmp_path, capsys):
    """The regression this file is named for: rows are not days."""
    lines = [_window(f"2026-08-24T{hour:02d}:00:00+00:00") for hour in range(7)]
    assert _streak(tmp_path, lines, capsys) == 1


def test_seven_consecutive_dates_close_the_falsifier(tmp_path, capsys):
    start = date(2026, 8, 18)
    lines = [
        _window((start + timedelta(days=d)).isoformat() + "T12:00:00+00:00")
        for d in range(7)
    ]
    assert _streak(tmp_path, lines, capsys) == 7


def test_a_calendar_gap_breaks_the_streak(tmp_path, capsys):
    """Aug 20 is missing: only Aug 21-24 are consecutive up to the newest date."""
    lines = [
        _window(f"2026-08-{day:02d}T12:00:00+00:00")
        for day in (17, 18, 19, 21, 22, 23, 24)
    ]
    assert _streak(tmp_path, lines, capsys) == 4


def test_a_failed_window_disqualifies_its_whole_date(tmp_path, capsys):
    """Two windows on Aug 24, one FAILED — the day was not clean, so it is not a day."""
    lines = [
        _window("2026-08-22T12:00:00+00:00"),
        _window("2026-08-23T12:00:00+00:00"),
        _window("2026-08-24T09:00:00+00:00"),
        _window("2026-08-24T15:00:00+00:00", clean=False),
    ]
    assert _streak(tmp_path, lines, capsys) == 0


def test_non_day_windows_never_extend_the_streak(tmp_path, capsys):
    """A window recorded with is_day=false is invisible to the falsifier."""
    lines = [
        _window("2026-08-22T12:00:00+00:00", is_day=False),
        _window("2026-08-23T12:00:00+00:00", is_day=False),
        _window("2026-08-24T12:00:00+00:00"),
    ]
    assert _streak(tmp_path, lines, capsys) == 1


@pytest.mark.parametrize("label,flag,expected", [("day", None, True),
                                                 ("LAT-P084-day1", None, False),
                                                 ("LAT-P084-day1", True, True),
                                                 ("day", False, False)])
def test_counts_as_day_is_explicit_and_overrides_the_label(label, flag, expected):
    """`--label` alone used to decide banking. It still can, for compatibility,
    but `--counts-as-day` must win — that is the whole point of adding it."""
    resolved = flag if flag is not None else (label == "day")
    assert resolved is expected


# ------------------------------------------------------------------ restarts


def test_two_stable_workers_are_not_a_restart():
    """Ruling 129: one dyno x WEB_CONCURRENCY=2 = two ids, forever, healthily.

    The old predicate was `len(processes) > 1`, which made this shape — the
    ONLY shape production ever has — report `restarted: true`, so every window
    graded INCONCLUSIVE and the seven-day falsifier could never bank a day.
    Measured 2026-08-24: both workers reported uptime 6,701s, climbing together.
    """
    mod = _load()
    uptimes = {
        "4211ad2cfb66": {"first_uptime": 6000, "last_uptime": 6701, "born_at_elapsed": -6000.0},
        "c586a31af980": {"first_uptime": 6000, "last_uptime": 6702, "born_at_elapsed": -6000.0},
    }
    restarted, reasons = mod._detect_restart(uptimes)
    assert restarted is False, reasons
    assert reasons == []


def test_uptime_going_backwards_is_a_restart():
    mod = _load()
    uptimes = {
        "aaa": {"first_uptime": 6000, "last_uptime": 12, "born_at_elapsed": -6000.0,
                "went_backwards": True},
    }
    restarted, reasons = mod._detect_restart(uptimes)
    assert restarted is True
    assert "uptime reset" in reasons[0]


def test_a_worker_born_mid_window_is_a_restart():
    """Seen 1800s in with only 300s of uptime: it did not exist at window open."""
    mod = _load()
    uptimes = {"bbb": {"first_uptime": 300, "last_uptime": 400, "born_at_elapsed": 1500.0}}
    restarted, reasons = mod._detect_restart(uptimes)
    assert restarted is True
    assert "born 1500s into the window" in reasons[0]


def test_boot_jitter_inside_tolerance_is_not_a_restart():
    """A worker that predates the window by a hair must not trip the detector."""
    mod = _load()
    uptimes = {"ccc": {"first_uptime": 100, "last_uptime": 160, "born_at_elapsed": 45.0}}
    restarted, _ = mod._detect_restart(uptimes)
    assert restarted is False


def test_a_scale_up_mid_window_is_flagged():
    """One stable worker plus one that appears late: coverage changed under us."""
    mod = _load()
    uptimes = {
        "stable": {"first_uptime": 6000, "last_uptime": 6600, "born_at_elapsed": -6000.0},
        "fresh": {"first_uptime": 30, "last_uptime": 90, "born_at_elapsed": 2400.0},
    }
    restarted, reasons = mod._detect_restart(uptimes)
    assert restarted is True
    assert len(reasons) == 1 and reasons[0].startswith("fresh")
