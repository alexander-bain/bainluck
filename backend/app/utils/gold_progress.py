"""How far the gold set has come, and whether it is SPREAD (UX-P117, #2060 item 4).

── THE NUMBER THE METER EXISTS TO SHOW IS NOT THE TOTAL ─────────────────────────

Labelling twenty cards a day is easy to display and easy to game. The gold set's
actual requirement is **temporal spread**, because the thing being sampled changes
underneath the sampler: the Discover slate turns over daily, so 250 labels
collected in two sittings are 250 opinions about two slates. UX-P116 hit the same
property from the other side — its #2084 re-measure could not reproduce P114's
414-event population ten hours later because 98% of the window had turned over.

So the streak is not gamification bolted onto a counter. It is the requirement
made visible, and it is the leg most likely to be failing silently: measured on
production 2026-08-21 the corpus is **88 rows across 6 distinct days**, and two of
those days are 2026-05-24/25 — a **77-day silence** sits in the middle of it
(the same gap ``FLIP_WINDOW_DAYS`` was sized against).

── DAYS ARE PACIFIC, AND THIS IS THE WHOLE REASON THIS FILE TAKES A TIMEZONE ────

Alex labels in the evening. A "today" bucketed in UTC rolls over at 5pm PT, so an
8pm session would show as tomorrow's count, today's would read zero, and the
streak would break on a night he actually worked. A progress meter that reports
zero on a day of real work is worse than no meter — it is the instrument telling
him to stop.

── PURE, FOR THE REASON ``flip_readiness`` IS PURE ──────────────────────────────

The streak is the interesting computation and it has edge cases (a gap of exactly
one day, a streak that ended yesterday and is still alive, a future-dated row).
None of them need a database to be settled, and gotcha #44 says a test that has to
seed dates against a live clock is a test that will go red on a schedule. The
caller hands in a set of day strings and ``today``; everything here is arithmetic.
"""

from __future__ import annotations

from datetime import date, timedelta
from math import ceil
from typing import Iterable

#: Cards per session. Alex's own figure in the #2060 package ("today's count vs
#: ~20"), and consistent with ``FLIP_MIN_BOUND`` — 20 is well inside one real
#: session's output (52 rows landed in a single ten-day stretch).
GOLD_DAILY_TARGET = 20

#: The corpus size ruling 016 is blocked on. Alex's figure in the same package.
GOLD_TOTAL_TARGET = 250


def gold_spread_target(
    total_target: int = GOLD_TOTAL_TARGET,
    daily_target: int = GOLD_DAILY_TARGET,
) -> int:
    """The number of distinct labelling days the target pace implies.

    DERIVED, not chosen: at ``daily_target`` a day, ``total_target`` takes
    ``ceil(250/20) = 13`` days. Stating it as a constant would invite arguing
    about it; stating it as a consequence of the two numbers Alex gave means it
    moves when they move.

    A corpus that reached its total in materially fewer days did not beat the
    target — it over-sampled a handful of slates, which is the failure the spread
    leg exists to catch.
    """
    if daily_target <= 0:
        return 0
    return ceil(total_target / daily_target)


def current_streak(days: Iterable[str], *, today: date) -> int:
    """Consecutive labelling days ending today or yesterday.

    ** YESTERDAY COUNTS AS ALIVE. ** A streak that ran through last night is not
    broken at 9am — the day is not over. Ending the streak at midnight would show
    Alex a zero every morning for work he did eight hours earlier, and the first
    thing a person does with a counter that lies is stop reading it.

    Future-dated days are ignored rather than counted or treated as an error: a
    clock-skewed client can post one, and neither crashing a progress meter nor
    awarding a streak for it is right.
    """
    labelled = {d for d in days if d}
    if not labelled:
        return 0

    anchor = today
    if today.isoformat() not in labelled:
        anchor = today - timedelta(days=1)
        if anchor.isoformat() not in labelled:
            return 0

    streak = 0
    cursor = anchor
    while cursor.isoformat() in labelled:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def gold_progress(
    *,
    total: int,
    today_count: int,
    days: Iterable[str],
    today: date,
    daily_target: int = GOLD_DAILY_TARGET,
    total_target: int = GOLD_TOTAL_TARGET,
) -> dict:
    """The three numbers the labelling header shows, plus the spread verdict.

    Every leg carries its own ``met`` flag rather than being folded into one
    percentage, for ``flip_readiness``' reason: a single number tells nobody
    which leg to go work on, and here the interesting failure (a big corpus from
    three sittings) and the healthy state (a small corpus growing daily) produce
    almost the same percentage.
    """
    distinct = sorted({d for d in days if d})
    spread_target = gold_spread_target(total_target, daily_target)
    return {
        "total": total,
        "total_target": total_target,
        "total_met": total >= total_target,
        "today": today_count,
        "daily_target": daily_target,
        "daily_met": today_count >= daily_target,
        "distinct_days": len(distinct),
        "spread_target": spread_target,
        # The leg that is easy to pass by accident and easy to fail invisibly.
        "spread_met": len(distinct) >= spread_target,
        "streak": current_streak(distinct, today=today),
        "first_day": distinct[0] if distinct else None,
        "last_day": distinct[-1] if distinct else None,
    }
