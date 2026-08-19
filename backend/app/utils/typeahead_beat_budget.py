"""Derive which `warm-typeahead` beat intervals are reachable, and refuse the rest.

LAT-P072 (#1609, #1866). Fable's LAT-P072 item 2 rules the first W-move:
**`warm_typeahead`'s beat from 10 s to 60 s** — it is 72.0 % of everything published
into the `background` queue and ~82 % of its fires are 10-millisecond no-ops, so the
cut reads as nearly free.

**The arrival half of that reasoning is correct and is not disputed here.** What this
module adds is the half the arrival arithmetic cannot see: the beat interval is not
only a publish rate, it is also the **quantiser of the warmer's pass period**, and the
pass period is measured against a hard 45-second cliff. Cutting the publish rate with
this lever necessarily moves the period, and at 60 s it moves it over the cliff on
every single pass.

So this module exists for the same reason `turbo_collapse_budget.py` does, and it is
the same ruling-075 shape: a change derived from a measurement may not be shipped past
that measurement's own floor, and where the derivation refuses, the refusal is the
output — never a default number, never a rounded compromise.

## The cliff, and it is measured rather than reasoned

`/api/events/typeahead` writes its response cache with a **45-second** TTL
(`routes/events.py`, `setex(_cache_key, 45, ...)`; pinned below by `RESPONSE_CACHE_TTL_S`
and by a mirror-drift test). LAT-P063 ran a paired W sweep and graded every pass:

> 20 passes, **every** pass with `period_s > 45` lost entries (up to 39 of 40) and
> **not one** pass under 45 s lost any — 20 for 20. Crossing the TTL does not degrade
> the head gradually. It empties it.
> — `docs/audits/latency/lat-p063-wsweep-graded.md`

That is the whole safety property. It is a step function with a measured location, not
a gradient, so "a bit over" is not a bit worse — it is the failure.

## The arithmetic the arrival share cannot see

A pass may only START on a beat fire, and only if `MIN_PASS_PERIOD_SECONDS` has elapsed
since the last start (the floor) and the run-lock is free. So the period is the beat
interval **quantised up**:

    P(B) = B * ceil(max(measured_wall, MIN_PASS_PERIOD_SECONDS) / B)

This is not a model; it is what LAT-P062 measured when it removed the 30 s beat. At
B = 30 against a ~31 s wall, every other beat skipped and the period quantised up to
~60 s — measured duty cycle 17.5 of 24, period straddling the TTL. Shortening the beat
to 10 s is what un-quantised it.

Read the other way, the same equation says a LONGER beat re-quantises it, and the
coarser the beat the coarser the quantisation:

| B | P at the median wall (32.0 s) | P at the worst measured wall (42.6 s) |
|---|---|---|
| 10 s (today) | 40 s | **50 s** |
| 22 s | 44 s | 44 s |
| 30 s | **60 s** | **60 s** |
| **60 s (proposed)** | **60 s** | **60 s** |

**At B = 60 the period is 60 s for every reachable wall** — the quantiser has become
coarser than the whole distribution, so there is no branch in which a pass lands under
45 s. By LAT-P063's 20-for-20 result that empties the head on every cycle, and the cost
of an empty head is #1866's own number: a typeahead cache MISS is **1.16–2.29 s p50**
against a `<150 ms` budget.

⚠️ **And the honest reading of the same table indicts today's value too.** At B = 10 the
worst measured wall gives P = 50 s, which is over the cliff — and production has
measured the period at **42.5–51.7 s** (LAT-P062, two reads), i.e. the upper tail is
already crossing. Today is *marginal*; 60 s is *unconditional*. That distinction is the
verdict this module returns, and flattening it to a bool would lose the only part a
reader needs.

## Why no beat interval is the answer

The gap between the worst measured pass wall (**42.6 s**) and the TTL (**45 s**) is
**2.4 s**. Any beat interval large enough to cut arrivals meaningfully is far coarser
than 2.4 s, so it cannot land the period inside that gap for every wall in the measured
range. `B = 22` happens to arithmetically fit (P = 44 s on the whole range) — and it is
still refused here, because 1.4 s of headroom against a distribution whose maximum came
from a finite sample is not a margin, it is a coincidence.

**The lever is wrong, not the goal.** Raising the beat couples two quantities that are
currently independent: the *message rate* (which the W-move wants to cut) and the *pass
period* (which must stay under 45 s). The remedies that cut the first without touching
the second are on the **publish side** — the same place LAT-P071 §4's clause points:

> *a gate inside the task cannot protect the queue.* If the cheap answer is "no work",
> the cheapness is spent on the wrong side of the bottleneck.

A publish-side gate (a `celery.schedules.schedule` subclass whose `is_due()` consults
the warmer's own `_LAST_PASS_START_KEY` before the beat publishes) removes ~82 % of the
messages while leaving the 10 s firing opportunity — and therefore the period — exactly
as it is today. That is designed and costed in
`docs/audits/latency/lat-p072-w-move-derivation.md`; it is **not** shipped here, because
it is a second intervention and the window's one intervention budget is spent on
measuring the first.

## What this module does NOT claim

* It does not claim 60 s would fail to reduce depth. It would: background inflow falls
  8.33 → 3.33 msg/min, a 60 % cut. **Depth is not the thing the cliff protects.**
* It does not re-litigate `WARM_CONCURRENCY`, the TTL, or `MIN_PASS_PERIOD_SECONDS`.
  Raising the TTL or shortening the pass are the two levers that genuinely move the
  cliff, and both are separate interventions with their own predictions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from typing import Optional

# ---------------------------------------------------------------------------
# Mirrored constants. Each is pinned against its real definition by
# `tests/test_typeahead_beat_budget.py` — mirrored rather than imported for the
# same reason `typeahead_warmer._CACHE_KEY_PREFIX` is: importing `routes/events`
# at module scope would make this utility's import graph the route's, and this
# module is imported by admin surfaces that must not drag the route in.
#
# A drifted mirror here is a RED TEST, never a silently wrong derivation — the
# failure mode doctrine clause 2 exists for.
# ---------------------------------------------------------------------------

#: `/api/events/typeahead`'s response-cache TTL, in seconds. The cliff itself.
#: Mirrored from `routes/events.py`'s `setex(_cache_key, 45, ...)`.
RESPONSE_CACHE_TTL_S = 45

#: The warmer's floor on how often a pass may START. Mirrored from
#: `tasks/typeahead_warmer.MIN_PASS_PERIOD_SECONDS`.
MIN_PASS_PERIOD_S = 30

#: The beat interval in force today. Mirrored from the `warm-typeahead` entry in
#: `tasks/__init__.py` (`"schedule": 10.0`).
CURRENT_BEAT_INTERVAL_S = 10.0

# ---------------------------------------------------------------------------
# The measured pass wall. PROVENANCE, not folklore.
#
# Live W=4 production passes: 32 s median, 29.4-42.6 s range (LAT-P062/LAT-P063,
# `docs/audits/latency/lat-p063-wsweep-graded.md`). These are wall-clock durations
# of real passes over the 40-entry head, not projections — an earlier version of
# the warmer's own docstring carried PROJECTED figures ("W=4 gives 14.7s worst")
# that production refuted by better than 2x, which is why only measured values
# are admitted here.
# ---------------------------------------------------------------------------

MEASURED_WALL_MEDIAN_S = 32.0
MEASURED_WALL_MIN_S = 29.4
MEASURED_WALL_MAX_S = 42.6

#: How many production passes stand behind the range above. Recorded because a
#: maximum drawn from a finite sample is a lower bound on the true maximum, and
#: every margin computed against it inherits that.
MEASURED_WALL_SAMPLE_PASSES = 20

#: A derived period must clear the TTL by at least this much to be called SAFE.
#: 5 s is one half of today's beat and roughly twice the 2.4 s that separates the
#: worst measured wall from the TTL — deliberately larger than the gap it is
#: judging, so that "SAFE" cannot be reached by a coincidence of arithmetic.
SAFETY_MARGIN_S = 5.0


class BeatVerdict:
    """Three-valued, because "unknown" and "unsafe" are not the same answer.

    Doctrine clause 1: a derivation that could not run must not render as one
    that ran and approved. `REFUSED` is reachable and is not a synonym for
    `UNSAFE` — it means the inputs did not support an answer at all.
    """

    SAFE = "safe"
    MARGINAL = "marginal"
    UNSAFE = "unsafe"
    REFUSED = "refused"


@dataclass(frozen=True)
class BeatGrade:
    """The full derivation for one candidate beat interval, with its own workings.

    Carries the intermediate periods rather than only the verdict: a reader who
    disagrees with the verdict needs to be able to see which wall produced it,
    and an instrument that reports a conclusion without the work is the shape
    ruling 074 asks us not to ship.
    """

    beat_s: float
    verdict: str
    reason: str
    period_at_median_s: Optional[float] = None
    period_at_worst_s: Optional[float] = None
    period_at_best_s: Optional[float] = None
    crosses_cliff_on_worst: Optional[bool] = None
    crosses_cliff_on_median: Optional[bool] = None
    arrivals_per_min: Optional[float] = None
    notes: tuple = field(default_factory=tuple)

    @property
    def is_shippable(self) -> bool:
        """Only `SAFE` ships. `MARGINAL` explicitly does not.

        `MARGINAL` describes today's live value, so this property is deliberately
        NOT "is the current config acceptable" — it is "may this be adopted as a
        change". Adopting a marginal value on purpose is a different decision
        from having inherited one, and it needs Alex, not a boolean.
        """
        return self.verdict == BeatVerdict.SAFE


def quantised_period_s(beat_s: float, wall_s: float, floor_s: float = MIN_PASS_PERIOD_S) -> float:
    """The pass period a given beat interval produces for a given pass wall.

    A pass can only start on a beat fire, and not before the floor has elapsed
    since the last start. So the effective period is the larger of (wall, floor)
    rounded UP to the next whole beat.

    This is the equation LAT-P062 measured directly when it removed the 30 s beat:
    a ~31 s pass inside a 30 s beat skipped every other fire and quantised to
    ~60 s. It is reproduced here so the same arithmetic cannot be done informally
    in a directive and come out differently.
    """
    if beat_s <= 0:
        raise ValueError("beat_s must be positive")
    if wall_s <= 0:
        raise ValueError("wall_s must be positive")
    binding = max(wall_s, floor_s)
    return beat_s * ceil(binding / beat_s)


def background_arrivals_per_min(beat_s: float) -> float:
    """Messages per minute this beat publishes into `background`.

    The half of the trade the W-move is buying, stated in the same units LAT-P071
    measured the queue in (8.33 msg/min total background inflow, of which
    `warm_typeahead` at a 10 s beat is 6.00/min = 72.0 %).
    """
    if beat_s <= 0:
        raise ValueError("beat_s must be positive")
    return 60.0 / beat_s


def grade_beat_interval(
    beat_s: float,
    *,
    wall_median_s: Optional[float] = None,
    wall_max_s: Optional[float] = None,
    wall_min_s: Optional[float] = None,
    ttl_s: int = RESPONSE_CACHE_TTL_S,
) -> BeatGrade:
    """Grade a candidate `warm-typeahead` beat interval against the 45 s cliff.

    Returns `REFUSED` — never a number, never a guess — when the measured wall
    inputs are absent or incoherent. That is ruling 075's shape: where the history
    cannot support a derivation, the answer is a visible refusal.
    """
    median = MEASURED_WALL_MEDIAN_S if wall_median_s is None else wall_median_s
    worst = MEASURED_WALL_MAX_S if wall_max_s is None else wall_max_s
    best = MEASURED_WALL_MIN_S if wall_min_s is None else wall_min_s

    if beat_s is None or beat_s <= 0:
        return BeatGrade(
            beat_s=beat_s,
            verdict=BeatVerdict.REFUSED,
            reason="beat interval must be a positive number of seconds",
        )
    if None in (median, worst, best) or min(median, worst, best) <= 0:
        return BeatGrade(
            beat_s=beat_s,
            verdict=BeatVerdict.REFUSED,
            reason="no measured pass wall available; a beat interval cannot be graded without one",
        )
    if not (best <= median <= worst):
        # An incoherent range is a refusal rather than a silent reorder: the
        # caller has passed something it does not understand, and quietly sorting
        # it would produce a confident answer from a confused input.
        return BeatGrade(
            beat_s=beat_s,
            verdict=BeatVerdict.REFUSED,
            reason=f"incoherent wall range: min={best} median={median} max={worst}",
        )
    if ttl_s <= 0:
        return BeatGrade(
            beat_s=beat_s,
            verdict=BeatVerdict.REFUSED,
            reason="response cache TTL must be positive",
        )

    p_median = quantised_period_s(beat_s, median)
    p_worst = quantised_period_s(beat_s, worst)
    p_best = quantised_period_s(beat_s, best)

    crosses_worst = p_worst > ttl_s
    crosses_median = p_median > ttl_s

    arrivals = background_arrivals_per_min(beat_s)
    notes = (
        f"period = beat * ceil(max(wall, {MIN_PASS_PERIOD_S}s floor) / beat)",
        f"cliff = {ttl_s}s response TTL; LAT-P063 measured 20/20 passes over it lost entries",
        f"publishes {arrivals:.2f} msg/min into background",
    )

    if crosses_median:
        # The median pass crosses. Every reachable wall at or above the median
        # empties the head, so this is not a tail risk, it is the normal case.
        verdict = BeatVerdict.UNSAFE
        reason = (
            f"period at the MEDIAN measured wall is {p_median:.0f}s, over the {ttl_s}s TTL — "
            f"the head is emptied on a typical pass, not merely on a bad one"
        )
    elif crosses_worst:
        verdict = BeatVerdict.MARGINAL
        reason = (
            f"period at the median wall is {p_median:.0f}s (inside {ttl_s}s) but "
            f"{p_worst:.0f}s at the worst measured wall — the upper tail crosses"
        )
    elif p_worst > ttl_s - SAFETY_MARGIN_S:
        verdict = BeatVerdict.MARGINAL
        reason = (
            f"period clears the TTL on the whole measured range (worst {p_worst:.0f}s) "
            f"but by less than the {SAFETY_MARGIN_S:.0f}s margin; the measured maximum is "
            f"a lower bound on the true maximum over {MEASURED_WALL_SAMPLE_PASSES} passes"
        )
    else:
        verdict = BeatVerdict.SAFE
        reason = (
            f"period is {p_worst:.0f}s even at the worst measured wall, clearing the "
            f"{ttl_s}s TTL by at least {SAFETY_MARGIN_S:.0f}s"
        )

    return BeatGrade(
        beat_s=beat_s,
        verdict=verdict,
        reason=reason,
        period_at_median_s=p_median,
        period_at_worst_s=p_worst,
        period_at_best_s=p_best,
        crosses_cliff_on_worst=crosses_worst,
        crosses_cliff_on_median=crosses_median,
        arrivals_per_min=arrivals,
        notes=notes,
    )


#: The interval Fable's LAT-P072 item 2 rules as the first W-move. Named as a
#: constant so the guard test asserts against the ACTUAL proposal rather than
#: against a number a future reader might assume it was.
PROPOSED_W_MOVE_BEAT_S = 60.0
