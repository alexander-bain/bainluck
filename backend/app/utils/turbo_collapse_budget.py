"""Derive the `turbo_collapse` pair's `soft_time_limit` from measured history.

LAT-P069 (#1609, #224). This module exists because of the exact shape ruling 075
names: **a budget derived from measured history may never fall below that phase's
own measured floor**, and when the history cannot support a derivation the answer
is a visible refusal, never a default number.

## Why this pair, and why a module instead of two integers

`turbo_collapse_futures` and `turbo_collapse_odds` each carry
`soft_time_limit=3600` on a **2-slot** `background` pool. They fire at `:30` and
`:45` of the same hours (`crontab(minute=30, hour="*/6")` and `minute=45`), so on
their declared schedule a long pair can hold **both** slots at once — a scheduled,
total background outage window with nothing else able to run.

Until LAT-P068 neither called `_tracked_run`, so neither wrote a start or a
terminal, so `/api/admin/task-metrics?task=turbo_collapse_futures` answered
`no_data` and the largest occupant of the pool had **no gauge at all**
(ruling 086). The instrumentation rides `program/latency-61`; this module is what
consumes it once it lands.

## The measured floor — provenance, not folklore

Both numbers below come from LAT-P068's S4 occupancy capture
(`docs/audits/latency/lat-p068-s4-occupancy.jsonl`), which sampled celery's
`active` set once a minute for 62 minutes and recorded each occupant's
`time_start` as celery itself reported it. A completion is therefore **bracketed**
— last sample the task was present, first sample it was gone — and both brackets
here are closed by *good* samples on both sides:

| task | `time_start` | last seen | first absent | completion |
|---|---|---|---|---|
| `turbo_collapse_futures` | 19:23:52.08Z | 19:37:05.81Z (idx 18) | 19:38:05.84Z (idx 19) | **(793.7, 853.8] s** |
| `turbo_collapse_odds` | 19:55:11.12Z | 20:02:05.98Z (idx 43) | 20:03:05.99Z (idx 44) | **(414.9, 474.9] s** |

`MEASURED_FLOOR_S` records the **upper** end of each bracket, because that is the
value a budget must not fall below: it is a duration we have *watched this task
complete at*. Killing a run at less than that is killing work we know is normal.

⚠️ **These are n=1 each.** A single observation has no dispersion, so it cannot
produce a p95, and this module will not pretend otherwise — see `MIN_SAMPLES`.

⚠️ **The observer's clock ran ~5.2 s ahead of the worker's** (`turbo_collapse_odds`
was first *seen* 5.19 s before its own reported `time_start`). The brackets above
are wide enough to absorb that; a tighter derivation than 60 s granularity would
not be.

## What the schedule separation is actually worth — measured, and it is not 900 s

The two beats are 900 s apart on paper. Their **observed starts were 1,879 s
apart**, because each waited a different amount of time in a saturated queue:
`futures` was published at 18:30Z and started at 19:23:52Z (**53.9 min** of queue
delay); `odds` was published at 18:45Z and started at 19:55:11Z (**70.2 min**).

So the 15-minute schedule gap does **not** survive a saturated `background`
queue — and a saturated queue is precisely the condition under which an overlap
would matter. Any argument of the form "they cannot overlap, they are scheduled
15 minutes apart" is refuted by this measurement. It is recorded here rather than
acted on: re-timing a beat is a schedule change, which is a different
intervention from bounding a budget.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: The largest duration at which each task has been **observed to complete**.
#: See the module docstring for provenance. A derived budget below one of these
#: is refused, not clamped (ruling 075).
MEASURED_FLOOR_S: dict[str, float] = {
    "turbo_collapse_futures": 853.8,
    "turbo_collapse_odds": 474.9,
}

#: Where each floor came from, carried alongside the number so a reader never has
#: to trust it on the strength of being hard-coded. Ruling 074: a value names the
#: work that produced it.
MEASURED_FLOOR_PROVENANCE: dict[str, str] = {
    "turbo_collapse_futures": (
        "LAT-P068 S4 celery `active` capture 2026-08-18; time_start 19:23:52.08Z, "
        "last present 19:37:05.81Z (idx 18), first absent 19:38:05.84Z (idx 19); "
        "completion bracketed to (793.7, 853.8] s; n=1"
    ),
    "turbo_collapse_odds": (
        "LAT-P068 S4 celery `active` capture 2026-08-18; time_start 19:55:11.12Z, "
        "last present 20:02:05.98Z (idx 43), first absent 20:03:05.99Z (idx 44); "
        "completion bracketed to (414.9, 474.9] s; n=1"
    ),
}

#: The `soft_time_limit` currently wired on each task's decorator, mirrored here so
#: a guard test can assert the two never drift apart. Changing the decorator without
#: changing this — or vice versa — turns
#: `tests/test_lat_p069_turbo_collapse_budget.py` red on purpose.
WIRED_SOFT_TIME_LIMIT_S: dict[str, int] = {
    "turbo_collapse_futures": 3600,
    "turbo_collapse_odds": 3600,
}

#: Below this many recorded completions, no percentile is computed and no budget is
#: derived. The verdict is `could_not_measure` and the budget is left ALONE.
#:
#: Five is not a statistical claim; it is the point at which a nearest-rank p95 stops
#: being a synonym for `max()`. At n=1 they are literally the same number, and
#: "the p95 is 853.8 s" would be a sentence with a distribution's authority and one
#: observation behind it. LAT-P068 registered this as prediction P3 with its own
#: halt — *the 3600 s budget must not be touched on the strength of one observation*
#: — and that halt is honoured here in code rather than in prose.
MIN_SAMPLES: int = 5

#: Multiplier applied to the measured p95 to leave room for the variance a bounded
#: sample cannot see. Declared as a **safety factor**, not an estimate: it is the one
#: number here that is chosen rather than measured, and it is isolated on its own line
#: so that is impossible to miss. It shrinks as `recent_durations_n` grows; the
#: re-derivation trigger is registered in
#: `docs/audits/latency/lat-p069-turbo-collapse-budget.md`.
SAFETY_FACTOR: float = 2.0

#: Budgets are rounded up to a whole minute. Finer granularity than this would be
#: false precision against a 60 s sampling interval and a ~5 s clock skew.
ROUND_TO_S: int = 60

COULD_NOT_MEASURE = "could_not_measure"
DERIVED = "derived"
REFUSED_BELOW_FLOOR = "refused_below_floor"


@dataclass(frozen=True)
class BudgetDecision:
    """One task's answer, carrying the numbers that produced it.

    Ruling 075 property 2: a refusal that says only "budget too small" cannot be
    acted on by the next reader, so `measured_floor_s`, `p95_s` and
    `derived_soft_time_limit_s` all ride along **whatever the verdict is**.
    """

    task: str
    verdict: str
    #: `None` for every verdict except `derived`. A refusal never carries a number
    #: that could be mistaken for an answer.
    derived_soft_time_limit_s: int | None
    wired_soft_time_limit_s: int | None
    measured_floor_s: float | None
    p95_s: float | None
    samples_n: int
    reason: str
    provenance: str | None = None

    @property
    def actionable(self) -> bool:
        """True only when a number was actually derived and differs from the wire."""
        return (
            self.verdict == DERIVED
            and self.derived_soft_time_limit_s is not None
            and self.derived_soft_time_limit_s != self.wired_soft_time_limit_s
        )

    def as_dict(self) -> dict:
        return {
            "task": self.task,
            "verdict": self.verdict,
            "derived_soft_time_limit_s": self.derived_soft_time_limit_s,
            "wired_soft_time_limit_s": self.wired_soft_time_limit_s,
            "measured_floor_s": self.measured_floor_s,
            "p95_s": self.p95_s,
            "samples_n": self.samples_n,
            "reason": self.reason,
            "provenance": self.provenance,
            "actionable": self.actionable,
        }


def nearest_rank_p95(durations_ms: list[int] | tuple[int, ...]) -> float | None:
    """p95 in seconds by nearest rank, or `None` for an empty sample.

    Nearest rank rather than interpolation because the sample is small and bounded
    by `DURATION_HISTORY_LEN`; interpolating between two observations invents a
    duration that was never recorded, which is the thing this whole module exists
    to avoid.
    """
    clean = sorted(float(d) for d in durations_ms if d is not None and float(d) >= 0)
    if not clean:
        return None
    idx = max(0, math.ceil(0.95 * len(clean)) - 1)
    return clean[idx] / 1000.0


def _round_up(seconds: float) -> int:
    return int(math.ceil(seconds / ROUND_TO_S) * ROUND_TO_S)


def derive_budget(
    task: str,
    durations_ms: list[int] | tuple[int, ...] | None,
    *,
    min_samples: int = MIN_SAMPLES,
    safety_factor: float = SAFETY_FACTOR,
) -> BudgetDecision:
    """Derive one task's `soft_time_limit`, or refuse and say why.

    Three outcomes, and only one of them is a number:

    * ``could_not_measure`` — fewer than `min_samples` recorded completions. This
      is the state on the day this module was written, and it is the state ruling
      075's second clause is about: *"could not check" must never render as
      "nothing to report."* The budget is left exactly as wired.
    * ``refused_below_floor`` — the arithmetic produced a budget beneath a duration
      this task has been watched completing at. Refused loudly, naming both
      numbers; the budget is left exactly as wired.
    * ``derived`` — a real number, at or above the measured floor.

    `durations_ms` is `recent_durations_ms` from
    `redis_state.get_task_metrics(task)` — newest first, bounded by
    `DURATION_HISTORY_LEN`. Order is irrelevant here; the percentile sorts.
    """
    floor = MEASURED_FLOOR_S.get(task)
    provenance = MEASURED_FLOOR_PROVENANCE.get(task)
    wired = WIRED_SOFT_TIME_LIMIT_S.get(task)
    samples = [d for d in (durations_ms or []) if d is not None]
    n = len(samples)

    if n < min_samples:
        return BudgetDecision(
            task=task,
            verdict=COULD_NOT_MEASURE,
            derived_soft_time_limit_s=None,
            wired_soft_time_limit_s=wired,
            measured_floor_s=floor,
            p95_s=None,
            samples_n=n,
            reason=(
                f"{n} recorded completion(s), need {min_samples} before a p95 means "
                f"anything other than max(). Budget left at {wired}s. This is "
                f"COULD-NOT-MEASURE, not a finding that {wired}s is right."
            ),
            provenance=provenance,
        )

    p95_s = nearest_rank_p95(samples)
    if p95_s is None:  # pragma: no cover - n >= min_samples implies a value
        return BudgetDecision(
            task=task,
            verdict=COULD_NOT_MEASURE,
            derived_soft_time_limit_s=None,
            wired_soft_time_limit_s=wired,
            measured_floor_s=floor,
            p95_s=None,
            samples_n=n,
            reason="no usable duration values in a non-empty sample",
            provenance=provenance,
        )

    candidate = _round_up(p95_s * safety_factor)

    if floor is not None and candidate < floor:
        return BudgetDecision(
            task=task,
            verdict=REFUSED_BELOW_FLOOR,
            derived_soft_time_limit_s=None,
            wired_soft_time_limit_s=wired,
            measured_floor_s=floor,
            p95_s=p95_s,
            samples_n=n,
            reason=(
                f"derived {candidate}s from p95 {p95_s:.1f}s x{safety_factor} is BELOW the "
                f"measured floor {floor}s — a duration this task has been observed "
                f"completing at. Ruling 075: refuse, do not clamp. Budget left at {wired}s."
            ),
            provenance=provenance,
        )

    return BudgetDecision(
        task=task,
        verdict=DERIVED,
        derived_soft_time_limit_s=candidate,
        wired_soft_time_limit_s=wired,
        measured_floor_s=floor,
        p95_s=p95_s,
        samples_n=n,
        reason=(
            f"p95 {p95_s:.1f}s over {n} completions x{safety_factor} safety factor, "
            f"rounded up to {ROUND_TO_S}s = {candidate}s (floor {floor}s)"
        ),
        provenance=provenance,
    )


def derive_all(metrics_by_task: dict[str, dict] | None) -> list[dict]:
    """Render both tasks' decisions from `get_task_metrics()` payloads.

    Shaped for an admin surface. `metrics_by_task` maps task label ->
    the dict `redis_state.get_task_metrics()` returns; a task missing from the
    mapping, or carrying `status: no_data`, is reported as `could_not_measure`
    with `samples_n: 0` rather than being silently dropped — a task that is
    absent from a census and a task with nothing to report are different facts
    (gotcha #53).
    """
    out: list[dict] = []
    for task in WIRED_SOFT_TIME_LIMIT_S:
        payload = (metrics_by_task or {}).get(task) or {}
        durations = payload.get("recent_durations_ms") or []
        out.append(derive_budget(task, durations).as_dict())
    return out
