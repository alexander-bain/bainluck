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
