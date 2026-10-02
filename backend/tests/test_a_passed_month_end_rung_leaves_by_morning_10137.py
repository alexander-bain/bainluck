"""#10137 — a date ladder stops showing a month-end deadline the morning after.

On production at 23:52Z on 2026-10-01, `/api/feed` served "September 30" as
the FIRST rung of seven Discover date ladders ("Iran leadership change? ·
September 30 0%"); at 00:02Z on Oct 2 every one of them had dropped it. The
rung was never stuck — the shared expiry rule (`expired_ladder_rungs`, which
the feed, `/futures/{id}` and `/politics` all call) gave every dated rung a
whole extra DAY of grace past 23:59:59 UTC of its named day, so a passed
deadline stayed on a US reader's screen until 4:59pm Pacific the next day.

The grace is now 12 hours: past every US-time venue deadline (Hawaii closes
the day at 09:59Z), and gone before a Pacific reader wakes up.

Clocks are fixed instants (gotcha #44) and every arm asserts BOTH directions:
the passed rung goes AND the live rungs stay.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.utils.market_staleness import (
    EXPIRED_RUNG_MAX_PROBABILITY,
    RUNG_GRACE_DAYS,
    expired_ladder_rungs,
    outcome_deadline_expired,
)

# The served specimen, market 3484764, read off `/api/feed` at 23:52Z Oct 1.
IRAN = [
    ("September 30", 0.0),
    ("October 31", 0.03),
    ("November 30", 0.06),
    ("December 31", 0.12),
    ("June 30, 2027", 0.24),
]
# Market 60789497 — the year-less shape the parser anchors at year 2000. The
# expiry rule reads NAMES, not that ordering key, so it drops this one too.
SAUDI = [("September 30", 0.0), ("October 15", 0.04), ("October 31", 0.07)]
# Market 112896 — the explicit-year shape.
PUTIN = [("September 30, 2026", 0.0), ("December 31, 2026", 0.03), ("June 30, 2027", 0.08)]


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def test_the_grace_is_twelve_hours():
    assert RUNG_GRACE_DAYS == 0.5


def test_the_served_specimens_lose_september_30_by_morning_pacific():
    # 13:00Z = 6am Pacific on Oct 1. Before #10137 all three kept the rung
    # until 23:59:59Z.
    morning = _utc(2026, 10, 1, 13, 0)
    for board, dead in (
        (IRAN, "September 30"),
        (SAUDI, "September 30"),
        (PUTIN, "September 30, 2026"),
    ):
        assert expired_ladder_rungs(board, morning) == {dead}


def test_the_moment_the_issue_was_photographed_drops_it():
    assert expired_ladder_rungs(IRAN, _utc(2026, 10, 1, 23, 52)) == {"September 30"}


def test_a_us_time_deadline_still_running_keeps_its_rung():
    # "by September 30, 11:59 PM ET" is 03:59Z on Oct 1, and Hawaii's Sep 30
    # ends at 09:59Z. Inside both, the rung is live and stays.
    for clock in (_utc(2026, 10, 1, 3, 59), _utc(2026, 10, 1, 9, 59)):
        assert expired_ladder_rungs(IRAN, clock) == set()
        assert expired_ladder_rungs(PUTIN, clock) == set()


def test_the_boundary_is_noon_utc_the_next_day():
    assert outcome_deadline_expired("September 30", _utc(2026, 10, 1, 11, 59, 59)) is False
    assert outcome_deadline_expired("September 30", _utc(2026, 10, 1, 12, 0, 0)) is True
    # A day-less "Before October" ends at the same instant as "September 30".
    assert outcome_deadline_expired("Before October", _utc(2026, 10, 1, 11, 59, 59)) is False
    assert outcome_deadline_expired("Before October", _utc(2026, 10, 1, 12, 0, 0)) is True


def test_a_rung_that_resolved_on_its_day_is_still_the_answer():
    # Narrowing the grace must not hide a winner: a rung priced at or above the
    # answer floor with a stamp ON its own day keeps its place the next morning.
    board = [
        ("September 30", EXPIRED_RUNG_MAX_PROBABILITY + 0.45, _utc(2026, 9, 30, 21, 0)),
        ("October 31", 0.97, _utc(2026, 9, 30, 21, 0)),
    ]
    assert expired_ladder_rungs(board, _utc(2026, 10, 1, 13, 0)) == set()
