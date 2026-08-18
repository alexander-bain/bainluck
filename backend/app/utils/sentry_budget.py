"""The Sentry volume NUMBERS, derived — never typed (#1894, C-CERT-SENTRY-R3 finding 1).

## What R3 rejected

The policy priced **184.25 events/day** against a quota that affords ~164.5/day.
The defect is not the arithmetic; it is the *shape* of the arithmetic. The old
model computed a priced total and then **asserted** it sat under a budget:

* the budget was a typed literal (``5_000 / 30.4``), so it could be restated;
* the priced total only ever grew by hand-added reserves, so a reserve that
  nobody remembered to add made the assertion pass on an incomplete model — and
  one was in fact missing (``watchdog_ceiling_per_day`` was asserted separately
  and never entered the priced total);
* and an assertion that passes is indistinguishable from an assertion that is
  measuring the wrong thing.

Alex, 2026-08-17: *a comment asserting the inequality is not construction.*

## What this module does instead

Every number below is either **measured** (and carries the measurement) or
**derived from the quota by division**. Nothing here is a tuning knob.

1. **The billing cycle is data, not a mean.** #1894 measured two consecutive
   cycles against Sentry's ``stats_v2``: ``accepted`` resumes on the 21st
   (2026-06-21 and 2026-07-21) and dies mid-cycle both times (07-10 and 07-29).
   So the affordance is ``quota / (days in THIS cycle)`` — 161.29/day for the
   31-day 07-21 -> 08-21 cycle, not the 164.47 a 30.4-day mean asserts. Pricing
   against the mean overspends by 19 events every 31-day cycle.

2. **The budget shrinks as it is spent.** The measured failure mode was ~823
   events/day for eight days followed by twenty-two days of silence. A flat mean
   cannot express that; :func:`remaining_daily_budget` divides what is LEFT by
   the days that remain, so an overspend is visible as a collapsing allowance
   rather than as a month that ends early.

3. **The cap is solved FROM the budget.** :func:`solve_backstop_per_window`
   returns the largest per-signature cap whose complete priced cost fits. The
   filter's ``BACKSTOP_PER_WINDOW`` is that return value. You cannot set the cap
   above affordance because you do not set the cap.

4b. **The blindness ceiling is a function of NEED, not of the plan** (added
   2026-08-17 on Alex's ruling, after ``C-CERT-SENTRY-R4`` refused to arm).
   :func:`discard_ceiling_per_day` is one cycle of :func:`declared_need_per_day`.
   The line it replaces was ``= QUOTA_EVENTS_PER_MONTH``, which was defensible
   only by coincidence: at the 5,000 plan a cycle of need is 4,656/day, so the
   two agreed within 7% and nobody could see which one the reasoning rested on.
   At 50,000 they diverge tenfold and the 19,066/day measured blindness renders
   healthy. Quota now enters in one direction only — as a clamp that can lower
   the ceiling, never raise it.

4. **When nothing fits, it says so by name.** If even cap 1 is unaffordable the
   solve returns 0, :data:`BUDGET_OVERCOMMITTED` goes True, and
   :func:`budget_shortfall_per_day` / :func:`required_monthly_quota` carry the
   size of the gap. The filter then runs at cap 1 anyway — deliberately. Muting
   the fleet to fit a budget would re-break codex finding (b) (every novel
   failure site must send its first event), and a monitoring system that
   protects its bill by going blind has inverted its own purpose. The honest
   state is "over budget, by this much, for this reason", loudly.

## The current reading, and why it is not a test failure

At cap 1 the complete price is ``136.2 (census replay) + 4 (novel-signature
reserve) + 10 (watchdog fail-open ceiling) = 150.2/day``, against 141.94/day
affordable on a 31-day cycle with the 12% floor. **It does not fit, by ~8.3
events/day.** That is R3's finding, reproduced by construction instead of
argued. It closes from either side and both are in flight: Alex's quota raise
(``required_monthly_quota`` = ~5,291 to fit at cap 1, so any plan above 5,000
clears it), and #1894's filter fix, which stops ~19k/day of Celery Beat cron
check-ins being charged to the error category at all.

Nothing here imports anything but the standard library, so it can be read from
``app/utils/sentry_filter.py`` at SDK-init time with zero circular-import risk
(the ``sport_keys.py`` rule).
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone

# =============================================================================
# The quota, and the cycle it is spent over
# =============================================================================

#: Errors per billing month on the current plan. Free Developer (``am3_f``) is
#: 5,000 with on-demand disabled.
#:
#: Environment-overridable ON PURPOSE: a plan change is an operational event, and
#: the whole construction below is a function of this number. Hard-coding it would
#: mean a quota raise silently leaves the caps priced for the old plan — which is
#: the same class of defect as the typed budget it replaces.
QUOTA_EVENTS_PER_MONTH = int(os.getenv("SENTRY_QUOTA_EVENTS_PER_MONTH", "5000"))

#: The billing period rolls on the 21st. MEASURED, not read off an invoice:
#: ``stats_v2`` ``error/accepted`` over 60 days shows the same sawtooth twice —
#: alive 06-21..07-09 then zero to 07-20; alive 07-21..07-28 then zero to 08-20.
BILLING_CYCLE_RESET_DAY = 21

#: Safety floor the priced total must clear, as a fraction of the affordance.
#:
#: Derived rather than chosen — see the long note on ``MIN_SAFE_MARGIN`` in
#: ``tests/fixtures/sentry_formation.py``: it is roughly twice the largest
#: correction the census fixture has ever needed (a 5.6% schema-2 rebuild), so a
#: comparable undiscovered distortion cannot by itself put the policy over quota.
#: Duplicated here because app code cannot import from ``tests/``;
#: ``test_sentry_ceiling_1894.py`` asserts the two never drift apart.
MIN_SAFE_MARGIN = 0.12


def _utc(now: datetime | None) -> datetime:
    """Normalise to aware UTC. Defined here rather than at the foot of the module
    because :data:`BUDGET_OVERCOMMITTED` is computed at import time and would
    otherwise reference it before definition (caught by the first gate run)."""
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def cycle_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """``[start, end)`` of the billing cycle containing ``now``, in UTC.

    Half-open on purpose: the reset day belongs to the cycle it opens, so
    ``cycle_window(Aug 21 00:00)`` starts on Aug 21 rather than ending there.
    """
    now = _utc(now)
    if now.day >= BILLING_CYCLE_RESET_DAY:
        start = now.replace(
            day=BILLING_CYCLE_RESET_DAY, hour=0, minute=0, second=0, microsecond=0
        )
    else:
        prev = now.replace(day=1) - timedelta(days=1)
        start = prev.replace(
            day=BILLING_CYCLE_RESET_DAY, hour=0, minute=0, second=0, microsecond=0
        )
    nxt = (start + timedelta(days=32)).replace(day=1)
    end = nxt.replace(day=BILLING_CYCLE_RESET_DAY, hour=0, minute=0, second=0, microsecond=0)
    return start, end


def cycle_length_days(now: datetime | None = None) -> int:
    """Real length of THIS cycle — 28, 29, 30 or 31. Never a mean."""
    start, end = cycle_window(now)
    return (end - start).days


def days_remaining_in_cycle(now: datetime | None = None) -> float:
    """Days left before the quota resets, floored at a usable fraction.

    Floored rather than allowed to reach zero: on the last afternoon of a cycle
    the true remainder is minutes, and dividing by it would report an allowance
    of tens of thousands per day. A budget instrument that goes euphoric at the
    boundary is worse than no instrument.
    """
    _, end = cycle_window(now)
    remaining = (end - _utc(now)).total_seconds() / 86_400.0
    return max(remaining, 1.0 / 24.0)


def sustainable_daily_budget(now: datetime | None = None) -> float:
    """Events/day the quota affords if spent evenly across THIS cycle."""
    return QUOTA_EVENTS_PER_MONTH / cycle_length_days(now)


def remaining_daily_budget(
    now: datetime | None = None, accepted_this_cycle: int = 0
) -> float:
    """What is still affordable per day, given what has already been spent.

    This is the reset-aware number, and the one that would have made #1894
    visible in week one: at 823/day the eighth day of the cycle reports an
    allowance near zero, which is a statement about the future rather than an
    autopsy.
    """
    left = QUOTA_EVENTS_PER_MONTH - max(0, int(accepted_this_cycle))
    if left <= 0:
        return 0.0
    return min(float(left), left / days_remaining_in_cycle(now))


def affordable_daily_emission(now: datetime | None = None) -> float:
    """The affordance the policy must fit inside, safety floor already taken."""
    return sustainable_daily_budget(now) * (1.0 - MIN_SAFE_MARGIN)


# =============================================================================
# The priced cost of the policy — complete, including the reserve that was
# previously asserted beside the model instead of inside it
# =============================================================================

#: Census replay through the shipped policy, per cap. Worst case (task errors
#: round-robin across the largest prefork pool), 2026-07-21 -> 07-29, schema 2.
#:
#: **Only caps in this table can be solved for, and that is the point.** The
#: replay cost is not linear in the cap — 1 -> 3 costs +20.8/day, and nobody has
#: measured 2, 4 or 8. An earlier draft of this module priced every cap with the
#: cap-1 base, which made a quota raise silently select cap 8 on the strength of
#: a number that had never been measured for cap 8. That is the same confident
#: extrapolation R3 rejected, one level down. An unmeasured cap is *unpriceable*
#: (:func:`priced_daily_total` returns ``inf``) and therefore never selected.
#:
#: ``tests/test_sentry_filter.py::test_measured_volume_worst_case`` owns the
#: cap-1 measurement; ``test_sentry_ceiling_1894.py`` asserts this table still
#: matches it, so a policy change cannot leave the price stale.
CENSUS_REPLAY_PER_DAY = {1: 136.2, 3: 157.0}

#: Convenience alias for the shipped cap's measured base.
CENSUS_REPLAY_PER_DAY_AT_CAP_1 = CENSUS_REPLAY_PER_DAY[1]

#: Largest celery prefork pool (``--concurrency``) in ``backend/Procfile``. A
#: task-side signature can land on any child and each child holds its own
#: throttle table, so a novel task error costs ``cap x children`` per day.
MAX_WORKER_POOL_CHILDREN = 4

#: Children in the pool that runs the watchdog beat (``worker-background``).
WATCHDOG_POOL_CHILDREN = 2

#: The watchdog's emission cooldown is 6h and fleet-shared (Redis SET NX).
WATCHDOG_COOLDOWN_WINDOWS_PER_DAY = 4

#: Distinct ``[alert_class, provider]`` pairs alarming per day (census: 40
#: pair-days over 8 days).
WATCHDOG_PAIRS_PER_DAY = 5

#: Novel signatures the budget must hold room for beyond the census. The census
#: cannot contain tomorrow's bug; pricing zero for it prices the sample.
NOVEL_SIGNATURES_RESERVED = 1


def novel_signature_reserve(cap: int, signatures: int = NOVEL_SIGNATURES_RESERVED) -> int:
    """Events/day held back for signature(s) the census has never seen."""
    return cap * MAX_WORKER_POOL_CHILDREN * signatures


def watchdog_ceiling_per_day(cap: int) -> int:
    """Watchdog events/day under the WORSE of its two shipped states.

    ``_alert_on_cooldown`` fails **open** when Redis is unreachable (deliberate:
    a telemetry-infra failure must never swallow an alarm), so the cooldown
    cannot be assumed to be holding. Both mechanisms are always armed, so the
    honest bound is the tighter of the two.

    This is the reserve that R3 found missing from the priced total. It was
    asserted in its own test, beside the model, where it could not affect the
    number the model produced.
    """
    return WATCHDOG_PAIRS_PER_DAY * min(
        WATCHDOG_COOLDOWN_WINDOWS_PER_DAY, cap * WATCHDOG_POOL_CHILDREN
    )


def priced_daily_total(cap: int, base_per_day: float | None = None) -> float:
    """Complete events/day the policy costs at ``cap``. No reserve left outside.

    Returns ``inf`` for a cap whose replay cost has never been measured, so an
    unpriceable cap can never win the search. Pass ``base_per_day`` explicitly to
    price a hypothetical fleet (the what-if the tests sweep over).
    """
    base = CENSUS_REPLAY_PER_DAY.get(cap) if base_per_day is None else base_per_day
    if base is None:
        return float("inf")
    return base + novel_signature_reserve(cap) + watchdog_ceiling_per_day(cap)


# =============================================================================
# The construction: the cap is a FUNCTION OF the budget
# =============================================================================

#: The caps the search may consider — exactly the measured ones, ascending.
SOLVABLE_CAPS = tuple(sorted(CENSUS_REPLAY_PER_DAY))

#: The cap the filter runs at when nothing is affordable. Never 0: muting the
#: fleet to fit a bill re-breaks codex finding (b) (every novel failure site must
#: send its first event) and inverts the purpose of the instrument.
MINIMUM_VIABLE_CAP = 1


def solve_backstop_per_window(
    now: datetime | None = None,
    base_per_day: float | None = None,
) -> int:
    """Largest per-signature cap whose COMPLETE priced cost fits the affordance.

    Returns **0** when even :data:`MINIMUM_VIABLE_CAP` is unaffordable. Zero is a
    verdict, not a cap — callers run at :data:`MINIMUM_VIABLE_CAP` and surface
    :func:`budget_shortfall_per_day`.
    """
    budget = affordable_daily_emission(now)
    best = 0
    for cap in SOLVABLE_CAPS:
        if priced_daily_total(cap, base_per_day) <= budget:
            best = cap
    return best


def effective_backstop_per_window(
    now: datetime | None = None,
    base_per_day: float | None = None,
) -> int:
    """The cap actually used: the solve, floored at :data:`MINIMUM_VIABLE_CAP`."""
    return max(MINIMUM_VIABLE_CAP, solve_backstop_per_window(now, base_per_day))


def budget_shortfall_per_day(
    now: datetime | None = None,
    base_per_day: float | None = None,
) -> float:
    """Events/day by which the policy exceeds its affordance. 0.0 when it fits."""
    over = priced_daily_total(
        effective_backstop_per_window(now, base_per_day), base_per_day
    ) - affordable_daily_emission(now)
    return max(0.0, round(over, 2))


def required_monthly_quota(
    now: datetime | None = None,
    base_per_day: float | None = None,
) -> int:
    """Smallest monthly quota under which the policy fits at the viable cap.

    The number to quote when asking for a plan change: it converts "we are over"
    into "buy this much and we are not".
    """
    need_per_day = priced_daily_total(
        effective_backstop_per_window(now, base_per_day), base_per_day
    )
    return math.ceil(need_per_day / (1.0 - MIN_SAFE_MARGIN) * cycle_length_days(now))


def fleet_emission_ceiling(
    now: datetime | None = None,
    base_per_day: float | None = None,
) -> float:
    """Priced events/day at the SOLVED cap.

    Bounded by :func:`affordable_daily_emission` by construction whenever the
    solve found a cap at all — that is what :func:`solve_backstop_per_window`
    searches for. When it found none, this reports the ceiling at the minimum
    viable cap, which is the honest over-budget number rather than a fiction.
    """
    return priced_daily_total(
        effective_backstop_per_window(now, base_per_day), base_per_day
    )


def budget_verdict(
    now: datetime | None = None,
    base_per_day: float | None = None,
) -> dict:
    """One readable dict: the affordance, the price, the gap, and what closes it.

    A number without its verdict gets read as whatever the reader already
    believed (gotcha #53), so the shortfall never travels without ``fits``.
    """
    solved = solve_backstop_per_window(now, base_per_day)
    cap = max(MINIMUM_VIABLE_CAP, solved)
    return {
        "cycle_days": cycle_length_days(now),
        "quota_per_month": QUOTA_EVENTS_PER_MONTH,
        "sustainable_per_day": round(sustainable_daily_budget(now), 2),
        "affordable_per_day": round(affordable_daily_emission(now), 2),
        "priced_per_day": round(priced_daily_total(cap, base_per_day), 2),
        "backstop_per_window": cap,
        "solved_cap": solved,
        "fits": solved >= MINIMUM_VIABLE_CAP,
        "shortfall_per_day": budget_shortfall_per_day(now, base_per_day),
        "required_monthly_quota": required_monthly_quota(now, base_per_day),
        "margin_floor": MIN_SAFE_MARGIN,
    }


# ---------------------------------------------------------------------------
# Boundary-aware accessors (C-CERT-SENTRY-R4 finding P1, queue 363)
#
# Every function above derives cycle length from the timestamp it is handed, and
# is therefore correct. The defect Codex found is one level up: the filter
# FROZE two of them at import (``BACKSTOP_PER_WINDOW``, ``BUDGET_VERDICT``), and
# a dyno outlives a billing cycle. Its specimen: a process imported during a
# 28-day cycle at quota 5,000 kept exporting ``fits: true, shortfall: 0,
# cycle_days: 28`` after the next 31-day cycle opened, while a fresh calculation
# said ``fits: false, shortfall: 8.26, cycle_days: 31``. The transition itself
# smooths away the shortfall the acceptance requires — a false green produced by
# the calendar rather than by anything changing.
#
# Recomputing per event is not an option: the cap is read on the hot path and
# the solve is a search. So the accessors below memoise on the CYCLE, which is
# the only thing the answer depends on: a cheap date comparison per call, and a
# re-solve exactly once per boundary crossing.
# ---------------------------------------------------------------------------

_CACHE: dict = {"key": None, "cap": None, "verdict": None}


def cycle_key(now: datetime | None = None) -> str:
    """Identity of the billing cycle containing ``now``. The memo key."""
    start, end = cycle_window(now)
    return f"{start.date().isoformat()}:{(end - start).days}:{QUOTA_EVENTS_PER_MONTH}"


def _refresh(now: datetime | None = None) -> None:
    key = cycle_key(now)
    if _CACHE["key"] == key:
        return
    _CACHE["key"] = key
    _CACHE["cap"] = effective_backstop_per_window(now)
    _CACHE["verdict"] = budget_verdict(now)


def current_backstop_per_window(now: datetime | None = None) -> int:
    """The cap in force RIGHT NOW, re-solved on a cycle boundary.

    Read on the hot path, so it must stay cheap: one date comparison in the
    common case.
    """
    _refresh(now)
    return int(_CACHE["cap"])


def current_budget_verdict(now: datetime | None = None) -> dict:
    """The exported verdict, re-derived on a cycle boundary.

    Returns a copy: the exported dict travels into counter payloads, and a
    caller mutating the cache would make the next reader's verdict a function of
    who read it first.
    """
    _refresh(now)
    return dict(_CACHE["verdict"])


#: True when the policy costs more than the quota affords at every searched cap.
#: Read at import by ``app/utils/sentry_filter.py``, which logs it CRITICAL once
#: — the "loudly" half of "impossible or loudly impossible".
BUDGET_OVERCOMMITTED = solve_backstop_per_window() < MINIMUM_VIABLE_CAP


# =============================================================================
# The DISCARD ceiling — Finding 2's declared, observable number
# =============================================================================

def declared_need_per_day(
    now: datetime | None = None,
    base_per_day: float | None = None,
) -> float:
    """Events/day the policy DECLARES it needs to keep, at the solved cap.

    This is :func:`priced_daily_total` under the name that says what it is FOR.
    It is a statement about how much of production we have decided we must be
    able to see — which is the only quantity a blindness ceiling can honestly be
    a function of.
    """
    return priced_daily_total(
        effective_backstop_per_window(now, base_per_day), base_per_day
    )


#: The ceiling must sit under this share of the monthly quota to count as "well
#: under" it. NOT a tuning knob and NOT the deriver — a *verdict threshold*:
#: :func:`discard_ceiling_verdict` reports the share and whether it clears this,
#: so "well under quota" is an observable property rather than an assumption.
CEILING_WELL_UNDER_QUOTA_SHARE = 0.5


def discard_ceiling_per_day(
    now: datetime | None = None,
    base_per_day: float | None = None,
) -> int:
    """Discards/day above which the filter has stopped being a budget instrument
    and become a blindfold.

    **Derived from declared NEED, never from raw quota** (Alex, 2026-08-17).

    One CYCLE of declared need. The reasoning the original constant had right:
    if we destroy in ONE DAY more than a MONTH of the traffic we declared we must
    be able to see, what we are discarding is no longer "noise we decided not to
    pay for" — it is the shape of production, unread. The reasoning it had wrong
    was the noun. It used the monthly *quota* as the stand-in for a month of
    need, and at the 5,000-event plan those two numbers happened to coincide
    within 7% (a cycle of need is 4,656/day; the quota was 5,000). **That
    coincidence is the entire reason the coupling survived review** — and it
    dissolved the moment the plan changed: at 50,000/month the same line derives
    a 50,000/day ceiling, under which the measured 19,066/day blindness specimen
    renders healthy. A ceiling that a plan upgrade raises tenfold is not a
    ceiling; it is a budget restated in the wrong units. ``C-CERT-SENTRY-R4``
    refused to arm on exactly this.

    Quota now enters in one direction only, as a hard clamp: the ceiling may
    never EXCEED the monthly quota, because past that point it has stopped
    bounding anything. It is deliberately not clamped at a *fraction* of quota —
    a fractional clamp is still a quota-derived ceiling on every occasion it
    binds, and at today's 5,000 default it would bind immediately, reinstating
    the coupling this function exists to remove. Whether the result is
    comfortably under quota is therefore *reported*
    (:func:`discard_ceiling_verdict`), not silently enforced.

    Measured, both plans, 31-day cycle:

    ==============  ==========  ================  ====================
    quota/month     ceiling/day  19,066/day        64,039/day (R3)
    ==============  ==========  ================  ====================
    5,000           4,656        over (4.1x)       over (13.8x)
    50,000          5,859        over (3.3x)       over (10.9x)
    ==============  ==========  ================  ====================

    A tenfold quota raise moves the ceiling 1.26x — it moves at all only because
    the solved cap rises with affordance, which is need genuinely increasing.
    """
    need_per_cycle = declared_need_per_day(now, base_per_day) * cycle_length_days(now)
    return int(min(math.ceil(need_per_cycle), QUOTA_EVENTS_PER_MONTH))


def discard_ceiling_verdict(
    now: datetime | None = None,
    base_per_day: float | None = None,
) -> dict:
    """The ceiling with the reading that keeps it honest.

    A ceiling handed over without whether it is *bounding* anything gets read as
    whatever the reader already believed — the same gotcha #53 shape that let a
    50,000/day ceiling pass as a ceiling.
    """
    ceiling = discard_ceiling_per_day(now, base_per_day)
    share = ceiling / QUOTA_EVENTS_PER_MONTH if QUOTA_EVENTS_PER_MONTH else float("inf")
    return {
        "ceiling_per_day": ceiling,
        "declared_need_per_day": round(declared_need_per_day(now, base_per_day), 2),
        "cycle_days": cycle_length_days(now),
        "quota_per_month": QUOTA_EVENTS_PER_MONTH,
        "share_of_quota": round(share, 4),
        "well_under_quota": share < CEILING_WELL_UNDER_QUOTA_SHARE,
        "clamped_by_quota": ceiling == QUOTA_EVENTS_PER_MONTH,
        "derived_from": "declared_need_per_day * cycle_days",
    }


#: Import-time reading, kept as a name because ``sentry_filter`` reads it on the
#: exception path where a function call per event is not free. Recomputed by
#: :func:`discard_ceiling_per_day` for any caller that has a ``now``.
DISCARD_CEILING_PER_DAY = discard_ceiling_per_day()


def over_discard_ceiling(
    discarded: int, window_s: float, now: datetime | None = None
) -> bool:
    """True when the discard RATE breaches the ceiling.

    Rate, never count: a count handed over without the window that makes it a
    rate is not a measurement (the LAT-P024 reason), and a process that has been
    up for ten minutes would otherwise look healthier than one up for a day
    purely by being younger.

    Derives the ceiling LIVE rather than reading the import-time constant. The
    constant freezes the cycle length at whatever it was when the dyno booted,
    and a web dyno routinely outlives a billing cycle — so a February boot would
    carry a 28-day ceiling into a 31-day cycle and quietly under-report. Cheap
    to do: this runs once per census read, not once per event.
    """
    if window_s <= 0:
        return False
    return (discarded * 86_400.0 / window_s) > discard_ceiling_per_day(now)
