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
#:
#: **A SURVIVOR OBSERVATION, NOT A FLOOR.** Re-measurement on 2026-08-24 proved a
#: younger sibling can already be purged while this one is present, so this number
#: describes the markets it was measured on and nothing else. It must not drive
#: warning or capture policy; see the 2026-08-24 section below.
OBSERVED_PRESENT_MAX_AGE_DAYS = 74

#: Youngest age (days) at which a settled market was already purged.
OBSERVED_PURGED_MIN_AGE_DAYS = 86

#: Skip-work horizon. A settled market older than this is provably unreachable, so
#: fetching it can only waste budget. Deliberately the UPPER observed bound.
PROVABLY_PURGED_AGE_DAYS = OBSERVED_PURGED_MIN_AGE_DAYS

#: Warning horizon. Past this age a price may vanish at any time, so the warning
#: precedes the loss.
#:
#: 2026-08-24: was ``OBSERVED_PRESENT_MAX_AGE_DAYS`` (74), which the re-measurement
#: showed fires 27 days AFTER the first confirmed loss — an alarm that rings once the
#: data is already gone. Now the youngest CONFIRMED purge. Written as a literal
#: because :data:`OBSERVED_PURGED_MIN_AGE_DAYS_ANY_SERIES` is defined below; the two
#: are held equal by a guard test rather than by a reader's attention.
AT_RISK_AGE_DAYS = 47

#: Date the table above was measured. Re-run the probe and update both bounds
#: together; never widen one alone.
#:
#: 2026-08-07 measured the four-series table above. 2026-08-24 re-measured the
#: POPULATION (3,242 distinct Kalshi capture records + public-API boundary
#: confirmation) and is the date the constants below act on.
MEASURED_ON = "2026-08-24"


# ---------------------------------------------------------------------------
# 2026-08-21 — A COUNTER-SPECIMEN, and why it gets its own constant
# ---------------------------------------------------------------------------
#
# C-WINNER-TRUTH-2 probed market ``KXITFMATCH-26JUN14FONSZA`` at age **68 days**
# and got ``event_found_markets_empty`` — the purge shape. That is INSIDE the
# 74-day bound above, which claims 74d was still fully retrievable.
#
# The two readings are not actually in conflict, and the difference matters:
# ``OBSERVED_PRESENT_MAX_AGE_DAYS`` was measured on four high-volume series
# (KXNBAPTS/KXNHL/KXMLBHRR/KXNASDAQ100U). The counter-specimen is a low-volume ITF
# tennis match. So retention is very likely **not uniform across series**, and 74
# is the bound for the series it was measured on, not for the population.
#
# The honest response is NOT to retune the measured constants — they record a real
# measurement over a stated population, and quietly moving 74 to 68 would destroy
# that record while making the new number look equally well-founded. Instead the
# planning horizon gets its own name, its own value, and its own evidence, so a
# reader can see that one is measured and the other is chosen.

#: Age (days) of the youngest market ever observed purged. Falsifies nothing about
#: the four-series measurement above; it bounds the POPULATION rather than a series.
#:
#: 2026-08-24: was 68, **falsified at 47** by C-KALSHI-RETENTION-1 (see below).
OBSERVED_PURGED_MIN_AGE_DAYS_ANY_SERIES = 47

#: Series the counter-specimen came from, so the next measurement knows where to look.
COUNTER_SPECIMEN = (
    "KXNBAPLAYOFFWINS-26BOS (purged at 47d, 2026-08-24; market 404 + event 200 "
    "markets:[] through the shipping two-channel classifier). Prior specimen: "
    "KXITFMATCH-26JUN14FONSZA (ITF tennis, purged at 68d, 2026-08-21)."
)


# ---------------------------------------------------------------------------
# 2026-08-24 — RETENTION IS NON-MONOTONIC, AND AGE PROVES NOTHING
# ---------------------------------------------------------------------------
#
# C-KALSHI-RETENTION-1 (BLOCK) re-measured the population and broke the shape this
# module was built on. The finding is not "the number was wrong by 21 days"; it is
# that **no single age threshold can describe the population at all**:
#
#   * A market-level purge is CONFIRMED at 47 days, through the shipping
#     two-channel classifier, not a bare 404 (market 404 + event 200/markets:[]).
#   * Retention is non-monotonic INSIDE one series. `KXATPGTOTAL` has a purged
#     54-day market while a 68-day sibling is still present with trades.
#     `KXMLBRFI` has a purged 66-day market and a present 64-day one.
#   * Therefore "the oldest market still present" is NOT a lower bound on
#     retention. It is a survivor observation. A younger sibling can already be
#     permanently gone.
#
# WHAT THAT DOES TO THE CONSTANTS ABOVE. ``OBSERVED_PRESENT_MAX_AGE_DAYS`` (74)
# survives only as a survivor observation and must never again drive warning or
# capture policy. The 86-day skip-work pair is untouched: every definitive read at
# 85-86d was purged, so refusing to spend a call there is still fail-open, and the
# evidence does not refute it.
#
# THE CLAUSE THAT REPLACES THE HORIZON:
#
#     **Age prioritizes work. It never proves availability.**
#
# Both directions of that sentence are load-bearing, and the second one is why
# lowering the number below is not sufficient on its own. The report says so
# explicitly: "the safe operational conclusion is not 'change 66 to 45 and trust
# the new number'." A planner that reads a past-horizon row as *unsalvageable*
# gets WORSE as this constant drops, because every additional row it writes off is
# a row the measurement just proved might still be there. So this constant moving
# to 45 is paired with the ordering fix in ``settlement_sweep_plan`` that makes
# "past the horizon" mean MAXIMUM URGENCY rather than "expired, sorts last".
# Neither half is safe alone.

#: Whether a single age can be used as a retention bound. It cannot. Kept as a
#: named constant rather than prose so a predicate can consume it (gotcha #35).
RETENTION_IS_MONOTONIC = False

#: **A work-prioritization anchor, NOT an availability guarantee.** Derived from the
#: 47-day confirmed purge with the same two-day margin the old 66 used, so the
#: derivation is auditable — but the margin is now the least interesting thing about
#: it. Because retention is non-monotonic, a row INSIDE this horizon may already be
#: gone and a row well outside it may still be fully retrievable.
#:
#: It answers exactly one question: "which rows should we spend the next call on
#: first". It answers NEITHER "is this row still there" NOR "is this row worth a
#: call" — the second belongs to :data:`PROVABLY_PURGED_AGE_DAYS` (86), which is the
#: only constant here permitted to STOP work.
CAPTURE_PLANNING_AGE_DAYS = OBSERVED_PURGED_MIN_AGE_DAYS_ANY_SERIES - 2


def capture_deadline_days(settled_at: datetime | None, now: datetime | None = None) -> float | None:
    """Days left to CAPTURE this settlement before planning says it is unsafe.

    Distinct from :func:`days_until_purge`, which answers whether a price is likely
    still fetchable. This answers whether we should have already fetched it. A
    negative value means the sweep is late, not that the market is gone — the fetch
    is still attempted, because :func:`is_provably_purged` (the 86-day upper bound)
    is what governs skipping.
    """
    age = _age_days(settled_at, now)
    return None if age is None else CAPTURE_PLANNING_AGE_DAYS - age


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
