"""Pure contract from recorded task counters to a SCHEDULE-ADHERENCE verdict.

LAT-P022 (#1609). ``task_verdict`` answers "did this run do its work?" and
CAL-P024b's ``record_task_started`` answers "did this run begin at all?". The
question still unanswered — and the one #1609 was filed about — is **"did it
run as often as it is scheduled to?"**

Nothing in the recorded metrics could answer it, for a reason worth stating
plainly: ``successes_24h`` is a counter of *unknown age*. The key is created on
its first increment with a 24h TTL, so at any instant it holds somewhere
between 0 and 24 hours of history and the payload never says which. A reader
comparing it against a 24h expectation is not measuring, it is assuming — and
on 2026-08-09 that assumption was wrong by a factor of ~24: six fixed-cadence
tasks whose counters read 52-63 all had windows about ONE HOUR old, so a
perfectly healthy 30-second task looked like it was missing 96% of its fires.

So adherence needs two things the store did not keep:

1. **The window start**, so a count becomes a rate. That is
   ``*_window_s`` here, written by ``_bump_window_counter``.
2. **Duration history**, so "p95 runtime exceeds the interval" — the textbook
   definition of a task lapping itself — is computable at all. Only
   ``last_duration_ms`` was kept, and one sample cannot see a tail.

Everything below is pure: it takes the recorded numbers and the beat interval
and returns a verdict. The Redis reads live in ``tasks/redis_state.py`` and the
beat intervals come from ``celery_app.conf.beat_schedule`` itself, so the
detector can never drift from the schedule it grades.

THE REFUSAL THAT MATTERS. ``unmeasurable`` is a first-class verdict, not an
error case. A counter window of 90 seconds tells you nothing about an hourly
task, and a detector that reports "0 of 0.025 expected fires — BEHIND!" is
manufacturing an alarm out of an absence of evidence. This module refuses to
grade until the window has had room for ``MIN_EXPECTED_FIRES`` fires. Gotcha
#53 in the detector rather than the data: an empty observation is a shape, not
a fact.
"""

from __future__ import annotations

#: A window must have had room for at least this many fires before a shortfall
#: means anything. At 2 expected, observing 0 is a real signal; at 0.3 expected,
#: observing 0 is the overwhelmingly likely outcome for a perfectly healthy task
#: and says nothing at all.
MIN_EXPECTED_FIRES = 2.0

#: Below this fraction of its scheduled fires, a task is not keeping up. Not 1.0:
#: beat/worker clock alignment, a deploy restart, and a self-gating task that
#: exits early all cost a fire or two legitimately, and a detector that pages on
#: 0.98 gets muted, which is worse than not having it.
BEHIND_RATIO = 0.6

#: A task whose p95 runtime exceeds this fraction of its own interval is lapping
#: (at 1.0 it has literally no gap between runs). Flagged below 1.0 because a
#: task using 80% of its period has no headroom for a slow day and is one
#: upstream hiccup from overlapping.
OVERRUN_RATIO = 0.8


