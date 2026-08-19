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

#: Two counters opened at different moments do not describe the same window, so
#: subtracting one from the other is the cross-window arithmetic this module was
#: built to refuse. Comparable within this fraction, or the difference is not
#: reported at all — and it is reported as ``None`` (unknown), never as 0.
SELF_GATE_WINDOW_TOLERANCE = 0.1

#: Below this fraction of fires, a start/delivery gap is counter noise at the
#: window boundary, not a gate. Measured: the ungated control
#: ``sync_statpal_livescores`` read 2,186 deliveries against 2,177 starts — a
#: 0.4% gap, from two counters born ~30s apart. The number is still reported;
#: this only decides whether the surface says a SENTENCE about it, because a
#: health surface that editorialises about noise is one people stop reading.
SELF_GATE_MATERIAL_RATIO = 0.1

#: A task whose p95 runtime exceeds this fraction of its own interval is lapping
#: (at 1.0 it has literally no gap between runs). Flagged below 1.0 because a
#: task using 80% of its period has no headroom for a slow day and is one
#: upstream hiccup from overlapping.
OVERRUN_RATIO = 0.8

#: How many of its own intervals a beat may go without any recorded activity
#: before the STAMP arm (below) calls it ``missing``.
#:
#: Not 1.0, and the reason is the defect this arm exists to route around. A
#: punctual daily beat sits at age 0.99x its interval for the last minutes of
#: every cycle, so a 1.0 threshold flips it to ``missing`` every time a fire
#: runs ten minutes late — a boundary that a *correct* system crosses daily.
#: That is the same shape as the counter race in §3 of the LAT-P070 T5 protocol
#: (``WINDOW_COUNTER_TTL`` == a daily cadence), and replacing one cadence-equals-
#: threshold bug with another would be a poor trade.
#:
#: At 2.0 the claim is unambiguous and cannot flap: **an entire scheduled fire
#: came and went with nothing recorded.** Lateness short of that is reported as
#: a number (``stamp_age_over_interval``) and not as a verdict, which is exactly
#: what T5 asks for — *late, never missing*.
STAMP_LATE_TOLERANCE = 2.0


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


def _sample_scope(out):
    """The parenthetical that stops a p95 being read as a window property.

    Empty when the span is unknown (a history written before LAT-P040 carries no
    timestamps) rather than guessed at — an invented span would be worse than
    the silence it replaces, because it would look authoritative.
    """
    n = out.get("p95_sample_n") or 0
    span = out.get("p95_window_s")
    if not n:
        return ""
    if span is None:
        return f" (over the last {n} runs; span unknown)"
    bits = f" (over the last {n} runs spanning {span/60.0:.0f}min"
    if out.get("p95_sample_saturated"):
        # Not decoration: at the cap, older runs existed and were dropped, so
        # this p95 CANNOT describe the counter window it is printed next to.
        bits += ", sample saturated — older runs discarded"
    return bits + ")"


def expected_fires(window_s, interval_s):
    """How many times the beat should have fired inside a counter's window."""
    if not window_s or not interval_s or interval_s <= 0:
        return None
    return window_s / float(interval_s)


def rate_arm_is_structurally_blind(interval_s, counter_ttl_s):
    """Can the RATE arm *ever* grade a beat this slow? Arithmetic, not a guess.

    LAT-P071. The rate arm needs ``window_s / interval_s >= MIN_EXPECTED_FIRES``.
    ``window_s`` is the age of a counter created ``SET NX EX <ttl>`` at its own
    first increment, so it is bounded above by ``counter_ttl_s`` and by nothing
    else. Therefore::

        gradeable  <=>  interval_s <= counter_ttl_s / MIN_EXPECTED_FIRES

    At the production values (86400s TTL, 2.0 fires) that ceiling is **12 hours**,
    and every beat slower than it is ``unmeasurable`` *forever* — not today, not
    until the counter warms up, but for as long as both constants hold.

    Measured on production 2026-08-19T04:3xZ: **33 of 123** scheduled entries are
    on the wrong side of that line, all 24-hourly or weekly, and they include
    **five of the six sentinels T5 grades**. The rate arm reported every one of
    them as ``window_too_short(expected=0.89<2.0)``, a string that reads as a
    transient condition about to clear. It never clears. Naming the two cases
    apart is most of this function's value: a reader who cannot tell "wait for
    the counter" from "this can never be answered this way" will keep waiting.

    Returns ``False`` when ``counter_ttl_s`` is unknown, because an unknown TTL
    cannot support the claim *forever* and asserting it anyway would be the same
    over-reach in the opposite direction.
    """
    if not interval_s or interval_s <= 0 or not counter_ttl_s or counter_ttl_s <= 0:
        return False
    return interval_s > counter_ttl_s / MIN_EXPECTED_FIRES


