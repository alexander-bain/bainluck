"""Derive which `warm-typeahead` beat intervals are reachable, and refuse the rest.

⚠️⚠️ **READ THIS AMENDMENT FIRST — LAT-P075 (2026-08-19) moved two of the numbers
this docstring argues from, and left the argument itself intact.**

* **The cliff is 65 s, not 45 s.** Fable ratified the TTL raise (GO ruling 4).
  Every "45 s" below is historical. The quantiser table is still correct as
  arithmetic; its verdict column is not.
* **The worst pass wall is 61.282 s, not 42.6 s** (`RING_WALL_MAX_S`, n=26, the
  first read of the deployed pass-ring instrument). This is the THIRD time a
  sampled maximum in this program turned out to be a lower bound.
* **Consequence, and it is the uncomfortable one:** the 60 s W-move this module
  was written to refuse no longer grades UNSAFE at the new TTL, so
  `test_live_beat_interval_is_not_unsafe` — described below as the load-bearing
  test — **no longer covers the case it was built for.** The refusal was moved
  into `test_the_proposed_60s_w_move_is_still_refused_on_the_newest_measurement`,
  which grades on the quantity (a 120 s period at the worst wall) rather than on
  a verdict label that stopped carrying it. Do not read the paragraph below
  about "the load-bearing test" without reading that one too.
* **And the period regression is NOT a beat-interval problem at all.** It is
  `--concurrency=2` on `worker-background` shared by 57 beats, with this warmer
  now holding ~91 % of one of the two slots. See `background_slot_occupancy()`.

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
#: Mirrored from `routes/events.py`'s `setex(_cache_key, 65, ...)`.
#:
#: ⚠️ 45 -> 65, LAT-P075, on Fable's RATIFICATION of 2026-08-19 (GO ruling 4).
#: 65 is derived and not chosen: `derive_response_ttl_s()` returns it from the
#: LAT-P074 pass-only worst wall, and it is the first TTL the live 10 s beat has
#: ever graded SAFE against this module's own `SAFETY_MARGIN_S` — 59 and 60 both
#: return MARGINAL with zero headroom over the 60 s quantised period.
#:
#: 🔴 **AND THE TTL IS A FLOOR UNDER THE DAMAGE, NOT THE REPAIR.** Fable's ruling
#: states the limit of this number in the same breath as ratifying it: the TTL
#: buys 5.7 percentage points of the head's cold time, because the 196-547 s
#: period stalls lose all 40 entries regardless of any TTL, and zeroing that loss
#: needs TTL >= 553 s — a decision to serve stale data instead of fixing the
#: regression. The repair is a CAPACITY change on `worker-background`; see
#: `background_slot_occupancy()` at the foot of this module.
RESPONSE_CACHE_TTL_S = 65

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

#
# ⚠️ **SWAPPED TO THE PASS-ONLY TRIPLE, LAT-P075.** These were 32.0 / 29.4 / 42.6
# from LAT-P062/P063's mixed sweep. LAT-P074 measured the clean pass-only
# distribution and deliberately did NOT substitute it, because doing so flips the
# live beat's verdict and that flip required the TTL decision Fable held. He ruled
# on 2026-08-19 (GO ruling 4) and the TTL is now 65, so the halt is discharged and
# the honest numbers become the grader's inputs. This is the swap
# `test_the_pass_only_measurement_grades_the_live_beat_unsafe` existed to force.
MEASURED_WALL_MEDIAN_S = 40.991
MEASURED_WALL_MIN_S = 32.852
MEASURED_WALL_MAX_S = 53.920

#: How many production passes stand behind the range above. Recorded because a
#: maximum drawn from a finite sample is a lower bound on the true maximum, and
#: every margin computed against it inherits that.
MEASURED_WALL_SAMPLE_PASSES = 17

# ---------------------------------------------------------------------------
# LAT-P074 — THE PASS-ONLY WALL, MEASURED. And why it is NOT substituted above.
#
# `MEASURED_WALL_MAX_S = 42.6` is a known underestimate (LAT-P073 §5 registered
# it as owed). It comes from LAT-P063's paired sweep, and the p95 LAT-P073
# reached for instead (44.6 s) was worse still: it is a percentile over a MIXED
# distribution of real passes and ~10 ms no-ops, and no-ops only drag a
# percentile DOWN. Substituting one for the other would have been the
# projected-vs-measured trap this module's docstring exists to prevent.
#
# LAT-P074 took the clean measurement. `warm_typeahead`'s duration history is
# BIMODAL with a 460x gap and no ambiguity whatsoever — 33 executions at
# <= 71 ms and 17 at >= 32,852 ms, nothing in between — so "which runs were real
# passes" needs no judgement call. Read 2026-08-20T00:15Z from
# `GET /api/admin/celery/task-metrics/warm_typeahead`, saturated 50-sample ring
# over a 1,261 s window, and corroborated by direct pass summaries sampled off
# `last_result_summary` (wall 47.776 s, 53.920 s):
#
#     pass-only wall   min 32.852 s   p50 40.991 s   p95 47.862 s   max 53.920 s
#     no-op            max 0.071 s    (n = 33)
#
# 🔴 **THESE ARE NOT SUBSTITUTED INTO `MEASURED_WALL_*` ABOVE, AND THAT IS A
# DECISION RATHER THAN AN OVERSIGHT.** Substituting the MEDIAN flips the LIVE
# 10 s beat's verdict from `MARGINAL` to `UNSAFE`: at a 40.991 s median,
# P(10) = 10 * ceil(40.991/10) = 50 s, over the 45 s TTL on a TYPICAL pass and
# not merely on the tail. That is a production finding requiring the TTL
# decision Fable holds (LAT-P074 item 3), not a constant edit smuggled in on a
# measurement commit — ruling 075's shape, where a derivation whose inputs have
# moved emits a visible refusal instead of quietly re-deriving.
#
# The consequence is PINNED, not merely written down:
# `test_the_pass_only_measurement_grades_the_live_beat_unsafe` asserts the flip,
# and `test_the_ttl_that_returns_the_live_beat_to_safe` asserts the number that
# undoes it. Swapping the constants is the FIRST thing to do once the TTL is
# ruled; until then the grader stays optimistic and the tests say by how much.
PASS_ONLY_WALL_MIN_S = 32.852
PASS_ONLY_WALL_MEDIAN_S = 40.991
PASS_ONLY_WALL_P95_S = 47.862
PASS_ONLY_WALL_MAX_S = 53.920

#: 17 real passes in the duration ring plus the directly-sampled summaries. A
#: maximum from a finite sample is a LOWER BOUND on the true maximum, and every
#: margin derived from it inherits that — which is exactly how 42.6 came to be
#: wrong by 11.3 s.
PASS_ONLY_WALL_SAMPLE_PASSES = 17

#: The measured no-op ceiling. Recorded because it is what makes the split
#: defensible: the two modes are 460x apart, so no threshold between 0.1 s and
#: 30 s changes a single classification.
PASS_ONLY_NOOP_MAX_S = 0.071

#: A derived period must clear the TTL by at least this much to be called SAFE.
#: 5 s is one half of today's beat and roughly twice the 2.4 s that separates the
#: worst measured wall from the TTL — deliberately larger than the gap it is
#: judging, so that "SAFE" cannot be reached by a coincidence of arithmetic.
SAFETY_MARGIN_S = 5.0

# ---------------------------------------------------------------------------
# LAT-P075 — THE FIRST READ OF THE DEPLOYED INSTRUMENT, and the input it moved.
#
# `GET /api/admin/typeahead-warmer/last` shipped on `program/latency-67` and
# deployed in `6e314028`. LAT-P075 took its first production read at
# 2026-08-20T02:5xZ: 26 real passes over a 2,196 s span, off the pass ring, which
# is pass-only BY CONSTRUCTION (skips are counted into `skips:<reason>`, never
# ringed) rather than by a bimodality argument over a mixed duration list.
#
#     ring wall   min 39.316 s   p50 45.687 s   p95 55.722 s   max 61.282 s   (n=26)
#
# 🔴 **THE WORST WALL MOVED AGAIN: 53.920 -> 61.282 s, +7.36 s.** This is the
# third time this program has watched a sampled maximum turn out to be a lower
# bound — 42.6 was wrong by 11.3 s, and 53.920 is now wrong by 7.36 s — and it is
# recorded here because the TTL that ships in this same commit was ratified
# against 53.920.
#
# ⚠️ **CONSEQUENCE, STATED AND PINNED RATHER THAN QUIETLY RE-DERIVED.** At the ring
# maximum the same `grade_beat_interval` returns **MARGINAL, not SAFE**, for the
# TTL that shipped: P(10) = 10 * ceil(61.282/10) = 70 s, which is over 65. The
# TTL that would return SAFE on these inputs is 75 s.
#
# **65 SHIPS ANYWAY, AND THAT IS THE RULING RATHER THAN AN OVERSIGHT.** Fable's
# GO ruling 4 closes TTL derivation explicitly — "do not spend another cycle
# deriving a TTL" — and forecloses exactly this move: a TTL raised to survive the
# regressed period is a decision to serve stale data instead of fixing the
# regression. Chasing 65 -> 75 on a moved maximum is that move. The repair is
# `derive_message_expiry_s()`; this block is the disclosure that the ratified
# number now stands on a thinner margin than the one it was ratified on.
#
# Pinned by `test_the_ring_wall_grades_the_ratified_ttl_marginal`.
RING_WALL_MIN_S = 39.316
RING_WALL_MEDIAN_S = 45.687
RING_WALL_P95_S = 55.722
RING_WALL_MAX_S = 61.282

#: Real passes behind the ring triple. Larger than `PASS_ONLY_WALL_SAMPLE_PASSES`
#: and cleaner in kind — but still a finite sample, so still a lower bound.
RING_WALL_SAMPLE_PASSES = 26

# ---------------------------------------------------------------------------
# THE MESSAGE-EXPIRY DERIVATION — LAT-P075.
#
# 🔴 NOT the period repair, though it was drafted as one and #2014 names it as the
# period's mechanism. It stops a measured two-thirds message discard and makes
# background saturation readable; the period's cause is `--concurrency=2` on
# `worker-background` shared by 57 beats. See `derive_message_expiry_s` below and
# `background_slot_occupancy()` at the bottom of this module.
#
# Mirrored from `tasks/typeahead_warmer._LOCK_TTL_SECONDS`.
LOCK_TTL_S = 120


def derive_message_expiry_s(
    *,
    beat_s: float = CURRENT_BEAT_INTERVAL_S,
    worst_wall_s: float = RING_WALL_MAX_S,
    lock_ttl_s: float = LOCK_TTL_S,
    margin_s: float = SAFETY_MARGIN_S,
) -> float:
    """How long a `warm-typeahead` message must be allowed to live. Derived.

    ## The defect this repairs, measured rather than argued

    `_EXPIRING_WARMER_BEATS["warm-typeahead"]` was **10**, equal to the beat
    period, on the reasoning that `expires` must never exceed the period or a
    superseded message survives its own replacement. That reasoning is sound for
    a task whose wall is SHORTER than its beat period. `warm_typeahead`'s is not:
    it runs 39.3-61.3 s against a 10 s beat.

    When the wall exceeds the period, the fires that land DURING a pass are not
    superseded messages — they are the only start opportunities that exist, and
    they are all held off by the run lock until the pass ends. Expiring them at
    one beat period destroys every one of them except those published in the
    final `expires` seconds of the pass.

    **The arithmetic is exact and production matches it.** Of the fires in one
    pass period, the fraction that can execute at all is::

        (expires + max(0, period - wall)) / period

    At the values measured 2026-08-20T02:5xZ — expires 10 s, wall p50 45.7 s,
    period p50 53.5 s — that predicts **32.7 %**. The deployed instrument's own
    counters said **30.5 %**: 26 ringed passes plus 41 counted skips = 67
    executions against ~220 beat fires over 2,196 s. Two thirds of the warmer's
    firing opportunities were being discarded unexecuted, by a bound whose stated
    purpose they did not fall under.

    ## The derived value

    The only thing that can legitimately delay a `warm_typeahead` message is the
    run lock, so the message must outlive the longest possible lock hold. That is
    **not** the sampled worst wall — this program has now been wrong twice by
    reading a finite maximum as a bound (42.6 by 11.3 s, 53.920 by 7.36 s). It is
    `_LOCK_TTL_SECONDS`, a CONSTANT: the lock cannot be held past its own TTL, so
    a message older than that is provably not waiting on the lock and is
    genuinely superseded. Deriving from the constant rather than the sample is
    what makes this value immune to the next wall measurement moving again.

    The sampled wall is retained as a corroboration, not as the input: the
    derived value must also clear `worst_wall_s + margin_s`, and a run where it
    does not is a REFUSAL rather than a smaller number.

    ## What it costs, stated

    Every fire now executes. The ones that cannot start a pass take the lock-skip
    path, measured at **<= 71 ms** (`PASS_ONLY_NOOP_MAX_S`). At 6 fires/min that
    is ~0.4 s of worker-slot time per minute, ~0.7 % of one slot. Publishes are
    unchanged — this bound touches delivery, never the publish rate — so #1609's
    background-queue arrival share is untouched in both directions.
    """
    if beat_s <= 0 or worst_wall_s <= 0 or lock_ttl_s <= 0:
        raise ValueError("beat, wall and lock TTL must all be positive")
    if margin_s < 0:
        raise ValueError("margin must not be negative")

    corroboration = worst_wall_s + margin_s
    if lock_ttl_s < corroboration:
        raise ValueError(
            f"lock TTL {lock_ttl_s}s is below the measured worst wall plus margin "
            f"({corroboration:.3f}s) — the lock can expire under a live pass, and "
            f"no message expiry derived from it would be safe"
        )
    return float(lock_ttl_s)


def executable_fire_fraction(
    *, expires_s: float, wall_s: float, period_s: float, beat_s: float = CURRENT_BEAT_INTERVAL_S
) -> float:
    """The share of beat fires that can execute at all, given an `expires` bound.

    The model `derive_message_expiry_s` rests on, exposed so it can be graded
    against production rather than believed. Returns a fraction of fires, not of
    publishes — a discarded message was published and then thrown away, which is
    precisely the loss this quantity exists to make visible.
    """
    if period_s <= 0 or beat_s <= 0 or wall_s <= 0 or expires_s <= 0:
        raise ValueError("expires, wall, period and beat must all be positive")
    live_s = min(float(expires_s), float(period_s)) + max(0.0, float(period_s) - float(wall_s))
    return min(1.0, live_s / float(period_s))


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



# ---------------------------------------------------------------------------
# LAT-P074 item 3 — THE TTL DERIVATION. Fable, 2026-08-19:
#
#   "derive the TTL per ruling 075 — TTL >= measured worst pass wall + margin,
#    margin stated — and bring me the number with its registered prediction
#    (cache-entry loss goes to zero; staleness cost bounded and named)."
#
# 🔴 THE FORMULA AS RULED PRICES THE WRONG QUANTITY, AND THE ARITHMETIC SAYS SO
# RATHER THAN AN OPINION. An entry is rebuilt once per PASS, so what it has to
# survive is the gap from one rebuild to the next — the pass PERIOD — and the
# period is the wall QUANTISED UP to the next beat fire (`quantised_period_s`,
# the same equation LAT-P062 measured directly). At the live 10 s beat the worst
# measured wall of 53.920 s quantises to a 60 s period. So:
#
#     Fable's literal reading   TTL >= 53.920 + margin   ->  59 s at margin 5
#     the survival requirement  TTL >= 60.000 + margin   ->  65 s at margin 5
#
# and at 59 s (or at 60 s) `grade_beat_interval` returns MARGINAL with ZERO
# headroom, which is precisely the "coincidence of arithmetic" `SAFETY_MARGIN_S`
# was written to refuse. 65 s is the first value at which the live beat has ever
# graded SAFE.
#
# The margin is NOT a new number invented for this decision — it is
# `SAFETY_MARGIN_S`, the constant this module already uses to separate SAFE from
# MARGINAL. Reusing it is deliberate: a decision whose margin was chosen after
# seeing the answer is a decision whose margin is an output.
#
# Ruling 075's three required properties, in order: the shortfall is visible as
# a REFUSAL (`prediction_holds=False` with a distinct verdict, never an empty
# success); the record names the floor it measured AND the budget it derived,
# both numbers, together; and it marks the state as one to FIX rather than one
# to watch.
# ---------------------------------------------------------------------------


class TtlVerdict:
    """Four-valued. `REFUSED` is not a synonym for `INSUFFICIENT`."""

    #: The derived TTL clears the quantised period AND the measured period, so
    #: `cache-entry loss goes to zero` survives contact with production.
    SUFFICIENT = "sufficient"
    #: A real derived number whose attached prediction is false at the measured
    #: period. The number is not wrong; the claim about it is.
    INSUFFICIENT_FOR_PREDICTION = "insufficient_for_prediction"
    #: No measured period was supplied, so the prediction cannot be graded
    #: either way. Distinct from `INSUFFICIENT` on purpose: "I could not check"
    #: must never render as "I checked and it fails", any more than as a pass
    #: (ruling 075, second clause).
    PREDICTION_UNGRADED = "prediction_ungraded"
    #: The inputs did not support a derivation at all.
    REFUSED = "refused"


@dataclass(frozen=True)
class TtlDerivation:
    """The whole derivation, with its workings. Rulings 074 and 075."""

    verdict: str
    reason: str
    #: The recommendation: smallest integer TTL clearing the quantised period.
    derived_ttl_s: Optional[float] = None
    #: Fable's literal reading, carried so the departure is visible rather than
    #: silently substituted. A derivation that quietly answers a different
    #: question than the one asked is the shape doctrine clause 2 banks.
    wall_plus_margin_ttl_s: Optional[float] = None
    #: The floors, both named in the same record (ruling 075, property 2).
    measured_wall_floor_s: Optional[float] = None
    quantised_period_floor_s: Optional[float] = None
    margin_s: Optional[float] = None
    beat_s: Optional[float] = None
    #: The TTL that drives loss to zero at the OBSERVED period, when one is
    #: supplied. `None` means unmeasured, never zero.
    loss_free_ttl_s: Optional[float] = None
    measured_period_s: Optional[float] = None
    current_ttl_s: Optional[int] = None
    #: How stale an entry may become at the derived TTL — the cost Fable asked
    #: to have bounded and named.
    max_staleness_s: Optional[float] = None
    notes: tuple = field(default_factory=tuple)

    @property
    def prediction_holds(self) -> bool:
        """Does `cache-entry loss goes to zero` survive contact with the period?

        `False` for both `INSUFFICIENT_FOR_PREDICTION` and `PREDICTION_UNGRADED`,
        and those are different states — read `verdict`, never this alone. The
        property exists so no call site hand-writes `verdict == SUFFICIENT` and
        quietly grows a second definition of the same idea.
        """
        return self.verdict == TtlVerdict.SUFFICIENT


def derive_response_ttl_s(
    *,
    worst_pass_wall_s: Optional[float] = None,
    beat_s: float = CURRENT_BEAT_INTERVAL_S,
    margin_s: float = SAFETY_MARGIN_S,
    measured_period_s: Optional[float] = None,
    current_ttl_s: int = RESPONSE_CACHE_TTL_S,
) -> TtlDerivation:
    """Derive `/typeahead`'s response-cache TTL from the measured pass wall.

    Ruling 075, in the direction it was written for: the derived value may never
    fall below the phase's own measured floor, and where the inputs do not
    support the claim being made, the output is a refusal naming both numbers
    rather than a plausible default.

    `worst_pass_wall_s` defaults to the LAT-P074 pass-only maximum. Pass a fresher
    one from `GET /api/admin/typeahead-warmer/last` (`passes.seconds_wall.max`) —
    that endpoint exists so this derivation never has to run against a stale
    constant again, which is how 42.6 s survived being wrong by 11.3 s.
    """
    floor = PASS_ONLY_WALL_MAX_S if worst_pass_wall_s is None else worst_pass_wall_s

    if floor is None or floor <= 0:
        return TtlDerivation(
            verdict=TtlVerdict.REFUSED,
            reason="no measured pass wall; a TTL cannot be derived without a floor",
        )
    if margin_s is None or margin_s < 0:
        return TtlDerivation(
            verdict=TtlVerdict.REFUSED,
            reason=f"margin must be a non-negative number of seconds, got {margin_s!r}",
            measured_wall_floor_s=floor,
        )
    if beat_s is None or beat_s <= 0:
        return TtlDerivation(
            verdict=TtlVerdict.REFUSED,
            reason=f"beat interval must be positive to quantise a period, got {beat_s!r}",
            measured_wall_floor_s=floor,
        )
    if current_ttl_s is None or current_ttl_s <= 0:
        return TtlDerivation(
            verdict=TtlVerdict.REFUSED,
            reason="current response TTL must be positive",
            measured_wall_floor_s=floor,
        )

    period_floor = quantised_period_s(beat_s, floor)
    derived = float(ceil(period_floor + margin_s))
    wall_only = float(ceil(floor + margin_s))

    notes = (
        f"an entry must survive one PASS PERIOD, not one pass wall: "
        f"period = {beat_s:.0f}s * ceil(max({floor:.3f}s, {MIN_PASS_PERIOD_S}s) / "
        f"{beat_s:.0f}s) = {period_floor:.0f}s",
        f"TTL >= {period_floor:.0f}s + {margin_s:.0f}s margin = {derived:.0f}s "
        f"(vs current {current_ttl_s}s)",
        f"Fable's literal wall+margin reading gives {wall_only:.0f}s, at which "
        f"grade_beat_interval still returns MARGINAL with zero headroom",
        f"the wall floor is a max over {PASS_ONLY_WALL_SAMPLE_PASSES} passes and is "
        "a LOWER bound on the true maximum",
    )

    common = {
        "derived_ttl_s": derived,
        "wall_plus_margin_ttl_s": wall_only,
        "measured_wall_floor_s": floor,
        "quantised_period_floor_s": period_floor,
        "margin_s": margin_s,
        "beat_s": beat_s,
        "current_ttl_s": current_ttl_s,
        "max_staleness_s": derived,
        "notes": notes,
    }

    if measured_period_s is None:
        return TtlDerivation(
            verdict=TtlVerdict.PREDICTION_UNGRADED,
            reason=(
                f"derived {derived:.0f}s from a {period_floor:.0f}s quantised-period floor "
                f"+ {margin_s:.0f}s margin, but NO measured period was supplied. The "
                "prediction 'cache-entry loss goes to zero' is UNGRADED, which is not the "
                "same as met — the quantiser predicts the period, production measures it, "
                "and this program has already been wrong about that gap once"
            ),
            **common,
        )

    if measured_period_s <= 0:
        return TtlDerivation(
            verdict=TtlVerdict.REFUSED,
            reason=f"measured period must be positive, got {measured_period_s!r}",
            **common,
        )

    loss_free = float(ceil(measured_period_s + margin_s))

    if derived >= loss_free:
        return TtlDerivation(
            verdict=TtlVerdict.SUFFICIENT,
            reason=(
                f"derived {derived:.0f}s clears the {period_floor:.0f}s quantised period "
                f"floor and the {measured_period_s:.3f}s measured period; every entry "
                f"survives to its next rebuild, at a bounded staleness of {derived:.0f}s"
            ),
            loss_free_ttl_s=loss_free,
            measured_period_s=measured_period_s,
            **common,
        )

    return TtlDerivation(
        verdict=TtlVerdict.INSUFFICIENT_FOR_PREDICTION,
        reason=(
            f"derived {derived:.0f}s clears the quantised period floor, but the OBSERVED "
            f"period is {measured_period_s:.3f}s — an entry rebuilt at the start of one "
            f"pass is dead {measured_period_s - derived:.1f}s before the next pass reaches "
            f"it. Cache-entry loss does NOT go to zero at {derived:.0f}s; it goes to zero "
            f"at {loss_free:.0f}s, and a {loss_free:.0f}s TTL is a different conversation. "
            "When the observed period exceeds the quantiser's prediction, the defect is "
            "the period, not the TTL"
        ),
        loss_free_ttl_s=loss_free,
        measured_period_s=measured_period_s,
        **common,
    )


# ---------------------------------------------------------------------------
# LAT-P075 — THE PERIOD REGRESSION'S ACTUAL CAUSE, made checkable.
#
# This module exists because "a constant whose only defence is a paragraph will
# eventually be changed by someone who did not read the paragraph". The same is
# true of a finding: a cause that lives only in a report is a cause the next
# window re-derives. So the arithmetic behind the period tail goes here, next to
# the arithmetic behind the cliff, and its guard goes in the test suite.
# ---------------------------------------------------------------------------

#: `worker-background`'s celery `--concurrency`, from `backend/Procfile`.
#: Mirrored, and pinned against the Procfile by
#: `test_background_concurrency_mirror_matches_the_procfile`.
BACKGROUND_WORKER_CONCURRENCY = 2


def background_slot_occupancy(
    *, wall_s: float = RING_WALL_MEDIAN_S, period_s: float = 50.072
) -> float:
    """The share of ONE background worker slot that `warm_typeahead` holds.

    ## Why this number is the period regression

    The period was 42.5-51.7 s at LAT-P062 and is 40.1-547.2 s now, and nothing
    about the beat changed: it was 10 s then and it is 10 s now. What changed is
    the pass wall, 32.0 s -> 45.7 s median, against a period that barely moved.

    `worker-background` runs `--concurrency=2`. **102 beat entries route to that
    queue** and one of them is this warmer. At LAT-P062's numbers the warmer held
    32.0/50 = 64 % of one of the two slots; at today's it holds **91 %** —
    effectively a permanent resident of one slot.

    🔴 **LAT-P076 corrects two facts LAT-P075 stated here.** Both were wrong in
    the direction that makes the queue look emptier than it is, and both are
    pinned by tests now rather than left as prose:

    1. **It is 102 beats, not 57.** 57 is the count with an EXPLICIT
       ``options={"queue": "background"}``. A further **45** carry no queue at
       all and land here through ``task_default_queue = "background"`` — among
       them ``turbo_collapse_futures`` (mean **1,859 s**), ``backfill_winners``
       (868 s) and ``poll_polymarket_markets`` (304 s). The heaviest co-tenants
       on this queue are here BY DEFAULT, not by decision, which is the part
       that matters for the remedy: this is not a queue somebody sized, it is
       the fall-through.
    2. **``rebuild_typeahead_index`` is NOT a co-tenant.** It routes to
       ``heavy`` (``task_routes``, and its own beat ``options``). LAT-P075 named
       its p95 150 s as the thing that starves this warmer; it cannot, because
       it never contends for these two slots. The real observed starvers are
       ``discover_events`` and ``warm_event_concepts`` — and ``discover_events``
       is one of the 45 default-queue fall-throughs.

    The corrected mechanism is stronger than the one it replaces. It is not that
    a single unlucky long co-tenant occasionally lands in the free slot; it is
    that **demand exceeds capacity outright** — see `background_utilisation`.

    That is the whole regression, and it is a CAPACITY fact rather than a policy
    one. It is why neither of this cycle's two shipped changes claims to fix it:

    * the TTL is a floor under the damage (Fable's GO ruling 4 says so in the
      sentence that ratifies it), and
    * the `expires` bound governs delivery, not scheduling — during a stall the
      broker pile drains on the first free slot either way.

    The levers are all capacity or isolation — raise `--concurrency`, move the
    warmer to its own queue, or move the long backfills off `background` — and
    every one of them is a dyno-memory decision (`--max-memory-per-child=200000`
    against the dyno size) rather than a code change this lane can derive. So the
    number is brought, not spent, exactly as the TTL was.

    Returns a fraction of one slot; > 1.0 would mean the warmer alone cannot fit.
    """
    if wall_s <= 0 or period_s <= 0:
        raise ValueError("wall and period must both be positive")
    return wall_s / period_s


def free_background_slots(
    *,
    concurrency: int = BACKGROUND_WORKER_CONCURRENCY,
    wall_s: float = RING_WALL_MEDIAN_S,
    period_s: float = 50.072,
) -> float:
    """Slots left for the other 101 background beats once the warmer has its share.

    Below 1.0 means a single long co-tenant can starve the warmer completely.
    **This function answers the weaker question**, and LAT-P076 kept it only so
    the comparison with LAT-P062 stays readable. It measures the warmer against
    the pool at one instant; it cannot see that the pool is oversubscribed on
    average, which is what `background_utilisation` measures and what actually
    produces the 176.5 s p95 / 326.3 s max period tail.
    """
    return float(concurrency) - background_slot_occupancy(wall_s=wall_s, period_s=period_s)


# ---------------------------------------------------------------------------
# LAT-P076: the queue is oversubscribed, which is a stronger claim than "the
# warmer is unlucky in a FIFO". Measured 2026-08-20T04:0xZ from the live beat
# schedule (exact intervals) joined to `/api/admin/celery/schedule-adherence`
# and `/api/admin/task-metrics` durations. See
# `docs/audits/latency/lat-p076-background-capacity.md` for the derivation.
# ---------------------------------------------------------------------------

#: Beat entries whose EFFECTIVE queue is `background`. 57 name it explicitly;
#: 45 more fall through `task_default_queue`. Pinned by
#: `test_the_background_queue_carries_102_beats_not_57`.
BACKGROUND_BEAT_COUNT = 102

#: Demand on `background` in slot-seconds per hour, EXCLUDING `warm_typeahead`
#: (which is self-gated by its run lock, so its 360 fires/h are not 360 passes).
#: Bracketed by the duration estimator, because a p95-weighted sum is an upper
#: bound and a mean-weighted sum is the lower one. **Both are reported and
#: neither is presented as the number** — the conclusion below survives the
#: whole bracket, which is the only reason it is safe to act on.
BACKGROUND_DEMAND_EX_WARMER_MEAN_S_PER_H = 4538.0
BACKGROUND_DEMAND_EX_WARMER_P95_S_PER_H = 7546.0

#: The warmer's own measured draw: 91 % of one slot, continuously.
WARMER_DEMAND_S_PER_H = 3276.0


def background_utilisation(
    *,
    concurrency: int = BACKGROUND_WORKER_CONCURRENCY,
    demand_s_per_h: float = BACKGROUND_DEMAND_EX_WARMER_P95_S_PER_H,
    include_warmer: bool = True,
) -> float:
    """Offered load / capacity on the `background` queue. >= 1.0 has NO steady state.

    ## Why this, and not "the warmer sits behind a long task"

    A FIFO-position story implies the wait is a fluctuation: sometimes the
    warmer is behind something long, sometimes it is not, and the p50 is fine
    because usually it is not. That story is consistent with the p50 (46.5 s)
    and it is what LAT-P075 wrote. It does not explain a 326 s max, and it
    quietly predicts that adding one slot fixes everything.

    The utilisation says something different and worse. With the warmer
    included, offered load is **1.09x capacity on the mean estimator and 1.50x
    on the p95 estimator**. A queue at rho >= 1 does not have a long tail; it
    has no steady state at all — the backlog grows until something sheds it,
    and on this queue the thing that sheds it is `expires` discarding warmer
    messages. **The tail is a deficit, not a fluctuation.**

    That both estimators land above 1.0 is what makes this actionable. If the
    mean estimator had come in at 0.8 the honest report would have been "we
    cannot tell", because the two brackets would disagree about whether a
    steady state exists at all.

    ## What it says about adding a slot

    At `concurrency=3` the bracket is **0.72 .. 1.00** — it straddles 1.0. So
    LAT-P075's R4 ("period p95 < 90 s at concurrency 3") is **NOT SUPPORTED by
    this measurement**: on the upper estimator, three slots leave the queue
    exactly at capacity, which is still no steady state. At `concurrency=4` the
    bracket is 0.54 .. 0.75 and clears under both.

    This is reported as a refusal to predict, not as a prediction of failure.
    R4 may still hold — the mean estimator may be the right one. What cannot be
    said is that measurement supports it.
    """
    if concurrency <= 0:
        raise ValueError("concurrency must be positive")
    demand = float(demand_s_per_h)
    if include_warmer:
        demand += WARMER_DEMAND_S_PER_H
    return demand / (concurrency * 3600.0)