def percentile(values, p: float):
    """Nearest-rank percentile. ``None`` for an empty sample.

    Nearest-rank rather than interpolated because these are durations from a
    short bounded history (tens of samples); interpolating between two of them
    implies a precision the sample size does not carry.
    """
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    if p <= 0:
        return vals[0]
    if p >= 1:
        return vals[-1]
    rank = int(-(-len(vals) * p // 1))  # ceil
    return vals[min(rank, len(vals)) - 1]


def expected_fires(window_s, interval_s):
    """How many times the beat should have fired inside a counter's window."""
    if not window_s or not interval_s or interval_s <= 0:
        return None
    return window_s / float(interval_s)


def adherence(
    *,
    starts,
    starts_window_s,
    interval_s,
    terminals=None,
    durations_ms=None,
):
    """Grade one task's schedule adherence from its recorded counters.

    ``starts`` is the numerator on purpose. It counts fires that BEGAN, which is
    what "is the beat actually running?" asks; completions are a separate
    question already graded by ``task_verdict`` and by ``hard_kills_24h``. Both
    are reported so a caller can tell "never started" from "started and died".

    Returns a dict rather than raising, because this grades the health surface
    and a health surface that throws is a health surface that goes dark.
    """
    exp = expected_fires(starts_window_s, interval_s)
    out = {
        "interval_s": interval_s,
        "window_s": starts_window_s,
        "expected_fires": round(exp, 2) if exp is not None else None,
        "starts": starts,
        "terminals": terminals,
        "ratio": None,
        "p95_duration_ms": None,
        "p95_over_interval": None,
        "verdict": "unmeasurable",
        "reason": "",
    }

    p95 = percentile(durations_ms or [], 0.95)
    out["p95_duration_ms"] = p95
    if p95 is not None and interval_s:
        out["p95_over_interval"] = round(p95 / 1000.0 / interval_s, 2)

    if exp is None:
        out["reason"] = "no_interval_or_window"
        return out
    if exp < MIN_EXPECTED_FIRES:
        # The honest answer. A 90-second window has nothing to say about an
        # hourly beat, and saying it anyway is how a detector earns its mute.
        out["reason"] = (
            f"window_too_short(expected={exp:.2f}<{MIN_EXPECTED_FIRES})"
        )
        return out

    ratio = (starts or 0) / exp
    out["ratio"] = round(ratio, 2)

    # Runtime-over-interval is checked FIRST and reported even when the fire
    # rate looks fine, because it is the *cause* shape: a task using ~all of its
    # period is already lapping, and the fire count only collapses later, once
    # the backlog has built. Naming it early is the whole point of the detector.
    if out["p95_over_interval"] is not None and out["p95_over_interval"] >= OVERRUN_RATIO:
        out["verdict"] = "overruns"
        out["reason"] = (
            f"p95 {p95/1000.0:.1f}s is {out['p95_over_interval']:.2f}x its "
            f"{interval_s}s interval"
        )
        return out

    if ratio < BEHIND_RATIO:
        out["verdict"] = "behind"
        out["reason"] = (
            f"{starts or 0} starts against {exp:.1f} scheduled "
            f"in {starts_window_s:.0f}s"
        )
        return out

    out["verdict"] = "on_schedule"
    return out


def schedule_interval_s(schedule):
    """A celery beat ``schedule`` value -> its mean interval in seconds.

    Handles the three shapes this repo's beat schedule actually uses: a bare
    number of seconds, a ``timedelta``, and a ``crontab``. Anything else returns
    ``None`` and is graded ``unmeasurable`` — a schedule the detector cannot
    read must not be silently assigned a plausible-looking interval, because a
    wrong interval produces a confident wrong verdict, which is worse than an
    admitted gap.

    For a crontab this is the MEAN interval across a day (86400 / fires per
    day), not the gap between two particular fires. A ``crontab(minute=47)``
    fires 24 times a day at an even 3600s spacing so the two agree; a clustered
    schedule such as ``minute="0,1,2"`` would have a mean of 28800s while three
    of its gaps are 60s. Mean is the right basis here because adherence divides
    a WINDOW by it — "how many fires should have fit in this window" — and that
    is exactly a mean-rate question.
    """
    if schedule is None:
        return None
    if isinstance(schedule, bool):
        return None
    if isinstance(schedule, (int, float)):
        return float(schedule) if schedule > 0 else None
    total = getattr(schedule, "total_seconds", None)
    if callable(total):  # timedelta
        secs = total()
        return float(secs) if secs > 0 else None
    # celery crontab: parsed field sets, already expanded from "*/5" etc.
    try:
        minutes = len(schedule.minute)
        hours = len(schedule.hour)
        dows = len(schedule.day_of_week)
        doms = len(schedule.day_of_month)
        moys = len(schedule.month_of_year)
    except (AttributeError, TypeError):
        return None
    if not (minutes and hours and dows and doms and moys):
        return None
    # Restricted day/month fields make a task fire on only some days; fold that
    # into the mean so a weekly sentinel is not graded as if it ran daily.
    day_fraction = (dows / 7.0) * (doms / 31.0) * (moys / 12.0)
    fires_per_day = minutes * hours * day_fraction
    if fires_per_day <= 0:
        return None
    return 86400.0 / fires_per_day


def beat_intervals(beat_schedule):
    """Collapse a celery beat schedule to ``task name -> effective interval_s``.

    Read from the live ``celery_app.conf.beat_schedule`` rather than
    re-declared, so the detector grades the schedule that is actually loaded and
    a new beat entry is covered the moment it is added.

    The shape this must get right, because it has already misled readers of the
    raw queue sample: **one task can have several beat entries.**
    ``sync_statpal_schedules`` has four (nba/nhl/mlb/nfl) and
    ``collapse_snapshots`` has three. Four copies of one of those pending is
    four different jobs, not one task stacked four deep — and since the metrics
    are keyed by task, its effective cadence is the SUM of its entries' rates.
    Intervals therefore combine reciprocally; taking any single entry's interval
    would under-count the expectation by up to 4x and report a healthy task as
    behind.
    """
    rates = {}
    for entry in (beat_schedule or {}).values():
        task = entry.get("task")
        iv = schedule_interval_s(entry.get("schedule"))
        if not task or not iv or iv <= 0:
            continue
        rates[task] = rates.get(task, 0.0) + 1.0 / iv
    return {t: 1.0 / r for t, r in rates.items() if r > 0}


def find_lapping(graded):
    """The work-list: every task whose verdict is not ``on_schedule``.

    Ordered worst-first by how far off schedule it is, so the top of the list is
    the thing to fix. ``unmeasurable`` sorts last and is carried rather than
    dropped — a task nobody can grade is itself a finding.
    """
    order = {"overruns": 0, "behind": 1, "unmeasurable": 3}

    def _key(item):
        _name, g = item
        return (
            order.get(g["verdict"], 2),
            g["ratio"] if g["ratio"] is not None else 99,
        )

    return [
        {"task": name, **g}
        for name, g in sorted(graded.items(), key=_key)
        if g["verdict"] != "on_schedule"
    ]