def _grade_on_stamp(
    out, interval_s, newest_terminal_age_s, newest_start_age_s, counter_ttl_s
):
    """The second arm: grade a too-slow beat on its STAMPS instead of its counters.

    LAT-P071, generalising §3 and §6 of the LAT-P070 T5 grading protocol from the
    one task it was written for to the 33 that need it.

    A stamp is a moment, not a count, so it carries its own age and needs no
    window. That is the entire reason this works where the rate arm cannot: the
    thing that defeats the rate arm — a counter TTL shorter than two intervals —
    has no purchase on a timestamp.

    THE THREE BRANCHES ARE THE PROTOCOL'S, NOT NEW ONES:

    * a terminal inside tolerance -> **it ran**. Late is not a fail; T5's whole
      claim is *late, never missing*, and lateness leaves as a number.
    * no terminal but a START inside tolerance -> **it still ran.** Adherence
      asks whether the beat fires, and it fired. Whether it then finished is
      #1716's open question and already has its own flag (``never_completes``);
      answering it here would decide that question by accident, which this
      module refuses to do elsewhere and will not start doing here.
    * neither -> **``missing``**. The only reading that triggers T5's halt, and
      the only one this arm will assert.

    No stamp at all is ``unmeasurable`` — an absent observation is a shape, not
    an observed absence (gotcha #53). It is *not* graded ``missing``, which is
    the mistake that would make this arm worse than the silence it replaces:
    a task that has simply never been seen would be reported as one that stopped.
    """
    out["arm"] = "stamp"
    ages = [(a, k) for a, k in
            ((newest_terminal_age_s, "terminal"), (newest_start_age_s, "start"))
            if a is not None and a >= 0]
    ceiling = counter_ttl_s / MIN_EXPECTED_FIRES if counter_ttl_s else None
    blind_note = (
        f"rate arm blind (interval {interval_s:.0f}s > "
        f"{ceiling:.0f}s ceiling from counter TTL)"
        if ceiling else "rate arm blind"
    )
    if not ages:
        out["reason"] = f"{blind_note}; no start or terminal stamp recorded"
        return out

    age, kind = min(ages)
    out["stamp_age_s"] = round(age, 1)
    out["stamp_kind"] = kind
    out["stamp_age_over_interval"] = round(age / interval_s, 2)

    if age <= interval_s * STAMP_LATE_TOLERANCE:
        out["verdict"] = "on_schedule"
        out["reason"] = (
            f"{blind_note}; graded on stamps: newest {kind} {age/3600.0:.1f}h ago, "
            f"{out['stamp_age_over_interval']:.2f}x its {interval_s:.0f}s interval"
        )
        return out

    out["verdict"] = "missing"
    out["reason"] = (
        f"{blind_note}; graded on stamps: newest {kind} {age/3600.0:.1f}h ago, "
        f"{out['stamp_age_over_interval']:.2f}x its {interval_s:.0f}s interval "
        f"(>{STAMP_LATE_TOLERANCE:.1f}x — at least one whole scheduled fire "
        f"recorded nothing)"
    )
    return out


