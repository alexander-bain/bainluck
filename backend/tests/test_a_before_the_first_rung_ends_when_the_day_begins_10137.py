"""#10137 sibling arm — "Before Oct 1" ends when Oct 1 BEGINS, not when it ends.

ux's 390px walk of /politics at 11:07Z on 2026-10-02 found three cards still
headlining `Before Oct 1, 2026 · 0%` (11617619 Gallego, 59693689 Lake America,
52755865 Khamenei). Kalshi closed `KXGALLEGOOUT-26OCT01` at 03:59Z Oct 1 and
settled it NO at 13:44Z. The month-day arm of `_named_deadline` dated the rung
to 23:59:59Z OF Oct 1, so with the 12h grace it stayed until 12:00Z Oct 2 —
31 hours past the venue's close. The day-less arm already read "before" as
exclusive ("Before July" is June 30); the month-day arm now does the same.

Clocks are fixed instants (gotcha #44); each arm asserts both directions.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.utils.market_staleness import (
    _named_deadline,
    expired_ladder_rungs,
    outcome_deadline_expired,
)


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


# Gallego's board as served on /api/politics at 10:25Z Oct 2.
GALLEGO = [
    ("Before Oct 1, 2026", 0.0),
    ("Before Nov 1, 2026", 0.02),
    ("Before Jan 1, 2027", 0.05),
]


def test_the_served_specimen_leaves_by_morning_on_the_first():
    # 13:00Z Oct 1 = 6am Pacific, after the venue closed at 03:59Z.
    morning = _utc(2026, 10, 1, 13, 0)
    assert expired_ladder_rungs(GALLEGO, morning) == {"Before Oct 1, 2026"}
    # ux's exact read: still up at 11:00Z Oct 2 before the fix.
    assert outcome_deadline_expired("Before Oct 1, 2026", _utc(2026, 10, 2, 11, 0))


def test_the_rung_stays_until_every_us_clock_has_closed_the_day_before():
    # 09:59Z Oct 1 is 11:59pm Sep 30 in Hawaii — the rung can still happen.
    assert not outcome_deadline_expired("Before Oct 1, 2026", _utc(2026, 10, 1, 9, 59))
    assert outcome_deadline_expired("Before Oct 1, 2026", _utc(2026, 10, 1, 12, 0, 1))


@pytest.mark.parametrize("word", ["Before", "Prior to", "Earlier than", "before"])
def test_every_exclusive_word_dates_the_day_before(word):
    deadline, explicit = _named_deadline(f"{word} Oct 1, 2026", _utc(2026, 9, 1))
    assert deadline == _utc(2026, 9, 30, 23, 59, 59)
    assert explicit is True


@pytest.mark.parametrize(
    "name", ["By Oct 1, 2026", "On or before Oct 1, 2026", "Oct 1, 2026", "Through Oct 1, 2026"]
)
def test_inclusive_words_keep_the_named_day(name):
    deadline, _ = _named_deadline(name, _utc(2026, 9, 1))
    assert deadline == _utc(2026, 10, 1, 23, 59, 59)
    # So they are still on the board at 13:00Z Oct 1, unlike "Before".
    assert not outcome_deadline_expired(name, _utc(2026, 10, 1, 13, 0))


def test_the_day_before_crosses_month_and_year_boundaries():
    assert _named_deadline("Before Jan 1, 2027", _utc(2026, 9, 1))[0] == _utc(2026, 12, 31, 23, 59, 59)
    assert _named_deadline("Before Mar 1, 2028", _utc(2026, 9, 1))[0] == _utc(2028, 2, 29, 23, 59, 59)


def test_a_range_rung_keeps_its_closing_day():
    # #7274: a range is dated by its END; "before" in front does not shift it.
    deadline, _ = _named_deadline("Before September 15 - 30, 2026", _utc(2026, 9, 1))
    assert deadline == _utc(2026, 9, 30, 23, 59, 59)


def test_a_yes_rung_resolved_on_the_last_day_is_still_the_answer():
    # Stamped during Sep 30 — the day the "Before Oct 1" deadline arrives.
    board = [("Before Oct 1, 2026", 0.99, "2026-09-30T18:00:00+00:00"), ("Before Nov 1, 2026", 0.99)]
    assert expired_ladder_rungs(board, _utc(2026, 10, 2, 0, 0)) == set()
    # A forecast stamped days before the deadline is not an answer.
    stale = [("Before Oct 1, 2026", 0.9, "2026-09-20T18:00:00+00:00")]
    assert expired_ladder_rungs(stale, _utc(2026, 10, 2, 0, 0)) == {"Before Oct 1, 2026"}


def test_not_before_is_never_moved_earlier():
    # "Not before Oct 1" is the opposite claim; it keeps the day it names.
    deadline, _ = _named_deadline("Not before Oct 1, 2026", _utc(2026, 9, 1))
    assert deadline == _utc(2026, 10, 1, 23, 59, 59)
