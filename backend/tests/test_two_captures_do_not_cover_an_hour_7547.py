"""#7547 — two captures do not cover an hour.

PILLAR: TRUTH / FORMATTING. SHIP: the phone's chart draws the turns the venue
recorded in an hour our own polls touched twice, instead of one median price.

`/probability-timeline` fenced any (outcome, bucket) cell holding TWO capture
instants: one median at the bucket start, every venue minute refused. Codex's
replay of 61097129 *over 9.5*, 2026-09-18T20Z: captures at 20:20:00 and
20:48:52, seventeen venue minutes 20:07–20:55 with a .425 trough and a .435
peak; the web drew nineteen rows, the phone one .43.

The replacement asks for COVERAGE (`captures_cover_cell`), and these are its
unit guards. The real-route replay is `test_P6` in
`tests/integration/test_phone_history_detail_7547_real_pg_redis.py`.

Every threshold case below sits BOTH sides of the line at one-minute resolution
— eight minutes is covered, twelve is not — so a multiple moved from 10× to 2×
or to 20× fails a named test. A fixture spaced forty minutes apart cannot tell
those three apart (it is uncovered under all of them); that was the flaw codex
found in the first proposal's mutant fixture.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.utils import generic_market_history as gmh
from app.utils.futures_chart_series import KALSHI_FINE_INTERVAL

HOUR = datetime(2026, 9, 18, 20, 0, 0, tzinfo=timezone.utc)
END = HOUR + timedelta(hours=1)


def _at(minutes: float) -> datetime:
    return HOUR + timedelta(minutes=minutes)


def _covers(stamps, *, start=HOUR, end=END) -> bool:
    return gmh.captures_cover_cell(stamps, cell_start=start, cell_end=end)


def test_the_hole_is_the_same_line_the_fill_trigger_draws():
    # One definition of "our captures are fine" in the route, not two.
    assert KALSHI_FINE_INTERVAL * 60 * gmh.COARSE_CAPTURE_MULTIPLE == 600


def test_the_named_hour_is_not_covered():
    """61097129 *over 9.5*, 2026-09-18T20Z — the count fenced it; coverage does not."""
    stamps = [
        datetime(2026, 9, 18, 20, 20, 0, 55540, tzinfo=timezone.utc),
        datetime(2026, 9, 18, 20, 48, 52, 365886, tzinfo=timezone.utc),
    ]
    assert _covers(stamps) is False


def test_clustered_captures_leave_the_tail_uncovered():
    """The counterexample to a spacing rule: a two-minute median gap, fifty-eight
    minutes nobody polled. A median-spacing predicate calls this dense."""
    assert _covers([_at(0), _at(2)]) is False
    assert _covers([_at(58), _at(60 - 1e-3)]) is False  # and the head, mirrored


def test_the_live_poll_covers_its_cells():
    """The fence's reason to exist: two-minute in-play polling, fifteen-minute cells."""
    start = HOUR
    stamps = [start + timedelta(minutes=m, seconds=7) for m in range(0, 15, 2)]
    assert _covers(stamps, start=start, end=start + timedelta(minutes=15)) is True
    # A missed poll (four minutes) is still covered.
    assert _covers([s for s in stamps if s.minute != 6], start=start,
                   end=start + timedelta(minutes=15)) is True


def test_eight_minutes_is_covered_and_twelve_is_not():
    """Both sides of the line — kills a 2× mutant (eight would read uncovered) and
    a 20× mutant (twelve would read covered)."""
    eight = [_at(m) for m in range(4, 60, 8)]  # head 4, gaps 8, tail 4
    assert _covers(eight) is True
    twelve = [_at(m) for m in range(6, 60, 12)]  # head 6, gaps 12, tail 6
    assert _covers(twelve) is False


def test_the_edges_count_and_a_ten_minute_stretch_is_a_hole():
    interior = [_at(m) for m in range(0, 61, 5)]
    assert _covers(interior) is True
    assert _covers([s for s in interior if s != _at(5)]) is False  # a 10-minute interior hole
    assert _covers([s for s in interior if s != _at(0) and s != _at(5)]) is False  # head of 10
    assert _covers([s for s in interior if s not in (_at(55), _at(60))]) is False  # tail of 10


def test_one_capture_never_covers_however_narrow_the_cell():
    """Never looser than the count it replaces: a lone capture in the middle of a
    fifteen-minute in-play cell is five minutes from both edges and would read
    covered — newly fencing venue minutes the route admits today."""
    start = HOUR
    assert _covers([start + timedelta(minutes=7, seconds=30)], start=start,
                   end=start + timedelta(minutes=15)) is False
    assert _covers([], start=start, end=start + timedelta(minutes=15)) is False
    # Two readings at the SAME instant (two sources) are one instant.
    assert _covers([_at(30), _at(30)], start=_at(25), end=_at(35)) is False


def test_the_cell_is_judged_on_the_part_the_window_can_see():
    """The current hour ends at `now`, not at the top of the next hour; a cell
    straddling the window's start begins at the window. The route clamps."""
    stamps = [_at(0), _at(4)]
    assert _covers(stamps, end=_at(8)) is True
    assert _covers(stamps) is False
    late = [_at(50), _at(55)]
    assert _covers(late, start=_at(48)) is True
    assert _covers(late) is False