def adherence(
    *,
    starts,
    starts_window_s,
    interval_s,
    terminals=None,
    durations_ms=None,
    deliveries=None,
    deliveries_window_s=None,
    durations_window_s=None,
    durations_saturated=None,
    newest_terminal_age_s=None,
    newest_start_age_s=None,
    counter_ttl_s=None,
):
    """Grade one task's schedule adherence from its recorded counters.

    THE NUMERATOR. ``starts`` used to be it, on the stated grounds that it
    "counts fires that BEGAN, which is what 'is the beat actually running?'
    asks". That was wrong, and LAT-P039 measured how wrong. ``starts`` is
    written by ``record_task_started`` from inside ``_tracked_run`` — a helper
    the *task body* calls — so it counts fires whose body chose to call it,
    which a body decides only after its own gate has already run. A task that
    deliberately declines to work is indistinguishable, in that number, from a
    beat that never fired.

    ``deliveries`` is the honest numerator: celery's ``task_prerun`` sees every
    delivery of every task before any body runs. When it is available it is
    used, and ``starts`` becomes what it always actually was — the count of
    fires that went on to do work. The gap between them is
    ``self_gated_fires``, a first-class number rather than a phantom shortfall.

    Measured on production 2026-08-11, which is why this is not a refactor:
    ``poll_all_odds`` graded ``ratio 0.50`` for two months and was read as the
    ingestion beat running at half speed. Its realtime worker had executed it 66
    times in the 1,982s since the release — one per 30.0s, its beat interval, to
    three significant figures. Every "missing" fire was ``should_poll_now()``
    declining on purpose, because ``LIVE_POLL_INTERVAL`` (32s) is longer than
    the beat (30s) and two consecutive fires can therefore never both pass.

    ``terminals`` is still reported rather than graded — whether adherence
    should own completion is an open product question (#1716) and inventing a
    verdict here would answer it by accident. What is NOT open, and is fixed, is
    that a task with fires and zero completions was omitted from the work-list
    entirely; ``never_completes`` flags it so ``find_lapping`` can carry it
    without pre-empting the taxonomy.

    LAT-P040 (#835): ``window_s`` ages the STARTS counter and nothing else. The
    duration sample is bounded by COUNT, so it carries its own, much shorter and
    per-task-different span — passed in as ``durations_window_s`` and reported
    as ``p95_window_s`` rather than left to be read off the field above it. This
    module's founding defect was a count whose age was unstated; the p95 landed
    with exactly the same defect one field to the right, and it cost a queue:
    `poll_all_odds` p95 46.2s (a ~50-minute burst) was recorded as a property of
    a 19-hour window and staged as the top standing item, then read 5.8s an hour
    later with nothing changed but the samples.

    Returns a dict rather than raising, because this grades the health surface
    and a health surface that throws is a health surface that goes dark.
    """
    # A delivery count is only usable with a window to age it against — a count
    # of unknown age is not a rate, which is the whole LAT-P024 lesson and the
    # reason this falls back rather than guessing.
    use_deliveries = deliveries is not None and deliveries_window_s
    fires = deliveries if use_deliveries else starts
    window_s = deliveries_window_s if use_deliveries else starts_window_s

    exp = expected_fires(window_s, interval_s)
    out = {
        "interval_s": interval_s,
        "window_s": window_s,
        "expected_fires": round(exp, 2) if exp is not None else None,
        "starts": starts,
        "deliveries": deliveries,
        "numerator": "deliveries" if use_deliveries else "starts",
        "self_gated_fires": None,
        "terminals": terminals,
        "never_completes": False,
        "ratio": None,
        "p95_duration_ms": None,
        "p95_over_interval": None,
        "p95_sample_n": len(durations_ms or []),
        "p95_window_s": durations_window_s,
        "p95_sample_saturated": durations_saturated,
        "arm": "rate",
        "stamp_age_s": None,
        "stamp_kind": None,
        "stamp_age_over_interval": None,
        "rate_arm_blind": rate_arm_is_structurally_blind(interval_s, counter_ttl_s),
        "verdict": "unmeasurable",
        "reason": "",
    }

    # Clamped at zero: a body can legitimately record a start in one 24h window
    # while the delivery that produced it was counted in the previous one, and a
    # negative "self-gated" count would be nonsense reported as fact. Computed
    # only across COMPARABLE windows — the delivery counter is born at its own
    # deploy, so for the first day it is much younger than the starts counter it
    # would be differenced against, and that subtraction means nothing.
    if use_deliveries and starts is not None and starts_window_s:
        widest = max(deliveries_window_s, starts_window_s)
        drift = abs(deliveries_window_s - starts_window_s) / widest
        if drift <= SELF_GATE_WINDOW_TOLERANCE:
            out["self_gated_fires"] = max(0, (deliveries or 0) - (starts or 0))

    # A task that fires and never finishes is the sharpest failure there is, and
    # the surface used to call it healthy (#1716). Gated on having enough fires
    # for the absence to mean something — the same refusal `unmeasurable` makes.
    if terminals == 0 and (starts or 0) >= MIN_EXPECTED_FIRES:
        out["never_completes"] = True

    p95 = percentile(durations_ms or [], 0.95)
    out["p95_duration_ms"] = p95
    if p95 is not None and interval_s:
        out["p95_over_interval"] = round(p95 / 1000.0 / interval_s, 2)

    if exp is None or exp < MIN_EXPECTED_FIRES:
        # The rate arm cannot speak. Before falling back to silence, ask WHY it
        # cannot — the two reasons need different words and, since LAT-P071, get
        # a different arm.
        if out["rate_arm_blind"]:
            return _grade_on_stamp(
                out, interval_s, newest_terminal_age_s, newest_start_age_s,
                counter_ttl_s,
            )
        if exp is None:
            out["reason"] = "no_interval_or_window"
            return out
        # The honest answer, and now an honestly TRANSIENT one: this counter is
        # young for its interval and will age into gradeability on its own.
        out["reason"] = (
            f"window_too_short(expected={exp:.2f}<{MIN_EXPECTED_FIRES}); "
            "transient — the counter can still reach this interval"
        )
        return out

    ratio = (fires or 0) / exp
    out["ratio"] = round(ratio, 2)

    # Runtime-over-interval is checked FIRST and reported even when the fire
    # rate looks fine, because it is the *cause* shape: a task using ~all of its
    # period is already lapping, and the fire count only collapses later, once
    # the backlog has built. Naming it early is the whole point of the detector.
    if out["p95_over_interval"] is not None and out["p95_over_interval"] >= OVERRUN_RATIO:
        out["verdict"] = "overruns"
        # The reason states the sample this p95 came from, not just the number.
        # An `overruns` that reads as a 19-hour property when it describes 50
        # minutes is a claim the data cannot support, and it is the exact claim
        # LAT-P039 made in good faith off this string.
        out["reason"] = (
            f"p95 {p95/1000.0:.1f}s is {out['p95_over_interval']:.2f}x its "
            f"{interval_s}s interval"
            f"{_sample_scope(out)}"
        )
        return out

    if ratio < BEHIND_RATIO:
        out["verdict"] = "behind"
        noun = "deliveries" if use_deliveries else "starts"
        out["reason"] = (
            f"{fires or 0} {noun} against {exp:.1f} scheduled "
            f"in {window_s:.0f}s"
        )
        return out

    out["verdict"] = "on_schedule"
    gated = out["self_gated_fires"] or 0
    if fires and gated / fires >= SELF_GATE_MATERIAL_RATIO:
        # Not a defect and deliberately not a verdict — the beat is on time and
        # the task chose to skip. Said out loud anyway, because this exact
        # silence is what let 1,089 intentional skips be read as lateness.
        out["reason"] = (
            f"delivered on schedule; {gated} of {fires} fires "
            f"self-gated before doing work"
        )
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
    """The work-list: every task that is not both on schedule AND completing.

    Ordered worst-first by how far off schedule it is, so the top of the list is
    the thing to fix. ``unmeasurable`` sorts last and is carried rather than
    dropped — a task nobody can grade is itself a finding.

    ``never_completes`` sorts ABOVE every schedule verdict and is included even
    when the verdict is ``on_schedule``. #1716: ``precompute_interestingness``
    had 10 starts, ZERO terminals, graded ``on_schedule`` with an empty reason,
    and was omitted from this list — a function whose docstring called itself
    the work-list was hiding the clearest failure a task can have, because the
    verdict it filtered on is computed from fires alone. Whether *adherence*
    should own a completion verdict is still open; whether the WORK-LIST may
    silently drop a task that has never once finished is not.
    """
    # LAT-P071: ``missing`` sorts above everything. It is the only verdict that
    # asserts a beat produced NOTHING across a whole scheduled fire, and it is
    # the one that triggers T5's halt — a work-list that buried it under a
    # lapping-but-running task would invert the urgency. The other values are
    # unchanged so the existing relative order is preserved exactly.
    order = {"missing": -1, "overruns": 0, "behind": 1, "unmeasurable": 3}

    def _key(item):
        _name, g = item
        return (
            0 if g.get("never_completes") else 1,
            order.get(g["verdict"], 2),
            g["ratio"] if g["ratio"] is not None else 99,
        )

    return [
        {"task": name, **g}
        for name, g in sorted(graded.items(), key=_key)
        if g["verdict"] != "on_schedule" or g.get("never_completes")
    ]
