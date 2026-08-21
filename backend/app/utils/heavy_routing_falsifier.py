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

    # `post_move_ring_share` rides on the PASSING verdicts too, not only the
    # refusing ones: "how much of this grade is actually about the move" is
    # exactly the question a reader has when the answer is HOLD.
    ratio = observed / baseline.p50_s if baseline.p50_s else None
    if ratio is not None and ratio > DEGRADE_P50_RATIO:
        return BeatVerdict(
            baseline.task,
            "degraded",
            f"p50 {observed:.1f}s is {ratio:.2f}x its pre-move {baseline.p50_s:.1f}s "
            f"(threshold {DEGRADE_P50_RATIO}x), on a ring {share:.0%} post-move",
            baseline.p50_s,
            observed,
            ratio,
            share,
        )
    return BeatVerdict(
        baseline.task,
        "hold",
        f"p50 {observed:.1f}s vs pre-move {baseline.p50_s:.1f}s, "
        f"on a ring {share:.0%} post-move",
        baseline.p50_s,
        observed,
        ratio,
        share,
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
        proven = post_move_runs_lower_bound(runs, age_since_move_s)
        if proven is None:
            p4 = "pre_horizon"
        elif runs > pre.runs_24h:
            p4 = "rose"
        else:
            p4 = "flat_or_fell"
        out[task] = {
            "metrics_name": name,
            "observed": True,
            "successes_24h": obs.get("successes_24h"),
            "failures_24h": obs.get("failures_24h"),
            "runs_24h": runs,
            "samples": len([d for d in (obs.get("recent_durations_ms") or []) if d is not None]),
            "pre_move_runs_24h": pre.runs_24h,
            "scheduled_fires_24h": pre.scheduled_fires_24h,
            "p4": p4,
        }
    return out


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

    gradeable = [b for b in beats if b.verdict == "hold"]
    if not gradeable:
        pre_horizon = [b for b in beats if b.verdict == "pre_horizon"]
        if pre_horizon:
            return MoveVerdict(
                "INCONCLUSIVE",
                f"{len(pre_horizon)} of {len(beats)} watched beats are still PRE-HORIZON "
                f"{age / 3600.0:.1f}h after the routing change — their p50s are drawn mostly "
                "from pre-move samples, so grading them would compare the distribution "
                "against itself. This is NOT evidence the move is safe.",
                tuple(beats),
            )
        return MoveVerdict(
            "INCONCLUSIVE",
            "no watched beat could be graded (all censored, unreadable, or not run) "
            "— this is NOT evidence the move is safe",
            tuple(beats),
        )
    return MoveVerdict(
        "HOLD",
        f"{len(gradeable)} of {len(beats)} watched beats graded, none degraded "
        f"at a {age / 3600.0:.1f}h horizon",
        tuple(beats),
    )
