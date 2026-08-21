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
"""

from __future__ import annotations

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
    note: str = ""

    @property
    def metrics_name(self) -> str:
        return METRICS_NAME[self.task]

    @property
    def censored(self) -> bool:
        """True when p95 sits at the soft time limit, so worse cannot be seen.

        A beat clamped at its own timeout reports the SAME number however much
        further behind it falls. Grading it would manufacture a `hold` out of
        a saturated instrument, which is the flattering direction.
        """
        return self.p95_s >= CENSOR_FRACTION_OF_SOFT_LIMIT * self.soft_time_limit_s


# Degradation thresholds. Deliberately generous: the falsifier exists to catch
# a real regression on the calibration lane, not to trip on ordinary variance
# in beats whose p50/p95 spread is already an order of magnitude wide.
DEGRADE_P50_RATIO = 1.25
CENSOR_FRACTION_OF_SOFT_LIMIT = 0.98

# ---------------------------------------------------------------------------
# PRE-MOVE BASELINE — measured 2026-08-20T16:40-16:47Z against production
# build v3873 (`086ce799`), via GET /api/admin/celery/task-metrics/<name>,
# BEFORE the routing change of ruling 110 shipped. n is that endpoint's
# `recent_durations_ms` ring.
#
# Two of the seven are ALREADY CENSORED at their 600 s soft limit and carry
# ZERO successes in 24 h. They are watched and reported, but they cannot
# falsify anything, and this file says so rather than counting them as
# evidence of safety.
# ---------------------------------------------------------------------------
PRE_MOVE_BASELINE: tuple[BeatBaseline, ...] = (
    BeatBaseline(
        task="app.tasks.precompute_calibration_main",
        soft_time_limit_s=1500,
        p50_s=214.7,
        p95_s=1302.1,
        max_s=1357.2,
        samples=50,
        successes_24h=21,
        failures_24h=1,
        note="the hourly :15 warmer — the one beat a user-facing page waits on. "
        "p95 is 87% of its soft limit, so it is gradeable but has little headroom.",
    ),
    BeatBaseline(
        task="app.tasks.compute_calibration_prices",
        soft_time_limit_s=600,
        p50_s=538.2,
        p95_s=599.9,
        max_s=600.3,
        samples=37,
        successes_24h=0,
        failures_24h=1,
        note="CENSORED at the 600s soft limit, 0 successes/24h. Already failing "
        "before the move; cannot show degradation.",
    ),
    BeatBaseline(
        task="app.tasks.compute_time_horizon_calibration",
        soft_time_limit_s=600,
        p50_s=302.0,
        p95_s=302.7,
        max_s=304.0,
        samples=40,
        successes_24h=0,
        failures_24h=0,
        note="unusually tight distribution (302.0-304.0s); 0 runs in the last 24h, "
        "so `no_new_runs` is the expected verdict until it fires.",
    ),
    BeatBaseline(
        task="app.tasks.compute_fair_fight_comparison",
        soft_time_limit_s=600,
        p50_s=147.8,
        p95_s=268.4,
        max_s=323.9,
        samples=37,
        successes_24h=3,
        failures_24h=0,
        note="gradeable with real headroom.",
    ),
    BeatBaseline(
        task="app.tasks.precompute_source_intelligence",
        soft_time_limit_s=600,
        p50_s=17.5,
        p95_s=27.3,
        max_s=41.2,
        samples=40,
        successes_24h=2,
        failures_24h=0,
        note="the cleanest subject in the set: tight, fast, far from its limit. "
        "If the move hurts the heavy lane, this is where it shows first.",
    ),
    BeatBaseline(
        task="app.tasks.snapshot_coverage_metrics",
        soft_time_limit_s=600,
        p50_s=480.1,
        p95_s=482.1,
        max_s=482.1,
        samples=10,
        successes_24h=0,
        failures_24h=0,
        note="only 10 samples and 0 runs in 24h; weak but readable.",
    ),
    BeatBaseline(
        task="app.tasks.precompute_backfill_winners_status",
        soft_time_limit_s=600,
        p50_s=518.4,
        p95_s=601.0,
        max_s=601.1,
        samples=50,
        successes_24h=0,
        failures_24h=2,
        note="CENSORED at the 600s soft limit, 0 successes/24h, 2 failures. "
        "Already failing before the move; cannot show degradation.",
    ),
)

BASELINE_BY_TASK: Mapping[str, BeatBaseline] = {b.task: b for b in PRE_MOVE_BASELINE}

# The watched set IS the baseline's set. Kept as a name so the routing guard
# test can assert the exception does not overlap what it is supposed to protect.
CALIBRATION_HEAVY_BEATS: frozenset[str] = frozenset(BASELINE_BY_TASK)


@dataclass(frozen=True)
class BeatVerdict:
    task: str
    verdict: str  # degraded | hold | censored | no_new_runs | unreadable
    reason: str
    baseline_p50_s: float | None = None
    observed_p50_s: float | None = None
    ratio: float | None = None


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


def grade_beat(baseline: BeatBaseline, observation: Mapping[str, Any] | None) -> BeatVerdict:
    """Grade one watched beat against its pinned pre-move baseline.

    Five states, never two. `unreadable` (we learned nothing), `no_new_runs`
    (the instrument answered but the beat has not fired), `censored` (the
    baseline is clamped at its timeout so worse is invisible), `degraded` and
    `hold`. Collapsing any of the first three into `hold` is how a falsifier
    reports itself armed while being blind (gotcha #53).
    """
    if observation is None:
        return BeatVerdict(baseline.task, "unreadable", "no observation supplied")

    if baseline.censored:
        return BeatVerdict(
            baseline.task,
            "censored",
            f"baseline p95 {baseline.p95_s:.1f}s is at the {baseline.soft_time_limit_s}s "
            "soft limit — degradation is not observable on this beat",
            baseline_p50_s=baseline.p50_s,
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
        return BeatVerdict(
            baseline.task,
            "no_new_runs",
            "0 runs in the last 24h — nothing has happened since the move to grade",
            baseline_p50_s=baseline.p50_s,
            observed_p50_s=observed,
        )

    ratio = observed / baseline.p50_s if baseline.p50_s else None
    if ratio is not None and ratio > DEGRADE_P50_RATIO:
        return BeatVerdict(
            baseline.task,
            "degraded",
            f"p50 {observed:.1f}s is {ratio:.2f}x its pre-move {baseline.p50_s:.1f}s "
            f"(threshold {DEGRADE_P50_RATIO}x)",
            baseline.p50_s,
            observed,
            ratio,
        )
    return BeatVerdict(
        baseline.task,
        "hold",
        f"p50 {observed:.1f}s vs pre-move {baseline.p50_s:.1f}s",
        baseline.p50_s,
        observed,
        ratio,
    )


def grade_move(observations: Mapping[str, Mapping[str, Any] | None]) -> MoveVerdict:
    """Grade ruling 110's condition. Keyed by METRICS name, not task name.

    Returns REVERT the moment ONE watched beat degrades — the grant is
    conditional on all of them, so any single failure revokes it. Returns
    INCONCLUSIVE, never HOLD, when nothing in the set could be graded: an
    unarmed falsifier must not read as a clean bill of health.
    """
    beats: list[BeatVerdict] = []
    for baseline in PRE_MOVE_BASELINE:
        beats.append(grade_beat(baseline, observations.get(baseline.metrics_name)))

    degraded = [b for b in beats if b.verdict == "degraded"]
    if degraded:
        names = ", ".join(b.task.rsplit(".", 1)[-1] for b in degraded)
        return MoveVerdict(
            "REVERT",
            f"{len(degraded)} calibration heavy-beat(s) degraded: {names}. "
            "Ruling 110's exception is revoked; revert the routing this window.",
            tuple(beats),
        )

    gradeable = [b for b in beats if b.verdict == "hold"]
    if not gradeable:
        return MoveVerdict(
            "INCONCLUSIVE",
            "no watched beat could be graded (all censored, unreadable, or not run) "
            "— this is NOT evidence the move is safe",
            tuple(beats),
        )
    return MoveVerdict(
        "HOLD",
        f"{len(gradeable)} of {len(beats)} watched beats graded, none degraded",
        tuple(beats),
    )
