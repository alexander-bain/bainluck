"""How long Kalshi keeps a settled market's price history — measured, not assumed.

CAL-P008 (#683). Gotcha #35 has said "~2-3 months" since May; that range was never
dated, so nothing in the code could act on it. This module turns it into a measured
constant with a re-runnable probe (``scripts/probe_kalshi_retention.py``), so the
horizon is falsifiable rather than folklore.

MEASUREMENT (2026-08-07, live public Kalshi API, no auth):

    settled          age    GET /markets/{ticker}   GET /markets/trades
    ---------------------------------------------------------------------
    2026-03-01..24   ~140d  404 x16                 200, 0 trades  x16
    2026-04-12..29   ~105d  404 x4                  200, 0 trades  x4
    2026-05-10..13    ~86d  404 x3                  200, 0 trades  x3
    2026-05-25..27    ~74d  200 x3                  200, 100 trades x3
    2026-06-19..27    ~45d  200 x3                  200, 100 trades x3
    2026-07-08..22    ~20d  200 x4                  200, 100/11/0 trades

So retention is at least 74 days and less than 86. Both bounds are kept below,
because which one is correct depends on the question being asked:

* **Skipping work** must use the UPPER bound. Only refuse to fetch a market that is
  *provably* gone; a row in the uncertain 74–86 day band is still tried. Fail-open:
  we would rather spend a wasted call than silently abandon a recoverable price.
* **Warning** must use the LOWER bound, so the alarm fires while there is still time
  to act rather than on the day the data dies.

THE TRAP THIS ENCODES. ``GET /markets/trades`` answers **HTTP 200 with an empty
list** for a market that no longer exists — it does not 404. So "no trades came
back" is not evidence about trading; it is not evidence about anything. Only the
market lookup distinguishes *purged upstream* from *genuinely never traded*, and
the two must never be conflated: the second is a fact about the market, the first
is a fact about Kalshi's retention policy.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

#: Oldest age (days) at which a settled market was still fully retrievable.
OBSERVED_PRESENT_MAX_AGE_DAYS = 74

#: Youngest age (days) at which a settled market was already purged.
OBSERVED_PURGED_MIN_AGE_DAYS = 86

#: Skip-work horizon. A settled market older than this is provably unreachable, so
#: fetching it can only waste budget. Deliberately the UPPER observed bound.
PROVABLY_PURGED_AGE_DAYS = OBSERVED_PURGED_MIN_AGE_DAYS

#: Warning horizon. Past this age a price may vanish at any time. Deliberately the
#: LOWER observed bound, so the warning precedes the loss.
AT_RISK_AGE_DAYS = OBSERVED_PRESENT_MAX_AGE_DAYS

#: Date the table above was measured. Re-run the probe and update both bounds
#: together; never widen one alone.
MEASURED_ON = "2026-08-07"


def _age_days(settled_at: datetime | None, now: datetime | None = None) -> float | None:
    """Age of a settlement in days, or None when it cannot be established."""
    if settled_at is None:
        return None
    now = now or datetime.now(timezone.utc)
    if settled_at.tzinfo is None:
        settled_at = settled_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - settled_at).total_seconds() / 86400.0


def is_provably_purged(settled_at: datetime | None, now: datetime | None = None) -> bool:
    """True only when Kalshi is *known* to no longer hold this market's prices.

    Fail-open by design: an unknown settlement time returns False, so a row with no
    date is still attempted rather than written off. A row this returns True for can
    be skipped without losing anything — every probe at this age came back 404.
    """
    age = _age_days(settled_at, now)
    return age is not None and age >= PROVABLY_PURGED_AGE_DAYS


def days_until_purge(settled_at: datetime | None, now: datetime | None = None) -> float | None:
    """Days of recovery time left before the price is expected to vanish.

    Measured against the LOWER bound, so it reaches 0 while the data is very likely
    still there. Negative means the window has already closed. None when unknown.
    """
    age = _age_days(settled_at, now)
    return None if age is None else AT_RISK_AGE_DAYS - age


def is_at_risk(
    settled_at: datetime | None,
    now: datetime | None = None,
    within_days: float = 14.0,
) -> bool:
    """True when a still-recoverable price is close enough to expiry to be urgent.

    Already-purged rows are NOT at risk — nothing is left to lose. This is the
    early-warning predicate: the population it counts is exactly the population a
    stalled backfill is about to turn into permanent loss.
    """
    remaining = days_until_purge(settled_at, now)
    if remaining is None:
        return False
    return -(PROVABLY_PURGED_AGE_DAYS - AT_RISK_AGE_DAYS) < remaining <= within_days


def recovery_window_start(now: datetime | None = None) -> datetime:
    """Earliest settlement time still worth fetching (the skip-work boundary)."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now - timedelta(days=PROVABLY_PURGED_AGE_DAYS)
