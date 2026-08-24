"""Ruling 110's armed falsifier: the scoped `heavy` exception, and what revokes it.

LAT-P077 (#1609, #1545). Pure logic — no Redis, no DB, no Celery — so the
grader unit-tests without an environment. The caller supplies observations.

WHAT RULING 110 GRANTED
-----------------------
The standing "`heavy` is calibration-only" constraint gets a **scoped
exception for two tasks BY NAME** (`HEAVY_MOVE_EXCEPTION` below), not for a
class. Fable's grant is conditional and the condition is mechanical:

    if any calibration heavy-beat's latency degrades measurably after the
    move, the routing reverts the same window and the rule re-hardens.

This module is that condition, written down as a predicate with its
pre-move baseline pinned, so the revert decision is READ rather than argued.
A halt with no readable instrument is a wish (ruling ratified LAT-P074); so
is a conditional grant whose condition lives only in prose.

WHY A FALSIFIER AND NOT A PROMISE — the risk is measured, not hypothetical
-------------------------------------------------------------------------
LAT-P076's slot census priced the two movers at 32 % + 24 % = **56 % of one
`background` slot**. Measured here from durations (n=50 each) against 24 h
run counts, they are:

    backfill_market_shapes        6.1 % of a slot observed  (14.2 % if every fire ran)
    precompute_backfill_progress 12.8 % of a slot observed  (27.3 % if every fire ran)
                                 -----                       -----
                                 18.9 %                      41.5 %

Two things follow, and the second is the whole reason this file exists.

1. **`background`'s relief is bounded by what actually runs there: ~19 %,
   not 56 %.** The census overstates per-task share (26 samples).
2. **`heavy` may inherit MORE than `background` sheds.** Both movers run far
   below schedule today — 31 of 72 fires and 45 of 96 — because they are
   being starved on `background`. A task that stops being starved runs more
   often. So `heavy` takes on up to **41.5 % of one slot**, against relief to
   `background` of **19 %**. `heavy` sits at rho 0.59-0.81 (LAT-P076 §2);
   adding 0.415 of one slot is ~0.21 of its two, landing it near 0.80-1.02.

That is a real chance of pushing the calibration lane over, which is exactly
what the falsifier watches. The exception is cheap to grant and cheap to
revoke; what it is not is safe to grant unwatched.

THE REVERT, so it is four lines and not a rewrite
-------------------------------------------------
`grade_move(...).verdict == "REVERT"` obliges, the same window:

    1. delete the two names from `HEAVY_TASKS` in `app/tasks/__init__.py`;
    2. set both beat entries' literal `options["queue"]` back to
       `"background"` (`backfill-market-shapes`, `precompute-backfill-progress`);
    3. record the reading that fired it in the ruling file;
    4. the rule re-hardens: no further exception without a new ruling.

Step 2 is not optional bookkeeping. Beat `options` OVERRIDE `task_routes` at
dispatch, and `test_heavy_beat_literals_match_their_effective_queue` reads
the SOURCE TEXT — a revert that touches only `HEAVY_TASKS` leaves two beat
entries literally routing to `heavy` and turns that guard red.

🔴 #1800 BIT THIS FILE THREE TIMES WHILE IT WAS BEING WRITTEN
--------------------------------------------------------------
`_tracked_run` registers metrics under a name that is often NOT the task
name, so `GET /api/admin/celery/task-metrics/<task>` answers with an empty
body for a task that is running fine. In one window that produced three
false "NO DATA" reads:

    app.tasks.backfill_market_shapes          -> "market_shape_backfill"
    app.tasks.snapshot_coverage_metrics       -> "coverage_metrics"
    app.tasks.compute_time_horizon_calibration / compute_fair_fight_comparison
        -> readable only under their FULL names (the `compute_` prefix was
           dropped on the first read)

A falsifier built on that first read would have been blind on 3 of its 7
subjects **while reporting itself armed** — the precise failure gotcha #53
names. `METRICS_NAME` below is therefore explicit for every watched beat,
and `test_metrics_names_match_tracked_run_registrations` reads the source of
`app/tasks/__init__.py` so the mapping cannot rot back.

🔴 LAT-P079: TWO DEFECTS FOUND IN THIS FILE'S FIRST PRODUCTION READ
-------------------------------------------------------------------
The first production read of the endpoint (2026-08-21 09:15:35 PT, 6 min 55 s
after the routing deployed) returned **`HOLD — 4 of 7 watched beats graded,
none degraded`**, and it could not have returned anything else.

**Defect 1 — NO HORIZON GATE.** `recent_durations_ms` is a 50-deep ring and
`successes_24h` is a 24 h counter. Seven minutes after a move, both are
~99.5 % pre-move data, so the grade compares the distribution against itself:
three of the seven observed p50s matched their own pinned baselines to three
decimals (214.747 vs 214.7, 302.043 vs 302.0, 480.133 vs 480.1). `INCONCLUSIVE`
fired only when *nothing* could be graded; it did not fire when *everything*
was graded against pre-move data — which is the common case for anyone reading
this endpoint after a deploy. That is the wrong-gate defect ruling 110's own
general clause names, committed by the file that names it.

**Defect 2 — THE PANEL COULD NOT SEE ITS OWN SUBJECTS.** The route read
`{b.metrics_name for b in PRE_MOVE_BASELINE}` — the seven *protected* beats —
and then asked that same dict for the two *movers*, which are not in it. So
`movers[*].samples` was `0` and `successes_24h` was `null` **by construction,
permanently, whatever the movers were doing.** Measured against production at
the same instant the panel reported `samples: 0`:

    market_shape_backfill          29 successes,  2 failures, 50 samples
    precompute_backfill_progress   44 successes,  0 failures, 50 samples

LAT-P078 read `samples == 0` and concluded "neither moved task has run on
`heavy`". That conclusion was **wrong** — the number is a constant. Its
verdict (HOLD was not a pass) survives on defect 1's evidence alone.

**The two fixes had to ship together, and that is the whole lesson.** The
staged fix for defect 1 was *"`movers[*].samples == 0` ⇒ INCONCLUSIVE"*.
Applied to the unrepaired read, that condition is **never false**, so it would
have converted a gate that could not go red into a gate that could not go
green — the same defect mirrored, minted by its own fix. `READ_SET` and
`test_the_panel_reads_its_own_subjects` exist so a falsifier can never again
grade a task it does not observe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

# The exception is these two tasks BY NAME. Ruling 110 is explicit that it is
# not a class, not a prefix, and not "backfills in general" — a class-shaped
# reading is how "heavy is calibration-only" would erode without anyone
# deciding to erode it.
HEAVY_MOVE_EXCEPTION: frozenset[str] = frozenset(
    {
        "app.tasks.backfill_market_shapes",
        "app.tasks.precompute_backfill_progress",
    }
)

# task name -> the identifier `_tracked_run` actually registers (#1800).
METRICS_NAME: Mapping[str, str] = {
    "app.tasks.precompute_calibration_main": "precompute_calibration_main",
    "app.tasks.compute_calibration_prices": "calibration_prices",
    "app.tasks.compute_time_horizon_calibration": "compute_time_horizon_calibration",
    "app.tasks.compute_fair_fight_comparison": "compute_fair_fight_comparison",
    "app.tasks.precompute_source_intelligence": "precompute_source_intelligence",
    "app.tasks.snapshot_coverage_metrics": "coverage_metrics",
    "app.tasks.precompute_backfill_winners_status": "precompute_backfill_winners_status",
    # the two movers, so the endpoint can show what the move cost them too
    "app.tasks.backfill_market_shapes": "market_shape_backfill",
    "app.tasks.precompute_backfill_progress": "precompute_backfill_progress",
}


# Degradation thresholds. Deliberately generous: the falsifier exists to catch
# a real regression on the calibration lane, not to trip on ordinary variance
# in beats whose p50/p95 spread is already an order of magnitude wide.
DEGRADE_P50_RATIO = 1.25
CENSOR_FRACTION_OF_SOFT_LIMIT = 0.98

# ---------------------------------------------------------------------------
# THE MATERIALITY FLOOR (#2116, Fable directive 2026-08-23, LAT-P083)
# ---------------------------------------------------------------------------
# 🔴 A RATIO WITH NO ABSOLUTE TERM IS MOST SENSITIVE WHERE IT MATTERS LEAST.
#
# `DEGRADE_P50_RATIO` alone made the absolute move required to revoke ruling
# 110's grant proportional to a beat's own p50:
#
#     precompute_source_intelligence   pinned  17.5s  ->  +4.4s  fires REVERT
#     compute_fair_fight_comparison    pinned 147.8s  ->  +37s   fires REVERT
#     precompute_calibration_main      pinned 1187.8s ->  +297s  fires REVERT
#
# — 67x more sensitive to a 4x/day admin precompute than to the one beat a
# user-facing page waits on. On 2026-08-23 that graded +9.3s of median, with a
# FALLING p95 at n=8, identically to a five-minute regression on `/calibration`.
#
# So a beat now degrades only when BOTH gates trip: the ratio AND an absolute
# delta in seconds. Fable's words were "absolute seconds, scaled by what
# consumes the beat", and the scaling is a MEASURED consumer classification
# rather than a taste dial — every baseline declares its `consumer` and cites
# where the consumer was found in `consumer_note`.
#
# THE THREE CLASSES, and the argument for each number:
#
#   `user_page` (30s) — a public page renders this beat's artefact, so a delay
#       reaches a visitor by pushing back the moment fresh data lands. The
#       artefact is served from a cache the page reads (`/api/calibration` is
#       documented at a 1h cache), so 30s is under 1% of the visitor's own
#       staleness window and is the smallest delta worth revoking a grant over.
#
#   `operator_panel` (60s) — an admin page or admin API is the only renderer.
#       The reader is an operator on a human clock, and a sub-minute shift in
#       when a multi-hour precompute lands is not observable to them. 60s is
#       also the coarsest unit an operator's own tooling reports in.
#
#   `no_reader` (120s) — nothing renders it. Only schedule pressure and clamp
#       pressure can hurt, and BOTH are gated elsewhere: P4 grades schedule and
#       the observation-side censor grades the clamp. The ratio's remaining job
#       here is to catch a step change, and a step change on a beat nobody
#       reads is worth two minutes before it revokes a standing grant.
#
# WHAT THIS IS NOT. A floor is a way to make a gate quieter, and a gate that
# cannot go red is a defect this program has already minted twice. Three
# structural guards, all executable in
# `tests/test_falsifier_materiality_floor_2116.py`:
#
#   1. a ratio trip under the floor grades **`immaterial`** — a named state that
#      is printed, counted, and carried into `grade_move`'s top-level reason. It
#      is NEVER folded into `hold`.
#   2. the floor gates the RATIO only. The observation-side censor (#2071) is
#      untouched: a newly-saturated beat is `censored` whatever its delta.
#   3. the floor is CAPPED at the point the censor takes over, so it can never
#      make a beat ungradeable by itself (`floor_capped_by_censor`).
#
# RESIDUAL, STATED (LAT-P083): the floor is a MINIMUM, so the ratio still
# governs slow beats and the sensitivity spread narrows from 67x to ~5x — it
# does not INVERT. Making the user-facing beat the most sensitive needs a
# per-consumer CEILING as well, which tightens REVERT and is therefore a
# decision about ruling 110's grant that this lane does not get to make.
#
# 🟢 RESIDUAL CLOSED 2026-08-24 — see THE PER-CONSUMER CEILING below. Fable's
# LAT-P084 directive APPROVED the ceiling as instrument work, with the design
# constraint that "floors and ceilings come from the same measured consumer
# classification, capped both directions". They do: one table's keys, below.
CONSUMER_FLOOR_S: Mapping[str, float] = {
    "user_page": 30.0,
    "operator_panel": 60.0,
    "no_reader": 120.0,
}

# ---------------------------------------------------------------------------
# THE PER-CONSUMER CEILING (#2116 second half, Fable directive 2026-08-24)
# ---------------------------------------------------------------------------
# 🔴 A FLOOR FIXED THE SIGN OF THE ABSURDITY. IT DID NOT FIX THE DIRECTION.
#
# The named decision this instrument exists to serve is **"when does a
# user-facing regression revert ruling 110's grant?"** With the floor alone the
# instrument still answered it worst where it mattered most:
#
#     precompute_calibration_main     user_page       +297.0s to REVERT
#     precompute_source_intelligence  operator_panel  + 60.0s to REVERT
#
# The one beat a public page waits on needed a FIVE-MINUTE median regression;
# an admin precompute needed one minute. The floor is a minimum, so above it the
# ratio governs again and the ratio is proportional — the whole disease.
#
# The ceiling is an ABSOLUTE cap on the trip point, keyed on the SAME measured
# `BeatBaseline.consumer` classification. A beat degrades when EITHER
#
#     (a) the ratio trips AND the delta clears the consumer's FLOOR, or
#     (b) the delta clears the consumer's CEILING, whatever the ratio did.
#
# so the trip point is bounded from both sides:
#
#     effective trip delta = min( max(ratio delta, floor), ceiling )
#
# THE NUMBERS, AND WHY THEY TILE. Each class's ceiling is exactly the next
# looser class's floor:
#
#     user_page       [ 30s ..  60s ]
#     operator_panel  [ 60s .. 120s ]
#     no_reader       [120s .. 240s ]
#
# That is not tidiness either — it is what makes the ordering a property of the
# SCHEME rather than of today's seven pins. The bands touch at their endpoints
# and never cross, so no future baseline can make an admin beat strictly more
# sensitive than a visitor-facing one. Contiguity also means there is no delta
# that falls in nobody's band. Measured over the real pins the spread goes
# 4.95x -> 2.0x and `user_page` is now the joint-minimum, which is the inversion
# LAT-P083 said it could not perform.
#
# The ceiling values are the floors read one class tighter, and the floors'
# arguments carry over unchanged: 60s is what an operator's own tooling can
# resolve, so a user-facing beat that has slipped a full operator-visible unit
# is unambiguously degraded; 120s is a step change on an unread beat; 240s is
# two of those.
#
# WHAT THIS IS NOT. A ceiling TIGHTENS a gate, which is the mirror-image failure
# mode from the floor's, and it gets the mirror-image guards — all executable in
# `tests/test_falsifier_consumer_ceiling.py`:
#
#   1. a ceiling trip is NAMED (`ceiling_exceeded`, `absolute_ceiling_s`) and
#      its reason says the ratio did NOT trip. Otherwise a reader re-derives the
#      ratio, sees it under 1.25x, and concludes the panel is broken.
#   2. the ceiling is CAPPED BY THE CENSOR exactly as the floor is
#      (`ceiling_capped_by_censor`). A ceiling above a beat's remaining headroom
#      is unreachable — the beat saturates first — which is a dead gate wearing
#      a strict gate's clothes.
#   3. the ceiling sits STRICTLY ABOVE its own floor, or the `immaterial` band
#      is empty and the ceiling has silently deleted #2116.
#   4. the ceiling never fires on an IMPROVEMENT. A delta is signed.
CONSUMER_CEILING_S: Mapping[str, float] = {
    "user_page": 60.0,
    "operator_panel": 120.0,
    "no_reader": 240.0,
}


@dataclass(frozen=True)
class Reading:
    """A percentile that knows whether it is a NUMBER or a BOUND (#2071).

    🔴 **The reporting shape is the fix.** `CENSOR_FRACTION_OF_SOFT_LIMIT` used
    to be applied once, to a beat's `p95`, and everywhere else a percentile
    travelled as a naked float that any caller could compare. A percentile
    sitting at a clamp is not a measurement of the distribution — it is a
    measurement of the clamp — and `for_grading()` returns `None` for exactly
    that case, so a censored read cannot be graded into a pass or a fail by
    someone who did not think about it. `seconds` is still carried, because a
    reader legitimately wants to know the bound.

    No `__lt__`, no `__float__`, `order=False`: a type that coerced to a float
    would be a censored value grading as a pass with extra steps.

    `implied_min_clip_rate` is `1 - quantile` and is a **lower bound, derived,
    never measured**. A p95 at the clamp proves at least 5 % of runs were
    clipped and nothing more; a p50 at the clamp proves at least 50 %. This is
    the arithmetic #2071 turns on — *any* clip rate above 5 % pins a p95, so the
    old rule discarded a beat over the 7 runs it could not read while ignoring
    the 43 it could.
    """

    seconds: float
    clamp_s: float
    quantile: float
    label: str

    @property
    def censored(self) -> bool:
        return self.seconds >= CENSOR_FRACTION_OF_SOFT_LIMIT * self.clamp_s

    @property
    def state(self) -> str:
        return "censored" if self.censored else "observed"

    def for_grading(self) -> float | None:
        """The value, or `None` when it is a bound rather than a value."""
        return None if self.censored else self.seconds

    @property
    def implied_min_clip_rate(self) -> float:
        return round(1.0 - self.quantile, 6) if self.censored else 0.0

    def describe(self) -> str:
        if not self.censored:
            return f"{self.label} {self.seconds:.1f}s"
        return (
            f"{self.label} {self.seconds:.1f}s CENSORED at the {self.clamp_s:.0f}s "
            f"clamp (>= {self.implied_min_clip_rate:.0%} of runs clipped)"
        )


@dataclass(frozen=True)
class BeatBaseline:
    """A watched beat's pre-move reading. Pinned, dated, and never recomputed.

    A baseline that is re-derived from live data after the change is not a
    baseline — it is the change grading itself.
    """

    task: str
    soft_time_limit_s: int
    p50_s: float
    p95_s: float
    max_s: float
    samples: int
    successes_24h: int
    failures_24h: int
    #: WHO READS THIS BEAT'S OUTPUT — #2116's requirement, and required rather
    #: than defaulted for the same reason `regime` is a field: a beat with no
    #: declared consumer has no defensible materiality floor, and a default
    #: would let one be added silently. One of `CONSUMER_FLOOR_S`'s keys.
    consumer: str
    #: WHERE the consumer was found. The floor is argued FROM this, so a
    #: classification with no evidence is a taste dial wearing a measurement's
    #: name. A test requires it to be non-empty.
    consumer_note: str
    note: str = ""
    #: WHICH REGIME this baseline describes — ruling 120's requirement, made a
    #: field rather than a sentence in prose so the endpoint can print it and a
    #: test can assert every beat answers.
    #:
    #: A baseline is a claim about the system we run in. If the system stepped
    #: between the pin and today, the pin describes a system that no longer
    #: exists and its ratio is a constant, not a measurement. #2102 caught
    #: exactly one such pin here and it read 6x forever.
    regime: str = "single — no dated step between the pin and today"
    #: The clamp a run actually stops on, when the task imposes one on ITSELF
    #: that is tighter than its configured `soft_time_limit`. `None` means the
    #: soft limit IS the clamp. See `clamp_note`.
    self_imposed_budget_s: float | None = None
    clamp_note: str = ""

    @property
    def metrics_name(self) -> str:
        return METRICS_NAME[self.task]

    @property
    def effective_clamp_s(self) -> float:
        """The smaller of the configured timeout and the task's own budget.

        #2071's correction, made executable. Ruling 110 said
        `compute_calibration_prices` was "clamped at its 600 s soft limit"; it
        is not. `_compute_calibration_prices` sets `_CAL_DEADLINE_S = 540.0` and
        stops there — 35 of 40 runs stop on the 540 s clock the task owns and
        only 3 of 40 ever reach 600 s. Censoring against the CONFIGURED limit
        therefore measured the wrong ceiling: it declared the beat unreadable
        for a reason that was not the reason, and would have kept declaring it
        so even if the 600 s limit were raised.
        """
        if self.self_imposed_budget_s is None:
            return float(self.soft_time_limit_s)
        return min(float(self.soft_time_limit_s), float(self.self_imposed_budget_s))

    @property
    def censor_threshold_s(self) -> float:
        """The p50 at which this beat stops being a measurement and becomes a bound."""
        return CENSOR_FRACTION_OF_SOFT_LIMIT * self.effective_clamp_s

    @property
    def declared_materiality_floor_s(self) -> float:
        """The floor its consumer class asks for, BEFORE the censor cap (#2116)."""
        return CONSUMER_FLOOR_S[self.consumer]

    @property
    def materiality_floor_s(self) -> float:
        """The floor actually applied: the declared one, capped by the censor.

        🔴 The cap is not tidiness. A declared floor larger than a beat's
        remaining headroom would put the ratio's trip point ABOVE the point at
        which the observation-side censor takes over — i.e. the beat could never
        grade `degraded` at all, because it would saturate first. That is a gate
        that cannot go red, minted by its own fix, which is the exact shape
        LAT-P079's `samples == 0 => INCONCLUSIVE` would have been.

        It binds on exactly one beat today (`snapshot_coverage_metrics`:
        120s declared, 107.9s applied) and `floor_capped_by_censor` says so on
        the panel rather than leaving the reader to subtract.
        """
        headroom = self.censor_threshold_s - self.p50_s
        return max(0.0, min(self.declared_materiality_floor_s, headroom))

    @property
    def floor_capped_by_censor(self) -> bool:
        return self.materiality_floor_s < self.declared_materiality_floor_s

    @property
    def declared_absolute_ceiling_s(self) -> float:
        """The ceiling its consumer class asks for, BEFORE the censor cap."""
        return CONSUMER_CEILING_S[self.consumer]

    @property
    def absolute_ceiling_s(self) -> float:
        """The ceiling actually applied: the declared one, capped by the censor.

        🔴 Capped for the SAME reason the floor is, and it is not symmetry for
        its own sake. A declared ceiling larger than the beat's remaining
        headroom is a gate that can never fire, because the beat saturates and
        grades `censored` before the delta could reach it. On the current pins
        this binds on three beats (`compute_time_horizon_calibration` 240 -> 240,
        `snapshot_coverage_metrics` 240 -> 107.9, `precompute_backfill_winners_
        status` 120 -> 69.6) and `ceiling_capped_by_censor` says so on the panel.

        Never below the applied FLOOR: the censor caps both, and if a cap pushed
        the ceiling under the floor then `min(max(ratio, floor), ceiling)` would
        make the ceiling the only gate and silently delete #2116's materiality
        band for that beat. Where the headroom forces them equal — as it does on
        `snapshot_coverage_metrics` at 107.9s — the band is legitimately a point:
        that beat has 107.9s of readable range and no more, which is a fact
        about the clamp, not a choice.
        """
        headroom = self.censor_threshold_s - self.p50_s
        capped = max(0.0, min(self.declared_absolute_ceiling_s, headroom))
        return max(capped, self.materiality_floor_s)

    @property
    def ceiling_capped_by_censor(self) -> bool:
        return self.absolute_ceiling_s < self.declared_absolute_ceiling_s

    @property
    def degrade_trips_at_s(self) -> float:
        """The observed p50 at which the beat degrades. Printed, never inferred.

        A reader asking "what would it actually take to revert this?" should get
        a number, not three thresholds and a baseline to combine.

        `min(max(ratio, floor), ceiling)` — bounded both directions. The floor
        raises the trip point for FAST beats the ratio over-reads; the ceiling
        lowers it for SLOW beats the ratio under-reads. Between them the ratio
        governs, unchanged.
        """
        two_gate = max(
            self.p50_s * DEGRADE_P50_RATIO, self.p50_s + self.materiality_floor_s
        )
        return min(two_gate, self.p50_s + self.absolute_ceiling_s)

    @property
    def p95(self) -> Reading:
        return Reading(self.p95_s, self.effective_clamp_s, 0.95, "p95")

    @property
    def p50(self) -> Reading:
        return Reading(self.p50_s, self.effective_clamp_s, 0.5, "p50")

    @property
    def censored(self) -> bool:
        """True when the statistic used to GRADE this beat is itself saturated.

        🔴 This used to read `p95`, and that is #2071. The grade is computed on
        the p50 (`DEGRADE_P50_RATIO` compares medians), so censoring on the p95
        excluded beats whose grading statistic was perfectly readable. Measured:
        `precompute_backfill_winners_status` has a 14 % clip rate, which pins
        any p95 by arithmetic, while its p50 sits at 518.4 s — 86 % of its
        clamp, with real headroom, and its durations span two and a half orders
        of magnitude. It was thrown away with 43 readable runs in hand.

        The p95 is still computed and still reported — a genuinely pinned beat
        must stay visible — but it no longer decides. Excluding a beat is the
        SAFE error direction (an exclusion never certifies safety), which is
        exactly why it needed a rule that could stop.
        """
        return self.p50.censored

# ---------------------------------------------------------------------------
# THE HORIZON (LAT-P079, defect 1)
# ---------------------------------------------------------------------------
# When the routing change reached production: Heroku **v3882** (`0c7ccdf2`),
# 2026-08-21T16:08:40Z = 09:08:40 PT, verified against `heroku releases` and
# `/api/health`. Pinned like the baseline is pinned, and for the same reason —
# a horizon recomputed from live data is the change timing itself.
ROUTING_CHANGE_AT_EPOCH: float = 1787328520.0

# `bainluck:task_metrics:<name>:durations` is LTRIM'd to 50 entries (gotcha
# #119). `successes_24h` / `failures_24h` are 24 h rolling counters.
OBSERVATION_RING_DEPTH = 50
RUN_COUNTER_WINDOW_S = 86_400.0

# P4 counts a mover as AT SCHEDULE at this fraction of its scheduled fires
# (#2110 defect a). Not 1.0, because a beat can never quite reach its nominal
# fire count — a run that overlaps the next tick, a dyno cycle, a deploy — and
# a threshold nothing can reach is a threshold that only ever grades FAILED.
# 0.9 says "running essentially every time it is asked to", which is what
# "no longer starved" means and is what ruling 110's P4 actually predicted.
AT_SCHEDULE_FRACTION = 0.9

# How recent a ring sample has to be before it CONTRADICTS a zero run counter
# (#2110 defect b). Same span as the counters nominally claim, so the two
# instruments are compared on the same footing: within this window the ring is
# the better witness, because it does not expire and they do.
RING_LIVENESS_WINDOW_S = 86_400.0

# How many POST-MOVE samples a p50 needs before it is allowed to grade.
#
# The grade is computed on the post-move samples ALONE (see `_post_move_split`),
# so no majority of the ring is required — only enough post-move data for a
# median to mean something. Eight is a judgement, stated rather than implied:
# it is the point at which the median is not one observation wearing a
# statistic's name, and at which a single outlier cannot carry it across a
# threshold as generous as 1.25x. It is deliberately small, because the cost of
# waiting is that ruling 110's grant sits unwatched, which the ruling itself
# calls the thing that must not happen.
MIN_POST_MOVE_SAMPLES = 8

# FALLBACK ONLY — used when the ring carries no timestamps (the pre-LAT-P040
# bare form). Then the grade falls back to requiring a MAJORITY of the ring to
# be post-move, because without stamps the post-move samples cannot be
# separated out and the whole ring is what the p50 is made of.
POST_MOVE_RING_SHARE_REQUIRED = 0.5


def post_move_runs_lower_bound(runs_24h: int, age_since_move_s: float) -> int | None:
    """How many of a beat's runs can be PROVEN to postdate the move.

    **The fallback instrument.** Used only when the duration ring carries no
    timestamps; when it does, `_post_move_split` counts the post-move samples
    exactly and this estimate is not consulted.

    `successes_24h` counts the window `[now - 24 h, now]`. That window lies
    entirely after the move only once `age >= 24 h`; before then the counter
    straddles the change and supplies **no lower bound at all** — every one of
    those runs could have happened before it. Returning `None` rather than a
    guess is the point: an estimate here would put a number on the one thing
    the instrument cannot see.

    The bound is conservative in the safe direction even when it exists: the
    duration ring is written for successes, failures *and* incompletes, while
    `runs_24h` counts only the first two, so the true post-move share is at
    least this. Under-counting delays a grade; over-counting would fake one.
    """
    if age_since_move_s < RUN_COUNTER_WINDOW_S:
        return None
    return max(0, int(runs_24h))


def _post_move_split(
    observation: Mapping[str, Any],
) -> tuple[list[float] | None, int]:
    """Split a duration ring into its post-move samples, EXACTLY.

    `recent_durations_at` is positionally aligned with `recent_durations_ms`
    and carries the epoch each sample was recorded at. Returns
    ``(post_move_durations_ms, total_ring_n)``, or ``(None, n)`` when the ring
    carries no usable stamps at all — which is a different fact from "no
    samples postdate the move" and must not be collapsed into it (#53). An
    entry whose own stamp is `None` is legacy, therefore genuinely old, and
    counts as pre-move.
    """
    durations = [d for d in (observation.get("recent_durations_ms") or []) if d is not None]
    stamps = observation.get("recent_durations_at")
    if not isinstance(stamps, (list, tuple)) or not any(s is not None for s in stamps):
        return None, len(durations)
    post: list[float] = []
    for i, ms in enumerate(durations):
        at = stamps[i] if i < len(stamps) else None
        if at is not None and float(at) >= ROUTING_CHANGE_AT_EPOCH:
            post.append(float(ms))
    return post, len(durations)


def _runs_per_24h(observation: Mapping[str, Any]) -> float | None:
    """Runs per 24 h, each counter rate-corrected against ITS OWN window.

    #2110 defect (a), half one. `successes_24h` and `failures_24h` are named
    for 24 h and are not 24 h counts — each window opens at that counter's own
    first increment, which is exactly why `successes_window_s` and
    `failures_window_s` are published alongside them. #2102 measured the
    consequence: the two windows on one beat were 15.54 h and 16.48 h, and
    dividing one by the other produced a headline ("3 of 5 runs failing") that
    was an artefact of the mismatch.

    A counter with a window is scaled to a full day. A counter with no window
    is taken at face value, which is the pre-#2102 behaviour and the best
    available; a counter at zero contributes zero either way. Returns `None`
    only when NEITHER counter can be read at all, so an unreadable rate is
    never rendered as a slow one.
    """
    total = 0.0
    readable = False
    for count_key, window_key in (
        ("successes_24h", "successes_window_s"),
        ("failures_24h", "failures_window_s"),
    ):
        raw = observation.get(count_key)
        if raw is None:
            continue
        readable = True
        count = float(raw)
        window = observation.get(window_key)
        try:
            window_s = float(window) if window is not None else 0.0
        except (TypeError, ValueError):
            window_s = 0.0
        if window_s > 0:
            # Never scale UP past the counter's own nominal span: a 30-minute
            # window carrying 3 runs would otherwise project to 144/day off
            # three observations. Clamping at the nominal window keeps the
            # correction honest in the direction it is allowed to help.
            total += count * (RUN_COUNTER_WINDOW_S / max(window_s, RUN_COUNTER_WINDOW_S / 4))
        else:
            total += count
    return total if readable else None


def _newest_sample_at(observation: Mapping[str, Any]) -> float | None:
    """The most recent stamp in the duration ring, or None if it has none.

    The ring's liveness witness (#2110 defect b). `None` means "this ring
    cannot speak to liveness", which is a different fact from "this beat has
    not run" and must not be read as the second (gotcha #53).
    """
    stamps = observation.get("recent_durations_at")
    if not isinstance(stamps, (list, tuple)):
        return None
    usable = [float(s) for s in stamps if s is not None]
    return max(usable) if usable else None

# ---------------------------------------------------------------------------
# PRE-MOVE BASELINE — measured 2026-08-20T16:40-16:47Z against production
# build v3873 (`086ce799`), via GET /api/admin/celery/task-metrics/<name>,
# BEFORE the routing change of ruling 110 shipped. n is that endpoint's
# `recent_durations_ms` ring.
#
# 🔴 AMENDED BY #2071 (LAT-P080B). This block used to read: "Two of the seven
# are ALREADY CENSORED at their 600 s soft limit and carry ZERO successes in
# 24 h." Both halves were wrong about at least one beat, and the correction
# raised effective coverage from 3 of 7 to **4 of 7**:
#
#   * `precompute_backfill_winners_status` — "zero successes" was FALSE (18 / 2
#     on the 2026-08-21 read) and it was excluded by a p95 that a 14 % clip rate
#     pins by arithmetic. It is GRADEABLE.
#   * `compute_calibration_prices` — still excluded, but it is clamped at the
#     540 s budget it imposes on ITSELF, not at the 600 s soft limit, and its
#     `partial` terminal is by design rather than a failure.
#
# The numbers below are the pre-move reading and are NOT refreshed to the later
# ones. A baseline re-derived after the change is the change grading itself.
# ---------------------------------------------------------------------------
PRE_MOVE_BASELINE: tuple[BeatBaseline, ...] = (
    BeatBaseline(
        task="app.tasks.precompute_calibration_main",
        consumer="user_page",
        consumer_note="`/api/calibration` "
        "(app/routes/admin_data_quality.py:3756-3787 documents the cache this beat "
        "fills) is called by `frontend/lib/api.ts:2118` from the PUBLIC "
        "`/calibration` page. The only user_page beat in the set — measured "
        "2026-08-23 by enumerating every frontend caller of each beat's serving "
        "route.",
        soft_time_limit_s=1500,
        # 🔴 RE-PINNED 2026-08-23 by ruling 120. WAS p50 214.7 / p95 1302.1 /
        # max 1357.2 — a MIXTURE STATISTIC taken across a regime boundary.
        #
        # CAL-P078's rolling re-stage shipped in v3874 (`724fd22c`, 2026-08-20
        # 10:45:57 PDT) and took this beat from a p50 of 163 s to a p50 of
        # 1,263 s — a 7.74x DATED, DELIBERATE step, `units_this_beat` going
        # from 0 to every-unit (#2102). The old pin's median was a regime-A
        # value and its p95/max were regime-B values, so it read ~6x against
        # every future observation of the perfectly healthy beat, forever, no
        # matter how many samples accumulated. A conditional grant whose
        # falsifier is stuck on REVERT is exactly as unwatched as one stuck on
        # HOLD.
        #
        # The re-pin is from LAT-P081's byte-pinned ring artefact
        # (`docs/audits/latency/lat-p081-gate1-pcm-ring.json`, captured
        # 2026-08-22T15:51Z), restricted to samples that are BOTH post-v3874
        # AND pre-routing-change — regime B, before ruling 110's move. n=22,
        # min 140.2 s.
        #
        # That double restriction is the whole design and it is why the live
        # ring could not be used: this ring has since rolled completely over
        # (oldest live sample 2026-08-21T14:38Z, 48 of 50 post-move), so a
        # baseline drawn from production TODAY would absorb the very move it
        # is supposed to grade — the change grading itself. The pre-move,
        # post-step window is only 22.4 h wide and exists in exactly one
        # committed artefact.
        p50_s=1187.8,
        p95_s=1396.4,
        max_s=1397.8,
        samples=22,
        successes_24h=12,
        failures_24h=8,
        regime="B (post-CAL-P078 rolling re-stage, v3874 2026-08-20 10:45:57 PDT), "
        "pre-move — the regime we run in",
        note="the hourly :15 warmer — the one beat a user-facing page waits on. "
        "Re-pinned by ruling 120 from regime B; the pre-v3874 numbers described "
        "a beat that has not existed since 2026-08-20. p95 1396.4s is 93% of "
        "its 1500s soft limit, so it is gradeable with 103.6s of headroom and "
        "very little of it — a genuine degradation shows up as saturation here "
        "before it shows up as a ratio, which is what the observation-side "
        "censor (#2071) is for.",
    ),
    BeatBaseline(
        task="app.tasks.compute_calibration_prices",
        consumer="no_reader",
        consumer_note="writes calibration prices to ROWS; no route serves a cache "
        "it fills. Excluded from grading anyway (censored at its own 540s budget), "
        "so the floor never runs.",
        soft_time_limit_s=600,
        p50_s=538.2,
        p95_s=599.9,
        max_s=600.3,
        samples=37,
        successes_24h=0,
        failures_24h=1,
        regime="single — cross-checked 2026-08-23: pre-v3874 p50 537.9s (n=31) vs post-v3874 550.2s (n=12), no step. EXCLUDED anyway, on its own budget.",
        note="CENSORED — but at its own 540s budget, not at the 600s soft limit, "
        "and it is NOT failing (#2071). 0 successes/24h is by design: it is a "
        "cursor-resuming bounded sweep whose terminal is `partial`, which "
        "task_verdict documents as not a failure, and its cursor advances "
        "monotonically (part_a 220,450,332 -> 220,617,056 over 20h). 35 of 40 "
        "runs stop on the 540s clock the task owns; only 3 of 40 reach 600s.",
        self_imposed_budget_s=540.0,
        clamp_note="_compute_calibration_prices sets _CAL_DEADLINE_S = 540.0 "
        "('soft_time_limit=600, keep a 60s margin'). Budget-bounded, not "
        "timeout-clamped — a real distinction, because a budget-bounded beat "
        "WOULD show contention, just in work-done per run (stopped_at, cursor "
        "delta) rather than in duration. A p50 comparator cannot see that; the "
        "work-done comparator #2071 proposes needs fields task-metrics does not "
        "carry today, so this beat stays excluded and says why.",
    ),
    BeatBaseline(
        task="app.tasks.compute_time_horizon_calibration",
        consumer="no_reader",
        consumer_note="fills `bainluck:calibration:time_horizon`, served by "
        "app/routes/calibration.py:1919. PUBLIC endpoint, but `grep -rn "
        "'time_horizon|time-horizon' frontend/` returns ZERO hits — no rendered "
        "consumer exists today. Classified on what reads it, not on what could: if "
        "a page starts rendering it, this line moves to user_page.",
        soft_time_limit_s=600,
        p50_s=302.0,
        p95_s=302.7,
        max_s=304.0,
        samples=40,
        successes_24h=0,
        failures_24h=0,
        regime="single — cross-checked 2026-08-23: pre-v3874 p50 302.0s (n=32) vs post-v3874 301.4s (n=12), 0.2% apart. The tightest beat in the set.",
        note="unusually tight distribution (302.0-304.0s); 0 runs in the last 24h, "
        "so `no_new_runs` is the expected verdict until it fires.",
    ),
    BeatBaseline(
        task="app.tasks.compute_fair_fight_comparison",
        consumer="operator_panel",
        consumer_note="fills `bainluck:calibration:fair_fight`, served by "
        "app/routes/source_intelligence.py:1339 `/source-intelligence/fair-fight`. "
        "Public route, but its only rendered consumer is "
        "`frontend/app/admin/source-intelligence/page.tsx` — an operator surface.",
        soft_time_limit_s=600,
        p50_s=147.8,
        p95_s=268.4,
        max_s=323.9,
        samples=37,
        successes_24h=3,
        failures_24h=0,
        regime="single — cross-checked 2026-08-23: pre-v3874 p50 147.2s (n=32) vs post-v3874 160.8s (n=12), +9%. No step; well inside this beat's own spread.",
        note="gradeable with real headroom.",
    ),
    BeatBaseline(
        task="app.tasks.precompute_source_intelligence",
        consumer="operator_panel",
        consumer_note="fills `bainluck:source_intelligence`, served by "
        "app/routes/source_intelligence.py:1383 and rendered ONLY by "
        "`frontend/app/admin/source-intelligence/page.tsx` "
        "(frontend/lib/api.ts:2214, linked from AdminSidebar.tsx:48). 🔴 THIS IS "
        "#2116's BEAT: its reader is an operator, so +9.3s of median is invisible "
        "to anyone.",
        soft_time_limit_s=600,
        p50_s=17.5,
        p95_s=27.3,
        max_s=41.2,
        samples=40,
        successes_24h=2,
        failures_24h=0,
        regime="single, and it is the one MOVING — cross-checked 2026-08-23: pre-v3874 p50 17.4s (n=32) vs post-v3874 26.7s (n=12), +53%. That post window CONTAINS the routing move, so this is a candidate SIGNAL rather than a regime problem, and it is the beat this instrument said would show it first. 9s in absolute terms, n=12: watch, do not conclude.",
        note="the cleanest subject in the set: tight, fast, far from its limit. "
        "If the move hurts the heavy lane, this is where it shows first.",
    ),
    BeatBaseline(
        task="app.tasks.snapshot_coverage_metrics",
        consumer="no_reader",
        consumer_note="referenced only by an admin TRIGGER "
        "(app/routes/admin_data_quality.py:5042); no route serves a cache it fills "
        "and no frontend file references it. 🔴 Its declared 120s floor is CAPPED "
        "to 107.9s by the censor — the one beat where the cap binds.",
        soft_time_limit_s=600,
        p50_s=480.1,
        p95_s=482.1,
        max_s=482.1,
        samples=10,
        successes_24h=0,
        failures_24h=0,
        regime="single — cross-checked 2026-08-23: pre-v3874 p50 480.1s (n=8) vs post-v3874 480.2s (n=3). Weakest evidence in the set, and unchanged.",
        note="only 10 samples and 0 runs in 24h; weak but readable.",
    ),
    BeatBaseline(
        task="app.tasks.precompute_backfill_winners_status",
        consumer="operator_panel",
        consumer_note="fills `bainluck:backfill_winners_status`, served by `GET "
        "/api/admin/backfill-winners/status` "
        "(app/routes/admin_data_quality.py:3488). Admin-only by route prefix. The "
        "ratio is the binding gate here (+129.6s) — the 60s floor changes nothing "
        "about it.",
        soft_time_limit_s=600,
        p50_s=518.4,
        p95_s=601.0,
        max_s=601.1,
        samples=50,
        successes_24h=0,
        failures_24h=2,
        regime="single, BUT UNVERIFIABLE FROM TODAY'S RING and that is worth saying plainly: this beat's ring has rolled completely over (oldest live sample 2026-08-21T14:47Z, 50 of 50 post-v3874), so the pre-v3874 arm no longer exists to cross-check against. The pin is retained on the LAT-P077 reading. Live post-move p50 541.4s is 1.04x it, consistent with no step — but that is an argument from the absence of a jump, not from a comparison.",
        note="GRADEABLE since #2071, and the two claims that excluded it were "
        "both wrong. 'ZERO successes in 24h' was FALSE on the 2026-08-21 read: "
        "18 successes / 2 failures. Its p95 is at the 600s clamp because 14% of "
        "runs clip there — and any clip rate above 5% pins a p95 by arithmetic "
        "— but its p50 is 518.4s with real headroom and its durations span two "
        "and a half orders of magnitude (1 of 50 in 10-100s, 20 in 100-500s, 22 "
        "in 500-598s, 7 at the ceiling). It carries exactly the signal the "
        "falsifier wants. The pinned counters below are the pre-move reading "
        "and are deliberately NOT refreshed to the later numbers.",
    ),
)

BASELINE_BY_TASK: Mapping[str, BeatBaseline] = {b.task: b for b in PRE_MOVE_BASELINE}

# The watched set IS the baseline's set. Kept as a name so the routing guard
# test can assert the exception does not overlap what it is supposed to protect.
CALIBRATION_HEAVY_BEATS: frozenset[str] = frozenset(BASELINE_BY_TASK)


@dataclass(frozen=True)
class MoverBaseline:
    """A moved task's pre-move activity, for LAT-P077's prediction P4."""

    task: str
    runs_24h: int
    scheduled_fires_24h: int


# Pinned from LAT-P077 §4 / ruling 110: both movers run far below schedule on
# `background` *because they are starved there*. P4 says that stops.
MOVER_PRE_MOVE: Mapping[str, MoverBaseline] = {
    "app.tasks.backfill_market_shapes": MoverBaseline(
        task="app.tasks.backfill_market_shapes", runs_24h=31, scheduled_fires_24h=72
    ),
    "app.tasks.precompute_backfill_progress": MoverBaseline(
        task="app.tasks.precompute_backfill_progress", runs_24h=45, scheduled_fires_24h=96
    ),
}

# 🔴 THE READ SET — every metrics name this instrument must fetch before it can
# say anything, protected beats AND movers together.
#
# The panel used to read only the seven protected beats and then interrogate
# that same dict about the two movers, which were never in it. The movers were
# therefore reported as `samples: 0` **forever**, and a reader — this program,
# LAT-P078 — took that constant for a measurement and concluded neither task
# had run. `test_the_panel_reads_its_own_subjects` asserts the containment, so
# a subject can never again be graded, or excused, from data nobody fetched.
READ_SET: tuple[str, ...] = tuple(
    sorted(
        {b.metrics_name for b in PRE_MOVE_BASELINE}
        | {METRICS_NAME[t] for t in HEAVY_MOVE_EXCEPTION}
    )
)


@dataclass(frozen=True)
class BeatVerdict:
    task: str
    verdict: str  # degraded | hold | pre_horizon | censored | no_new_runs | unreadable
    reason: str
    baseline_p50_s: float | None = None
    observed_p50_s: float | None = None
    ratio: float | None = None
    post_move_ring_share: float | None = None
    #: WHICH side saturated, when `verdict == "censored"` (#2071). `"baseline"`
    #: means the beat was never readable and tells a reader nothing new;
    #: `"observation"` means it WAS readable and has newly pinned, which is the
    #: loudest fact the panel can carry and must not render the same.
    censored_side: str | None = None
    #: The post-move clip rate, COUNTED from the ring rather than bounded from a
    #: percentile. The observation carries every sample, so reporting a bound
    #: here would throw away data we hold.
    observed_clip_rate: float | None = None
    #: #2116. The three fields that make the two-gate decision auditable from
    #: the payload alone. `ratio_exceeded` is carried even when the verdict is
    #: `hold`, because "the ratio never moved" and "the ratio moved but not
    #: materially" are different facts and a reader must not have to infer
    #: which one they are looking at (gotcha #53, one level in).
    absolute_delta_s: float | None = None
    materiality_floor_s: float | None = None
    ratio_exceeded: bool | None = None
    #: #2116's second half. The ceiling that applied, and whether the delta
    #: cleared it. Carried on EVERY verdict for the same reason `ratio_exceeded`
    #: is: "the ceiling was nowhere near" and "the ceiling fired" must not
    #: render as the same absent value, and a `degraded` that the ratio did not
    #: cause is unauditable without them.
    absolute_ceiling_s: float | None = None
    ceiling_exceeded: bool | None = None


@dataclass(frozen=True)
class MoveVerdict:
    verdict: str  # REVERT | HOLD | INCONCLUSIVE
    reason: str
    beats: tuple[BeatVerdict, ...] = field(default_factory=tuple)

    @property
    def must_revert(self) -> bool:
        return self.verdict == "REVERT"


def _p50(durations_ms: Sequence[float] | None) -> float | None:
    if not durations_ms:
        return None
    vals = sorted(float(d) for d in durations_ms if d is not None)
    if not vals:
        return None
    return vals[len(vals) // 2] / 1000.0


def grade_beat(
    baseline: BeatBaseline,
    observation: Mapping[str, Any] | None,
    *,
    age_since_move_s: float,
) -> BeatVerdict:
    """Grade one watched beat against its pinned pre-move baseline.

    SIX states, never two. `unreadable` (we learned nothing), `no_new_runs`
    (the instrument answered but the beat has not fired), `pre_horizon` (it has
    fired, but not enough since the move for this p50 to be about the move),
    `censored` (the baseline is clamped at its timeout so worse is invisible),
    `degraded` and `hold`. Collapsing any of the first four into `hold` is how a
    falsifier reports itself armed while being blind (gotcha #53).

    🔴 **The horizon test runs BEFORE the ratio, and that ordering is
    load-bearing in both directions.** A p50 drawn mostly from pre-move samples
    can no more prove a regression than it can prove safety, so a `pre_horizon`
    beat must not be able to fire a spurious `degraded` either. The gate
    protects the grant from a false revocation exactly as it protects the
    calibration lane from a false clean bill.
    """
    if observation is None:
        return BeatVerdict(baseline.task, "unreadable", "no observation supplied")

    if baseline.censored:
        budget = (
            f" (its own {baseline.effective_clamp_s:.0f}s budget, not the "
            f"{baseline.soft_time_limit_s}s soft limit — budget-bounded, not "
            "timeout-clamped)"
            if baseline.self_imposed_budget_s is not None
            else f" ({baseline.effective_clamp_s:.0f}s soft limit)"
        )
        return BeatVerdict(
            baseline.task,
            "censored",
            f"baseline {baseline.p50.describe()}{budget} — the statistic this "
            "beat is graded on is itself saturated, so degradation is not "
            f"observable here. Its {baseline.p95.describe()}.",
            baseline_p50_s=baseline.p50_s,
            censored_side="baseline",
        )

    observed = _p50(observation.get("recent_durations_ms"))
    if observed is None:
        return BeatVerdict(
            baseline.task,
            "unreadable",
            "observation carried no durations",
            baseline_p50_s=baseline.p50_s,
        )

    runs = (observation.get("successes_24h") or 0) + (observation.get("failures_24h") or 0)
    if runs == 0:
        # 🔴 #2110 defect (b): `no_new_runs` MUST NOT be asserted over a LIVE
        # RING. The counters and the ring are different instruments with
        # different lifetimes, and this line used to trust only the counter.
        #
        # `successes_24h` / `failures_24h` are not 24 h counts — each window
        # "opens at its own first increment" (`redis_state.py`'s own comment,
        # which is why `successes_window_s` exists), and they EXPIRE. The ring
        # does not. So a beat whose counters have lapsed reads `0 runs in the
        # last 24h` while its ring carries a sample from two hours ago.
        #
        # Measured on production 2026-08-23, this was not hypothetical — it was
        # THREE of the seven watched beats, every one of them demonstrably
        # alive:
        #
        #   compute_time_horizon_calibration  0/0, newest ring sample 13:06:57Z
        #   coverage_metrics                  0/0, newest ring sample 03:07:50Z
        #   calibration_prices                0/0, newest ring sample 14:19:28Z
        #
        # Each was being reported as "nothing has happened since the move to
        # grade" about a beat that had just run. `no_new_runs` is one of the
        # states `grade_move` counts as ungradeable, so this shrank the graded
        # set and pushed the whole panel toward INCONCLUSIVE — an instrument
        # disarming itself on evidence of liveness.
        #
        # The ring is the better witness precisely BECAUSE it does not expire.
        # `now` is reconstructed exactly from the caller's own arithmetic, so
        # no clock is read here (gotcha #44) and no parameter is defaulted into
        # existence for a caller who never considered the horizon.
        newest = _newest_sample_at(observation)
        now_epoch = ROUTING_CHANGE_AT_EPOCH + age_since_move_s
        if newest is not None and (now_epoch - newest) <= RING_LIVENESS_WINDOW_S:
            pass  # the counters lapsed; the beat is alive. Grade it.
        else:
            age_note = (
                f"; newest ring sample is {(now_epoch - newest) / 3600.0:.1f}h old"
                if newest is not None
                else "; ring carries no timestamps to corroborate"
            )
            return BeatVerdict(
                baseline.task,
                "no_new_runs",
                "0 runs on the success/failure counters, and the ring does not "
                f"contradict them{age_note} — nothing has happened since the move to grade",
                baseline_p50_s=baseline.p50_s,
                observed_p50_s=observed,
            )

    # --- the horizon gate (LAT-P079, defect 1) ------------------------------
    # Preferred path: the ring is timestamped, so the post-move samples are
    # separated out EXACTLY and the grade is computed on those alone. The
    # whole-ring p50 above is kept only as the reported `observed_p50_s` when
    # the fallback is in play.
    post_move, ring_n = _post_move_split(observation)

    if post_move is not None:
        share = (len(post_move) / ring_n) if ring_n else 0.0
        if len(post_move) < MIN_POST_MOVE_SAMPLES:
            return BeatVerdict(
                baseline.task,
                "pre_horizon",
                f"{len(post_move)} post-move samples in a {ring_n}-deep ring "
                f"({share:.0%}) at a {age_since_move_s / 3600.0:.1f}h horizon — under the "
                f"{MIN_POST_MOVE_SAMPLES} this p50 needs before it describes the move rather "
                "than the baseline",
                baseline_p50_s=baseline.p50_s,
                observed_p50_s=observed,
                post_move_ring_share=round(share, 3),
            )
        observed = _p50(post_move) or observed
        share = round(share, 3)
    else:
        # Fallback: an unstamped ring. The post-move samples cannot be
        # separated, so the whole-ring p50 is the only statistic available and
        # it is honest only once the ring is majority post-move.
        proven = post_move_runs_lower_bound(runs, age_since_move_s)
        if proven is None:
            return BeatVerdict(
                baseline.task,
                "pre_horizon",
                f"ring carries no timestamps, and only {age_since_move_s / 3600.0:.1f}h since "
                "the routing change — the 24h run counters still straddle it, so no run can be "
                "shown to postdate the move and this p50 is mostly the baseline echoing back",
                baseline_p50_s=baseline.p50_s,
                observed_p50_s=observed,
                post_move_ring_share=0.0,
            )
        needed = max(1, math.ceil(ring_n * POST_MOVE_RING_SHARE_REQUIRED))
        share = min(1.0, proven / ring_n) if ring_n else 0.0
        if proven < needed:
            return BeatVerdict(
                baseline.task,
                "pre_horizon",
                f"ring carries no timestamps; {proven} proven post-move runs against a "
                f"{ring_n}-deep ring ({share:.0%}) — under the "
                f"{POST_MOVE_RING_SHARE_REQUIRED:.0%} majority the whole-ring p50 needs",
                baseline_p50_s=baseline.p50_s,
                observed_p50_s=observed,
                post_move_ring_share=round(share, 3),
            )
        share = round(share, 3)

    # --- the OBSERVATION-side censor (#2071) --------------------------------
    # 🔴 The mirror of the defect #2071 named, and the more dangerous half.
    # `CENSOR_FRACTION_OF_SOFT_LIMIT` was only ever applied to the BASELINE, so
    # nothing stopped a saturated OBSERVATION from being graded. Worked example
    # on the beat #2071 is about: `precompute_backfill_winners_status` at a
    # post-move p50 of 600 s means every run now hits the ceiling — the worst
    # outcome this instrument exists to catch — and 600.0/518.4 = 1.16x is under
    # the 1.25x threshold, so it returned **HOLD**. A saturated instrument read
    # as evidence of safety.
    #
    # It grades `censored`, not `degraded`, for the same reason the horizon gate
    # refuses to fire a spurious REVERT: a statistic that cannot be seen is not
    # evidence in EITHER direction, and a false revocation of ruling 110's grant
    # is a real cost. `censored_side` carries the difference to the reader, and
    # `grade_move` names it, because a beat that was readable and has newly
    # pinned is the loudest fact the panel can hold.
    clamp_ms = baseline.effective_clamp_s * 1000 * CENSOR_FRACTION_OF_SOFT_LIMIT
    graded_samples = post_move if post_move is not None else [
        d for d in (observation.get("recent_durations_ms") or []) if d is not None
    ]
    clip_rate = (
        round(sum(1 for d in graded_samples if float(d) >= clamp_ms) / len(graded_samples), 4)
        if graded_samples
        else None
    )
    observed_reading = Reading(observed, baseline.effective_clamp_s, 0.5, "observed p50")
    if observed_reading.censored:
        return BeatVerdict(
            baseline.task,
            "censored",
            f"🔴 NEWLY SATURATED: {observed_reading.describe()} against a "
            f"readable pre-move p50 of {baseline.p50_s:.1f}s "
            f"({clip_rate:.0%} of post-move runs at the clamp). The beat was "
            "gradeable before the move and is not now, so this reading is "
            "neither a pass nor a fail — but it is the one censored state that "
            "is evidence of something, and it must not be read as a quiet night.",
            baseline_p50_s=baseline.p50_s,
            observed_p50_s=observed,
            post_move_ring_share=share,
            censored_side="observation",
            observed_clip_rate=clip_rate,
        )

    # `post_move_ring_share` rides on the PASSING verdicts too, not only the
    # refusing ones: "how much of this grade is actually about the move" is
    # exactly the question a reader has when the answer is HOLD.
    ratio = observed / baseline.p50_s if baseline.p50_s else None
    delta = observed - baseline.p50_s
    floor = baseline.materiality_floor_s
    ceiling = baseline.absolute_ceiling_s
    ratio_exceeded = ratio is not None and ratio > DEGRADE_P50_RATIO
    # A delta is SIGNED. A beat that got 400s faster has not "cleared" anything,
    # and `abs()` here would be the classic way a tightened gate starts reverting
    # on improvements. `ceiling > 0` guards the degenerate no-headroom beat,
    # which the censor already took above but which must not be reachable by a
    # future reordering of these branches.
    ceiling_exceeded = ceiling > 0.0 and delta >= ceiling

    # --- THE MATERIALITY FLOOR (#2116) --------------------------------------
    # 🔴 BOTH gates, always AND. A pure ratio is most sensitive where a beat
    # matters least — 67x more sensitive to a 4x/day admin precompute than to
    # the one beat a user-facing page waits on — so it converted +4.4s of noise
    # into a mechanical revocation of ruling 110's grant.
    #
    # `immaterial` is a NAMED state, not a fold into `hold`. A floor that
    # silently swallowed a ratio trip would be indistinguishable from a beat
    # that never moved, and the whole complaint in #2116 is that the panel
    # could not tell a noise-scale effect from a page-scale one. It still has
    # to tell you — it just no longer reverts on the first kind.
    if ratio_exceeded and delta < floor:
        return BeatVerdict(
            baseline.task,
            "immaterial",
            f"p50 {observed:.1f}s is {ratio:.2f}x its pre-move {baseline.p50_s:.1f}s "
            f"— OVER the {DEGRADE_P50_RATIO}x ratio — but only +{delta:.1f}s in "
            f"absolute terms, UNDER the {floor:.0f}s materiality floor for a "
            f"'{baseline.consumer}' beat. Reported, not reverted: the ratio moved "
            f"and the reader is entitled to know, but ruling 110's 'degrades "
            f"measurably' is not +{delta:.1f}s on this consumer. Trips at "
            f"{baseline.degrade_trips_at_s:.1f}s. Ring {share:.0%} post-move",
            baseline.p50_s,
            observed,
            ratio,
            share,
            observed_clip_rate=clip_rate,
            absolute_delta_s=round(delta, 3),
            materiality_floor_s=floor,
            ratio_exceeded=True,
            absolute_ceiling_s=ceiling,
            ceiling_exceeded=ceiling_exceeded,
        )

    if ratio_exceeded:
        return BeatVerdict(
            baseline.task,
            "degraded",
            f"p50 {observed:.1f}s is {ratio:.2f}x its pre-move {baseline.p50_s:.1f}s "
            f"(threshold {DEGRADE_P50_RATIO}x) AND +{delta:.1f}s absolute, over the "
            f"{floor:.0f}s materiality floor for a '{baseline.consumer}' beat, "
            f"on a ring {share:.0%} post-move",
            baseline.p50_s,
            observed,
            ratio,
            share,
            observed_clip_rate=clip_rate,
            absolute_delta_s=round(delta, 3),
            materiality_floor_s=floor,
            ratio_exceeded=True,
            absolute_ceiling_s=ceiling,
            ceiling_exceeded=ceiling_exceeded,
        )

    # --- THE PER-CONSUMER CEILING (#2116 second half) -----------------------
    # 🔴 The ratio did NOT trip, and this still degrades. That is the whole
    # point: on `precompute_calibration_main` a +90s median regression is 1.08x,
    # so under the ratio alone the beat a public page waits on could slip a
    # minute and a half and grade `hold`. The reason has to say the ratio did
    # not fire, or the first reader to re-derive 1.08x against a 1.25x threshold
    # will conclude the panel is broken and stop trusting it.
    if ceiling_exceeded:
        return BeatVerdict(
            baseline.task,
            "degraded",
            f"p50 {observed:.1f}s is +{delta:.1f}s over its pre-move "
            f"{baseline.p50_s:.1f}s — AT OR OVER the {ceiling:.0f}s absolute "
            f"ceiling for a '{baseline.consumer}' beat. The {DEGRADE_P50_RATIO}x "
            f"ratio did NOT trip ({ratio:.2f}x) and is not what fired here: a "
            f"ratio scales the bar with the beat's own p50, so a slow beat can "
            f"absorb a large absolute regression without moving it. Ruling 110's "
            f"'degrades measurably' IS +{delta:.1f}s on this consumer. "
            f"Ring {share:.0%} post-move",
            baseline.p50_s,
            observed,
            ratio,
            share,
            observed_clip_rate=clip_rate,
            absolute_delta_s=round(delta, 3),
            materiality_floor_s=floor,
            ratio_exceeded=False,
            absolute_ceiling_s=ceiling,
            ceiling_exceeded=True,
        )
    # The clip rate rides on HOLD too, and that is the point of #2071: a beat
    # can hold on its p50 while a rising share of its runs clip at the clamp,
    # and a panel that only printed the median would show that as no change.
    return BeatVerdict(
        baseline.task,
        "hold",
        f"p50 {observed:.1f}s vs pre-move {baseline.p50_s:.1f}s, "
        f"on a ring {share:.0%} post-move"
        + (f", {clip_rate:.0%} of runs at the clamp" if clip_rate else ""),
        baseline.p50_s,
        observed,
        ratio,
        share,
        observed_clip_rate=clip_rate,
        absolute_delta_s=round(delta, 3),
        materiality_floor_s=floor,
        ratio_exceeded=False,
        absolute_ceiling_s=ceiling,
        ceiling_exceeded=False,
    )


def summarize_movers(
    observations: Mapping[str, Mapping[str, Any] | None],
    *,
    age_since_move_s: float,
) -> dict[str, dict[str, Any]]:
    """The two moved tasks, READ — with absent distinguished from zero.

    🔴 This exists because the route used to build this block from a dict that
    never contained the movers, so `samples` was `0` and the counters were
    `null` for tasks running 29 and 44 times a day. `observed` is the field
    that makes the difference legible: `observed=False` means the metrics hash
    was not there, and every number beside it is `None`, never `0` (gotcha
    #53 — an absent read and a zero read must not render the same).

    Also grades **P4**, LAT-P077's one prediction that could always
    discriminate the intervention: *the movers' 24 h run counts rise toward
    schedule, because they are starved rather than idle.* It is subject to the
    same horizon as everything else — a 24 h counter read 7 minutes after the
    move is a fact about the previous day.
    """
    out: dict[str, dict[str, Any]] = {}
    for task in sorted(HEAVY_MOVE_EXCEPTION):
        name = METRICS_NAME[task]
        obs = observations.get(name)
        pre = MOVER_PRE_MOVE[task]
        if obs is None:
            out[task] = {
                "metrics_name": name,
                "observed": False,
                "reason": "task-metrics carried no entry under this name — NOT a zero",
                "successes_24h": None,
                "failures_24h": None,
                "runs_24h": None,
                "samples": None,
                "pre_move_runs_24h": pre.runs_24h,
                "scheduled_fires_24h": pre.scheduled_fires_24h,
                "p4": "unreadable",
            }
            continue

        runs = (obs.get("successes_24h") or 0) + (obs.get("failures_24h") or 0)
        rate = _runs_per_24h(obs)
        proven = post_move_runs_lower_bound(runs, age_since_move_s)

        # 🔴 #2110 defect (a), BOTH halves. This used to read
        # `runs > pre.runs_24h`, comparing a raw counter sum against a 24 h
        # figure and calling anything else `flat_or_fell`.
        #
        # HALF ONE — the counters are not 24 h counts. Each window "opens at
        # its own first increment" (`redis_state.py`), which is why
        # `successes_window_s` exists and why #2102's "3 of 5 runs failing"
        # was an artefact of dividing two differently-windowed counters. A
        # mover read at a 6 h horizon shows ~a quarter of its day's runs and
        # grades `flat_or_fell` for being early. `_runs_per_24h` rate-corrects
        # each counter against ITS OWN window before adding them.
        #
        # HALF TWO, and it is the one that made the prediction untestable: the
        # prediction is *"the movers' run counts RISE TOWARD SCHEDULE, because
        # they are starved rather than idle."* Schedule is its CEILING. A
        # mover at 100 % of schedule has satisfied the prediction completely
        # and cannot rise further — yet it graded `flat_or_fell`, i.e. FAILED,
        # for being exactly where success is defined to be. `at_schedule` is
        # therefore a PASS, checked BEFORE the comparison, and the honest
        # reading of a starved task that stopped being starved.
        if proven is None:
            p4 = "pre_horizon"
        elif rate is None:
            p4 = "unreadable_rate"
        elif rate >= pre.scheduled_fires_24h * AT_SCHEDULE_FRACTION:
            p4 = "at_schedule"
        elif rate > pre.runs_24h:
            p4 = "rose"
        else:
            p4 = "flat_or_fell"

        out[task] = {
            "metrics_name": name,
            "observed": True,
            "successes_24h": obs.get("successes_24h"),
            "failures_24h": obs.get("failures_24h"),
            "runs_24h": runs,
            #: The rate-corrected figure the grade is actually computed on.
            #: Reported beside the raw counters rather than instead of them,
            #: so a reader can see the correction rather than take it on faith.
            "runs_per_24h": None if rate is None else round(rate, 1),
            "successes_window_s": obs.get("successes_window_s"),
            "failures_window_s": obs.get("failures_window_s"),
            "samples": len([d for d in (obs.get("recent_durations_ms") or []) if d is not None]),
            "pre_move_runs_24h": pre.runs_24h,
            "scheduled_fires_24h": pre.scheduled_fires_24h,
            "at_schedule_threshold_24h": round(
                pre.scheduled_fires_24h * AT_SCHEDULE_FRACTION, 1
            ),
            "p4": p4,
        }
    return out


def beat_payload(b: "BeatVerdict") -> dict[str, Any]:
    """The per-beat JSON block — ONE definition, two consumers.

    🔴 This function exists because the drift it prevents ALREADY HAPPENED.
    `admin_celery.heavy_move_falsifier` and
    `scripts/falsifier_offline_mirror.py` each built this dict by hand, and the
    mirror's own docstring promised it mirrored the route "field for field ...
    If the route's shape changes, this drifts". #2116 added six fields to the
    route and the mirror emitted `null` for every one of them on its first run
    — while still being read as the authoritative re-grade, because the verdict
    field was right and the missing fields render exactly like fields whose
    values are absent (gotcha #53, in a payload rather than an API).

    A shape a reader compares across two producers must have one producer.
    """
    baseline = BASELINE_BY_TASK.get(b.task)
    return {
        "task": b.task,
        "verdict": b.verdict,
        "reason": b.reason,
        "baseline_p50_s": b.baseline_p50_s,
        "observed_p50_s": b.observed_p50_s,
        "ratio": round(b.ratio, 3) if b.ratio is not None else None,
        "post_move_ring_share": b.post_move_ring_share,
        # #2071. `censored_side` distinguishes "never was readable" (tells a
        # reader nothing) from "was readable, has newly pinned" (the loudest
        # fact on the panel). `observed_clip_rate` rides on HOLD too: a beat can
        # hold on its median while a rising share of its runs clip at the clamp,
        # and a panel printing only the median would show that as no change.
        "censored_side": b.censored_side,
        "observed_clip_rate": b.observed_clip_rate,
        # #2116, the materiality floor. All of it printed together so a reader
        # can audit the two-gate decision without re-deriving anything: whether
        # the RATIO tripped, by how many ABSOLUTE seconds, against which FLOOR,
        # and what observed p50 would actually fire a REVERT.
        "ratio_exceeded": b.ratio_exceeded,
        "absolute_delta_s": b.absolute_delta_s,
        "materiality_floor_s": b.materiality_floor_s,
        "consumer": baseline.consumer if baseline else None,
        "degrade_trips_at_s": (
            round(baseline.degrade_trips_at_s, 1) if baseline else None
        ),
        "floor_capped_by_censor": (
            baseline.floor_capped_by_censor if baseline else None
        ),
        # #2116's second half, the per-consumer ceiling. Printed alongside the
        # floor and never instead of it: the trip point is now bounded from BOTH
        # directions, and a reader auditing a `degraded` needs to know which
        # bound fired. A `degraded` with `ratio_exceeded: false` is a CEILING
        # trip and is only legible if the ceiling is on the page.
        "ceiling_exceeded": b.ceiling_exceeded,
        "absolute_ceiling_s": b.absolute_ceiling_s,
        "declared_absolute_ceiling_s": (
            baseline.declared_absolute_ceiling_s if baseline else None
        ),
        "ceiling_capped_by_censor": (
            baseline.ceiling_capped_by_censor if baseline else None
        ),
        # Ruling 120. A baseline is a claim about the system we run in, and a
        # pin taken across a dated step reads as a constant forever — #2102
        # found one here reading ~6x against a healthy beat.
        "baseline_regime": baseline.regime if baseline else None,
        "consumer_note": baseline.consumer_note if baseline else None,
    }


def grade_move(
    observations: Mapping[str, Mapping[str, Any] | None],
    *,
    now_epoch: float,
) -> MoveVerdict:
    """Grade ruling 110's condition. Keyed by METRICS name, not task name.

    Returns REVERT the moment ONE watched beat degrades — the grant is
    conditional on all of them, so any single failure revokes it. Returns
    INCONCLUSIVE, never HOLD, when nothing in the set could be graded: an
    unarmed falsifier must not read as a clean bill of health.

    `now_epoch` is **required and keyword-only** rather than defaulted to
    `time.time()`. A default is how the ungated read gets reintroduced by a
    caller who never thought about the horizon, and it would also make every
    test in this module a function of the wall clock — which is gotcha #44,
    the defect this program has now paid for four times.
    """
    age = now_epoch - ROUTING_CHANGE_AT_EPOCH
    beats: list[BeatVerdict] = []
    for baseline in PRE_MOVE_BASELINE:
        beats.append(
            grade_beat(
                baseline,
                observations.get(baseline.metrics_name),
                age_since_move_s=age,
            )
        )

    degraded = [b for b in beats if b.verdict == "degraded"]
    if degraded:
        names = ", ".join(b.task.rsplit(".", 1)[-1] for b in degraded)
        return MoveVerdict(
            "REVERT",
            f"{len(degraded)} calibration heavy-beat(s) degraded: {names}. "
            "Ruling 110's exception is revoked; revert the routing this window.",
            tuple(beats),
        )

    # #2071: a beat that WAS readable and has newly pinned is not an ordinary
    # exclusion. It is the only censored state that carries information, and it
    # rides on the top-level reason in every outcome — including HOLD, where a
    # saturated sibling beside four holding beats would otherwise be invisible.
    saturated = [b for b in beats if b.censored_side == "observation"]
    saturated_note = (
        " ⚠️ NEWLY SATURATED (readable before the move, pinned at the clamp now, "
        "so neither passing nor failing): "
        + ", ".join(b.task.rsplit(".", 1)[-1] for b in saturated)
        + "."
        if saturated
        else ""
    )

    # #2116: a ratio trip under the materiality floor. It did NOT revert, and it
    # is NOT a quiet night — it rides on the top-level reason exactly as the
    # newly-saturated note does, and for the same reason. The one thing a floor
    # must never buy is silence.
    immaterial = [b for b in beats if b.verdict == "immaterial"]
    immaterial_note = (
        " ⚠️ RATIO TRIPPED BUT IMMATERIAL (#2116 — over the "
        f"{DEGRADE_P50_RATIO}x ratio, under the absolute floor its consumer "
        "class asks for, so reported rather than reverted): "
        + ", ".join(
            f"{b.task.rsplit('.', 1)[-1]} +{b.absolute_delta_s:.1f}s vs a "
            f"{b.materiality_floor_s:.0f}s floor"
            for b in immaterial
        )
        + "."
        if immaterial
        else ""
    )
    saturated_note += immaterial_note

    gradeable = [b for b in beats if b.verdict in ("hold", "immaterial")]
    if not gradeable:
        pre_horizon = [b for b in beats if b.verdict == "pre_horizon"]
        if pre_horizon:
            return MoveVerdict(
                "INCONCLUSIVE",
                f"{len(pre_horizon)} of {len(beats)} watched beats are still PRE-HORIZON "
                f"{age / 3600.0:.1f}h after the routing change — their p50s are drawn mostly "
                "from pre-move samples, so grading them would compare the distribution "
                "against itself. This is NOT evidence the move is safe." + saturated_note,
                tuple(beats),
            )
        return MoveVerdict(
            "INCONCLUSIVE",
            "no watched beat could be graded (all censored, unreadable, or not run) "
            "— this is NOT evidence the move is safe" + saturated_note,
            tuple(beats),
        )
    return MoveVerdict(
        "HOLD",
        f"{len(gradeable)} of {len(beats)} watched beats graded, none degraded "
        f"at a {age / 3600.0:.1f}h horizon" + saturated_note,
        tuple(beats),
    )
