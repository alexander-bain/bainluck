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

#: Celery ``--concurrency`` per worker queue, from ``backend/Procfile``.
#:
#: LAT-P242 (#3466). Mirrored here rather than read at runtime because the
#: Procfile is not on a path the dyno can rely on, and pinned against the
#: Procfile text for all three queues by
#: ``test_worker_concurrency_mirror_matches_the_procfile`` — the same guard that
#: already pinned the background entry alone, widened, so a concurrency change
#: cannot land silently on any queue.
#:
#: This is the DENOMINATOR of every capacity claim this lane makes: a queue's
#: capacity is ``slots x 3600`` worker-seconds per hour, and demand measured
#: against the wrong slot count is not a measurement. ``background``'s 2 is a
#: MEMORY bound, not a preference — 2 x 200MB + ~100MB overhead fits a 512MB
#: Standard-1X exactly — so raising it is a dyno purchase and never a config
#: edit. See the routing block in ``app/tasks/__init__.py``.
QUEUE_SLOTS = {"realtime": 4, "background": 2, "heavy": 2}

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

#: Below this fraction of a bucket's publications, an undelivered gap is bucket-
#: boundary spill, not broker loss — LAT-P238, resized under CERT-1966.
#:
#: 🔴 IT IS NUMERICALLY EQUAL TO ``SELF_GATE_MATERIAL_RATIO`` AND NO LONGER
#: DERIVED FROM IT. The first version of this field compared two independently
#: born 24h window counters, so it inherited that constant's noise argument
#: wholesale. The matched-bucket repair removed that noise source entirely —
#: there are no longer two birthdays — and left a different one, so the value
#: stays and the reasoning does not.
#:
#: The residual noise is SPILL: a message published at second 599 of a bucket is
#: delivered in the next one, so a perfectly healthy task can under-report by up
#: to one fire per bucket. That is 1-in-15 at the 40s rail this instrument was
#: built for, which 0.10 covers — but it is 1-in-2 for a 300s beat, which no
#: fraction threshold covers at all. Hence the SECOND term at the call site:
#: material requires the gap to exceed one whole fire as well. A fraction alone
#: would editorialise about a single boundary message on every slow beat in the
#: schedule.
#:
#: That absolute term IS a subtraction, and it is the one place this module
#: permits one: the two counts come from the SAME bucket, so they describe the
#: same span and the cross-window arithmetic this module refuses is not in play.
#: It is also never published — it decides whether a ``behind`` verdict says a
#: SENTENCE, nothing more. The fraction itself is on every row regardless.
UNDELIVERED_MATERIAL_RATIO = 0.10

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

#: An absolute FLOOR under the tolerance above, in seconds.
#:
#: Two intervals is the right shape for a slow beat and a hair-trigger for a fast
#: one: at a 10s cadence it would call a beat ``missing`` after twenty seconds of
#: ordinary jitter — a deploy restart, one slow upstream call, a worker recycling
#: a child. The stamp arm reaches fast beats only via the no-window route (their
#: starts counter expired), so this floor is what keeps that route from becoming
#: an alarm generator.
#:
#: 300s is chosen against the two numbers that bracket it: comfortably above any
#: jitter a 10-60s beat can produce, and two orders of magnitude below the
#: **2h 55m** `warm_typeahead` stall this arm exists to catch (1,050x its own
#: interval). A threshold with nothing on either side of it is a guess; this one
#: has both.
STAMP_MIN_TOLERANCE_S = 300.0


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


def _newest_stamp(newest_terminal_age_s, newest_start_age_s):
    """``(age_s, kind)`` of the freshest usable stamp, or ``None``.

    Shared by BOTH arms on purpose. The negative-age guard below is the whole
    reason this is a function: a clock-skewed stamp yields a negative age, which
    sails through every ``age <= limit`` comparison as the freshest reading
    possible and certifies a dead beat as healthy. That guard was written once
    for the stamp arm and has a mutation test on it; giving the rate arm its own
    copy of the same three lines is how the two would drift apart.
    """
    ages = [
        (a, k)
        for a, k in (
            (newest_terminal_age_s, "terminal"),
            (newest_start_age_s, "start"),
        )
        if a is not None and a >= 0
    ]
    return min(ages) if ages else None


def _stamp_tolerance_s(interval_s):
    """How old the newest stamp may be before a beat is ``missing``.

    One definition, used by both arms. See ``STAMP_LATE_TOLERANCE`` and
    ``STAMP_MIN_TOLERANCE_S`` for why the two terms and why these values.
    """
    return max(interval_s * STAMP_LATE_TOLERANCE, STAMP_MIN_TOLERANCE_S)


def _self_gate_fraction(deliveries, deliveries_window_s, starts, starts_window_s):
    """Fraction of delivered fires whose body declined to start, or ``None``.

    RATES, NOT COUNTS, AND THAT IS THE ENTIRE POINT. ``self_gated_fires`` above
    is a SUBTRACTION, so it is only computed when the two counters describe
    comparable windows (``SELF_GATE_WINDOW_TOLERANCE``) and is ``None``
    otherwise — correctly, because subtracting across unequal windows is this
    module's founding defect. But "the windows drifted" is not "the task does
    not self-gate", and the veto below needs an answer in exactly that case:
    measured on production 2026-09-05, ``poll_all_odds`` had a delivery window
    of 64,957s against a starts window of 49,447s — a 23.9% drift, so
    ``self_gated_fires`` was ``None`` — while genuinely self-gating.

    Dividing each count by its OWN window first makes the comparison window-safe
    without the cross-window arithmetic the module refuses: two rates measured
    over two spans are comparable even when the spans are not. On the same
    production reading that is 2024/64957 = 0.0312 deliveries/s against
    1318/49447 = 0.0267 starts/s, so 14.5% of fires self-gated — against
    ``prewarm_live_feed_shapes``, dead four hours, at 1327/79469 vs 1327/80011
    = 0.68%. A 21x separation either side of ``SELF_GATE_MATERIAL_RATIO``.

    ``None`` means UNKNOWN — no delivery counter, or a window of zero — and the
    caller must not read it as zero. That is gotcha #53 in the small: the
    absence of an observation is not an observation of absence, and the veto
    treats the two oppositely.
    """
    if deliveries is None or not deliveries_window_s or not starts_window_s:
        return None
    if deliveries_window_s <= 0 or starts_window_s <= 0:
        return None
    delivery_rate = deliveries / deliveries_window_s
    if delivery_rate <= 0:
        return None
    start_rate = (starts or 0) / starts_window_s
    # Clamped into [0, 1]: a start rate above the delivery rate is counter noise
    # at a window boundary, not a negative gate, and reporting -0.03 as fact is
    # the same over-reach the clamp on `self_gated_fires` exists to prevent.
    return max(0.0, min(1.0, 1.0 - (start_rate / delivery_rate)))


def _undelivered_fraction(matched_emitted, matched_delivered):
    """Fraction of a bucket's PUBLICATIONS that never reached a worker, or ``None``.

    LAT-P238-EMIT-SIDE-COUNTER, as repaired under CERT-1966. Both arguments come
    from ONE wall-clock bucket — ``get_matched_emit_delivery`` reads the emit and
    delivery counters that share a bucket index — so this is a ratio within a
    single matched cohort and not a comparison of two populations.

    THE FIRST VERSION OF THIS FUNCTION TOOK FOUR ARGUMENTS AND WAS BLOCKED, and
    the reason is worth keeping in front of whoever edits it next. It divided a
    new emission count by its own window and a 24h delivery count by its own
    window, and compared the rates. Dividing by each counter's own age fixes the
    UNIT mismatch and leaves the POPULATION mismatch untouched — the emission
    counter is born at the deploy that ships it while the delivery counter
    deliberately preserves up to a day of PRE-deploy behaviour. CERT-1966's
    counterexample: 90 emitted in 3600s against 1080 delivered in 86400s is
    produced BOTH by a healthy current hour (90 delivered, plus 990 older) and by
    an hour losing half its fires (45 delivered, plus 1035 older). The old code
    reported 50% for both, with a sentence naming the broker — on a rail whose
    queue had just been moved, i.e. exactly when a change-point is the only thing
    being looked for. An average over a long window cannot see a change-point;
    that is #1790's founding defect, and it had been committed inside the field
    built to escape it.

    No tolerance can rescue that comparison, so there is none here. Two counts in
    one 600s bucket cover the same span by construction.

    ``None`` means UNKNOWN and must not be read as zero:

    * ``matched_delivered`` is ``None`` when the fleet-wide bucketed delivery
      writer has not been seen — the state of the whole system for one bucket
      after the release. Reading it as 0 would report 100% loss on every beat in
      the schedule at the moment the instrument is first trusted.
    * fewer than ``MIN_EXPECTED_FIRES`` publications in the bucket is the same
      refusal the rate arm makes: at 1 expected, observing 0 says nothing, and a
      detector that manufactures 100% from one sample gets muted.

    Clamped into ``[0, 1]``. More deliveries than publications is the bucket
    boundary — a message published at second 599 lands in the next bucket — not
    negative loss.
    """
    if matched_emitted is None or matched_delivered is None:
        return None
    if matched_emitted < MIN_EXPECTED_FIRES:
        return None
    return max(0.0, min(1.0, 1.0 - (matched_delivered / matched_emitted)))


def bucket_attribution(matched_emitted, matched_delivered, matched_bucket_s,
                       interval_s):
    """Which end lost the fires, decided ON THE COMPLETED BUCKET — CERT-1969.

    Returns one of ``None`` (nothing can be said), ``"current_bucket_healthy"``,
    ``"scheduler"``, ``"broker_or_worker"``, ``"both"``.

    🔴 THE ATTRIBUTION MUST COME FROM THE SAME COHORT AS THE NUMBERS, and the
    first repair got that wrong. It fixed the QUOTIENT — matched buckets, no
    pre-deploy history — and then still drove the SENTENCE off the 24h `behind`
    verdict: any row that was behind over a day and had a non-material bucket
    fraction printed "the shortfall is at the SCHEDULER — the messages were
    never published". CERT-1969's reproduction: 15 emitted and 15 delivered in
    the current bucket, against 15 expected, is a perfectly healthy cohort, and
    that row accused the scheduler. The 24h shortfall is real and is simply not
    something this bucket saw.

    So the bucket answers with its OWN expectation, ``matched_bucket_s /
    interval_s``, and there are two independent questions rather than one:

    * did beat PUBLISH what the schedule asked for in this bucket?
    * was what it published DELIVERED?

    which gives the four honest answers, and the bus's own worked examples:

    ==================  ==================  ==========================
    published           delivered           attribution
    ==================  ==================  ==========================
    15 of 15 expected   15 of 15            ``current_bucket_healthy``
    7 of 15 expected    7 of 7              ``scheduler``
    15 of 15 expected   7 of 15             ``broker_or_worker``
    7 of 15 expected    3 of 7              ``both``
    ==================  ==================  ==========================

    ``current_bucket_healthy`` is a first-class answer and not a shrug: it says
    the shortfall the verdict is complaining about did not happen in the window
    this instrument can see. Reporting that honestly is the difference between
    an instrument and an alarm.

    Both shortfalls are judged materially, on the same two-part test the
    fraction uses — a fraction floor AND more than one whole fire — because one
    fire spilling over a bucket boundary is the expected reading of a healthy
    task, and on a slow beat it is a large fraction of a small bucket.
    """
    if matched_emitted is None or matched_delivered is None:
        return None
    if not matched_bucket_s or not interval_s or interval_s <= 0:
        return None
    if matched_emitted < MIN_EXPECTED_FIRES:
        return None
    expected = matched_bucket_s / float(interval_s)
    if expected < MIN_EXPECTED_FIRES:
        return None

    def _short(actual, of):
        gap = of - actual
        return gap > 1 and (gap / of) >= UNDELIVERED_MATERIAL_RATIO

    under_published = _short(matched_emitted, expected)
    under_delivered = _short(matched_delivered, matched_emitted)
    if under_published and under_delivered:
        return "both"
    if under_published:
        return "scheduler"
    if under_delivered:
        return "broker_or_worker"
    return "current_bucket_healthy"


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
    stamp = _newest_stamp(newest_terminal_age_s, newest_start_age_s)
    ceiling = counter_ttl_s / MIN_EXPECTED_FIRES if counter_ttl_s else None
    if not out["rate_arm_blind"]:
        # Reached via the no-window route, not the too-slow one. Say which, or a
        # reader sees "rate arm blind (interval 10s > 43200s ceiling)" and
        # correctly concludes the grader is broken.
        blind_note = "rate arm mute (no counter window — the counter has expired)"
    elif ceiling:
        blind_note = (f"rate arm blind (interval {interval_s:.0f}s > "
                      f"{ceiling:.0f}s ceiling from counter TTL)")
    else:
        blind_note = "rate arm blind"
    if stamp is None:
        out["reason"] = f"{blind_note}; no start or terminal stamp recorded"
        return out

    age, kind = stamp
    out["stamp_age_s"] = round(age, 1)
    out["stamp_kind"] = kind
    out["stamp_age_over_interval"] = round(age / interval_s, 2)

    tolerance_s = _stamp_tolerance_s(interval_s)
    if age <= tolerance_s:
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
        f"(over a {tolerance_s:.0f}s tolerance — at least one whole scheduled "
        f"fire recorded nothing)"
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
    matched_emitted=None,
    matched_delivered=None,
    matched_bucket_s=None,
    matched_bucket_start=None,
    matched_coverage_proven=False,
    lease_declines=None,
    lease_declines_window_s=None,
    durations_window_s=None,
    durations_saturated=None,
    newest_terminal_age_s=None,
    newest_start_age_s=None,
    newest_delivery_age_s=None,
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
    declining, because ``LIVE_POLL_INTERVAL`` (32s) was longer than the beat
    (30s) and two consecutive fires could therefore never both pass.

    🔴 **THAT DECLINE WAS NOT "ON PURPOSE", WHICH IS WHAT THIS PARAGRAPH USED TO
    CLAIM (LAT-P159).** The numerator fix above is correct and stands. What was
    wrong was filing the CAUSE as a design: a 32s gate against a 30s beat was an
    accident that doubled every live sport's odds cadence, and recording it here
    as intended behaviour is what made it invisible — this is the surface that
    would otherwise have flagged a task throwing away half its deliveries.
    ``LIVE_POLL_INTERVAL`` is now derived from ``ODDS_POLL_BEAT_SECONDS``, so a
    large ``self_gated_fires`` on ``poll_all_odds`` is a finding again, not a
    footnote.

    ``matched_emitted`` / ``matched_delivered`` are NOT a third numerator and
    must never become one. LAT-P238: every other count here is taken at-or-after
    delivery, so the module could localise a 35% shortfall to "before delivery"
    and then say nothing about which side of the broker it happened on. These
    two are the same 600s wall-clock bucket counted at ``before_task_publish``
    and at ``task_prerun``, purely so ``_undelivered_fraction`` can answer that —
    reported, never graded on. Grading on them would swap one blind spot for
    another: a task the broker throws away has a perfect emission count and does
    no work at all.

    They are a MATCHED COHORT and the pairing is not interchangeable with the
    fields beside them. Pairing ``matched_emitted`` with ``deliveries`` — the 24h
    counter one line up — is CERT-1966's defect exactly: that counter survives
    deploys and holds pre-change history, so the quotient cannot distinguish a
    healthy current hour from one losing half its fires.

    ``lease_declines`` is reported and never graded on either, for a reason
    that is NOT the same as the emit counter's. It is not a schedule fact at
    all: a tick that found ``single_flight``'s lease held was delivered, ran,
    and declined — the beat was perfect. It is on the row because it splits a
    number that was already there. ``self_gated_fires`` is
    ``max(0, deliveries - starts)``, i.e. everything that drops between
    ``task_prerun`` and ``_tracked_run``, and on ``poll_all_odds`` that is two
    gates in series (the lease, then ``should_poll_now()``). Publishing the
    lease's share makes the cadence gate's share readable by subtraction; folded
    together neither number means anything.

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
        # LAT-P238: published EXPLICITLY rather than left to be read off
        # `window_s`, which is the deliveries window on some rows and the starts
        # window on others depending on which numerator won. A reader dividing
        # the emit count by its window has to divide the delivery count by the
        # RIGHT one, and "whichever this row happened to grade on" is not it.
        "deliveries_window_s": deliveries_window_s,
        # LAT-P238-EMIT-SIDE-COUNTER, as repaired under CERT-1966: the first
        # count in this payload taken ABOVE the delivery boundary, and the
        # delivery count from the SAME wall-clock bucket beside it. The two are a
        # matched cohort by construction, which is the only shape in which their
        # quotient identifies anything — see `_undelivered_fraction`.
        #
        # `matched_delivered` is NOT `deliveries` and the names are kept apart on
        # purpose: `deliveries` is the 24h counter the rate arm grades on and
        # carries pre-deploy history, and pairing THAT with an emission count is
        # the defect this field exists to not have. Never a numerator, never
        # folded into `self_gated_fires`; the `numerator` field below still names
        # only the two counters that can grade.
        "matched_emitted": matched_emitted,
        "matched_delivered": matched_delivered,
        "matched_bucket_s": matched_bucket_s,
        "matched_bucket_start": matched_bucket_start,
        # CERT-1972: did BOTH counters cover the whole bucket, or only a suffix
        # of it? Published, because every derived number below is conditional on
        # it and a reader has to be able to see which state produced a `None`.
        "matched_coverage_proven": bool(matched_coverage_proven),
        "undelivered_fraction": None,
        # CERT-1969: which end, decided on the SAME bucket as the two
        # counts above — never inherited from the 24h verdict.
        "bucket_attribution": None,
        # LAT-P238 ITEM 3, on lane1b's spec and under its three constraints:
        # its OWN field (never folded into `self_gated_fires`, which is a
        # superset counting the lease gate AND the cadence gate), never a
        # numerator, and carrying its own window — because a count without its
        # age is not a rate, and this counter's age was previously unreadable
        # through the only surface that exposed it.
        #
        # On EVERY row, not only `lapping[]` as originally specified. A task
        # that declines its lease on every tick and is therefore NOT lapping is
        # precisely the row a reader needs this number on, and `lapping[]`
        # filters it out.
        "lease_declines": lease_declines,
        "lease_declines_window_s": lease_declines_window_s,
        "numerator": "deliveries" if use_deliveries else "starts",
        "self_gated_fires": None,
        # Both default to None on EVERY row so the payload shape does not depend
        # on which branch graded it — a key that appears only when the veto was
        # considered makes `.get()` mean two different things to a reader.
        "self_gate_fraction": None,
        "stamp_veto_withheld": None,
        # CERT-1943: the delivery MOMENT, published beside the delivery COUNT
        # for the same reason `stamp_age_s` is published beside the fire count —
        # a reader asked to trust a withheld veto has to be able to see the
        # evidence it was withheld on. Defaulted on every row, like the two
        # above, so the payload shape never depends on which branch graded it.
        "delivery_age_s": None,
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

    # LAT-P238: computed on EVERY row, before any branch returns, and outside
    # the `use_deliveries` gate above. A row that never reaches the rate arm —
    # `unmeasurable`, `window_too_short`, either stamp branch — is exactly a row
    # whose reader most needs to know whether anything is being published, and a
    # field that only appears on the branches that happened to fall through
    # makes `.get("undelivered_fraction")` mean two different things.
    undelivered = (
        _undelivered_fraction(matched_emitted, matched_delivered)
        if matched_coverage_proven else None
    )
    out["undelivered_fraction"] = (
        round(undelivered, 3) if undelivered is not None else None
    )
    # CERT-1972: no derived reading at all from a bucket the instrumentation
    # only partly covered. A 7-published/7-delivered bucket is a perfect cadence
    # over half a window and a 53% scheduler shortfall over the whole one, and
    # nothing in the counts says which — so it says nothing.
    attribution = (
        bucket_attribution(
            matched_emitted, matched_delivered, matched_bucket_s, interval_s
        )
        if matched_coverage_proven else None
    )
    out["bucket_attribution"] = attribution

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
        # cannot — the reasons need different words and, since LAT-P071, two of
        # the three get a different arm.
        #
        # NO WINDOW AT ALL takes the stamp arm regardless of interval, and that
        # is the case a dry-run against production caught. `warm_typeahead` has a
        # 10 s interval — nowhere near the 12 h blindness ceiling — but its starts
        # counter had expired, so `window_s` was `None` and the rate arm was mute.
        # Its last start stamp was 2 h 55 m old against a 10 s interval: **1,050x**,
        # screamingly missing, and the largest single publisher into the queue
        # this whole program is about. A count of unknown age is unusable; a
        # moment is not. Where a window is merely YOUNG the counter will age into
        # gradeability on its own, and that stays a transient rate-arm shrug.
        if out["rate_arm_blind"] or (exp is None and interval_s):
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

    # --- #3276: the rate arm being ABLE to speak does not make it the right
    # instrument, and until now "able" was the only test applied. -------------
    #
    # The two arms were written as ALTERNATIVES — the stamp is reached (L~397)
    # only when the rate arm is mute — so a task with a healthy-looking ratio
    # never had its stamp read at all, even though the caller passes it in and
    # it is live in this scope.
    #
    # THE SCOPE MISMATCH, which is this module's founding defect (#1790) one
    # field further left. A ratio is an average over `window_s`, and an average
    # cannot see a hole much shorter than its own window. Measured on production
    # 2026-09-05: `prewarm_live_feed_shapes` — the beat that keeps Discover and
    # Sports warm — had been dead for 3h43m on a 40s interval, and graded
    # `on_schedule` with an EMPTY REASON, because 3.7h of death inside a 21h
    # counter window only moved the ratio to 0.70, above BEHIND_RATIO. Its
    # `last_started_at` was 334x its interval old the whole time. Every visitor
    # ate a cold build for four hours and this surface said nothing.
    #
    # Worse, it might never have spoken: as the window saturates at the counter
    # TTL the ratio bottoms out at 1327/(86400/40) = 0.61 — still above 0.6. The
    # beat only becomes visible ~24h later, when the counters expire and L~397
    # finally hands it to the stamp arm. A detector whose first report of a dead
    # rail is a day late is not a detector.
    #
    # Lowering BEHIND_RATIO is NOT the fix and is explicitly rejected: it would
    # only shorten the blindness (never remove it — the bound above is 0.61) and
    # would re-redden the four `expires`-carrying beats of #2014.
    #
    # So: read the moment, not just the count. This module already argues the
    # point in `_grade_on_stamp`'s own comment — "A count of unknown age is
    # unusable; a moment is not" — and then only acts on it when the count is
    # missing. The tolerance, the negative-age guard and the `missing` verdict
    # are all REUSED from that arm rather than restated, so the two cannot
    # disagree about what "dead" means.
    #
    # CHECKED BEFORE `overruns` DELIBERATELY. `p95_over_interval` is computed
    # from a duration ring that describes the past; a beat that has recorded
    # nothing for many intervals is not lapping, it is absent, and returning
    # `overruns` first would mask the sharper fact. `arm` stays "rate" because
    # the rate arm is still what graded the fire count — the stamp is a veto on
    # its `on_schedule`, not a replacement for it.
    #
    # ONLY THE START STAMP MAY VETO HERE, and the distinction is load-bearing
    # rather than cautious. `_grade_on_stamp` takes the newest of {terminal,
    # start} because it runs when there is no counter at all, so any stamp is
    # the best evidence in the room. On THIS arm the counter has already given
    # positive evidence that fires happened, and the two stamps then answer
    # different questions:
    #
    #   * a stale START says the beat did not FIRE — which is exactly what
    #     adherence grades, and is decisive;
    #   * a stale TERMINAL says nothing FINISHED, which is compatible with a
    #     beat that is firing and hanging. That is #1716's open question, it
    #     already has its own flag (`never_completes`), and answering it here
    #     would decide it by accident — the thing this module refuses to do.
    #
    # Concretely: 2 starts counted in 3 days against a terminal stamp 10 days
    # old is a task that runs and never completes, NOT a missing beat, and
    # grading it `missing` off the terminal would be a false alarm. There is a
    # guard test on exactly that row.
    #
    # Gotcha #53 holds: no start stamp at all leaves the verdict alone. An
    # absent observation is not an observed absence, and a task nobody has ever
    # stamped must not be reported as one that stopped.
    start_stamp = _newest_stamp(None, newest_start_age_s)
    if start_stamp is not None and interval_s:
        age, kind = start_stamp
        # Reported unconditionally, fresh or stale. A reader comparing a count
        # against a moment needs both on the row; publishing the moment only
        # when it is damning is how a surface becomes an alarm instead of an
        # instrument.
        out["stamp_age_s"] = round(age, 1)
        out["stamp_kind"] = kind
        out["stamp_age_over_interval"] = round(age / interval_s, 2)

        # --- CERT-1932 repair: A START STAMP MEASURES THE GATE, NOT THE BEAT,
        # ON A TASK THAT SELF-GATES. ------------------------------------------
        #
        # The veto's claim is "nothing STARTED, therefore the beat did not
        # fire". That inference is only sound while starts track deliveries.
        # `record_task_started` is called from inside `_tracked_run`, which the
        # task BODY calls after its own gate has run, so on a self-gating task a
        # stale start stamp is the expected reading of a perfectly healthy beat:
        # the fire was delivered, the body declined, nothing stamped.
        #
        # The row that caught this is `poll_all_odds`, which drops to a 600s
        # adaptive cadence when no sport is live. Graded on the first
        # presentation of #3276 it returned `missing` on 20/20 deliveries, 19
        # self-gated fires, ratio 1.0 and a 301s start age — a false alarm on
        # the largest publisher into the queue, on the very surface this program
        # is making trustworthy. A detector whose first act is to cry wolf about
        # the healthiest beat on the board does not get read a second time.
        #
        # SELF-GATING IS STILL A FINDING, NOT AN EXCUSE, and the distinction is
        # the one this module's own docstring insists on (LAT-P159: "a large
        # `self_gated_fires` on `poll_all_odds` is a finding again, not a
        # footnote"). Nothing here suppresses that number — the fraction is
        # published on every row and the `self_gated_fires` sentence downstream
        # is untouched. What it withdraws is one specific inference: that a
        # self-gated fire is an ABSENT one. It fired.
        #
        # UNKNOWN FAILS THE VETO CLOSED-MOUTHED, NOT CLOSED. `None` means there
        # is no delivery counter to compare against, so the module cannot tell a
        # gate from a grave — and asserting the sharpest verdict it owns off
        # evidence it does not have is exactly the over-reach `unmeasurable`
        # exists to refuse (gotcha #53). The reason string says so out loud
        # rather than leaving a silently ungraded row.
        gate_fraction = _self_gate_fraction(
            deliveries, deliveries_window_s, starts, starts_window_s
        )
        out["self_gate_fraction"] = (
            round(gate_fraction, 3) if gate_fraction is not None else None
        )

        # WRITTEN TO ITS OWN FIELD, NOT TO `reason`. A withheld veto is not the
        # grade — the row still goes on to be graded `overruns` / `behind` /
        # `on_schedule` on its rate, and those branches own `reason` and would
        # overwrite anything left there. Recording it separately is what keeps
        # the #3276 failure mode legible: `on_schedule` with an EMPTY reason was
        # the original defect, and `on_schedule` beside a stamp 10x its interval
        # with no note saying why that was tolerated would be the same silence
        # wearing the fix's clothes.
        tolerance_s = _stamp_tolerance_s(interval_s)

        # --- CERT-1943 repair: A HISTORY IS NOT A HEARTBEAT. ------------------
        #
        # The clause above ends "the fires are arriving" — and on the evidence
        # it had, it could not know that. `gate_fraction` is a whole-window
        # statistic: 24h of counters divided by 24h of counters. It says fires
        # WERE arriving, averaged over a day. A mature self-gating task that
        # stopped dead five minutes ago has exactly the same fraction it had
        # while healthy, because 5 minutes moves a 24h average by nothing — so
        # the veto went on withholding and the task read `on_schedule`.
        #
        # This is the module's founding defect (#1790) for the third time, one
        # field further right, and it is worth naming as such: an average over
        # a long window cannot see a hole much shorter than the window. The
        # rate arm was blind to it, the stamp arm fixed that for STARTS, and
        # then the self-gate exemption re-opened it by keying the exemption on
        # another long-window average. The graded row that caught it:
        # `starts=2462, deliveries=2880` over equal 86400s windows, interval
        # 30s, newest start 301s old — ratio 1.0, fraction 0.145, veto
        # withheld, `on_schedule`, on a beat that had not fired in ten periods.
        #
        # So the exemption now needs a MOMENT, not just a history. The
        # self-gate story is "the fire was delivered and the body declined" —
        # that story has an observable consequence, which is a fresh DELIVERY
        # alongside the stale start. When deliveries have stopped too, nothing
        # is being declined, and there is no gate left to blame the silence on.
        # Delivery recency is judged on the same `_stamp_tolerance_s` as the
        # start stamp, deliberately reusing the helper rather than restating a
        # threshold, so the two moments cannot drift apart on what "stale" is.
        #
        # UNKNOWN STILL FAILS CLOSED-MOUTHED (gotcha #53). A `None` delivery
        # age is "no delivery has been stamped", which is NOT "no delivery has
        # arrived": delivery counters carry a 24h TTL and survive a dyno
        # restart, so for one interval after every deploy a perfectly healthy
        # self-gating beat has a live counter and no stamp yet. Reading that
        # gap as staleness would grade `poll_all_odds` `missing` after every
        # release — CERT-1932's false positive, bought straight back. The
        # withheld note names which of the two it is, so the row never claims
        # more than it measured.
        # NORMALISED TO ONE REPRESENTATION OF UNKNOWN, FIRST, and a guard test
        # exists because the first draft of this repair got it wrong. A stamp
        # in the FUTURE is ahead-drift (ruling 008 names two lane-lock
        # incidents caused by it), and the draft let a negative age fall past
        # the `delivery_fresh` test into the `missing` branch — so a
        # clock-skewed delivery stamp would have graded a healthy self-gating
        # beat dead, which is CERT-1932's false positive wearing a new stamp.
        # Unknown and stale are treated OPPOSITELY here, so they must never be
        # reachable through the same value: `_stamp_ages_s` collapses
        # ahead-drift to `None` at the caller and this collapses it again for
        # every other caller of a public function.
        if newest_delivery_age_s is not None and newest_delivery_age_s < 0:
            newest_delivery_age_s = None

        delivery_fresh = (
            newest_delivery_age_s is not None
            and newest_delivery_age_s <= tolerance_s
        )
        if newest_delivery_age_s is not None:
            out["delivery_age_s"] = round(newest_delivery_age_s, 1)

        if age > tolerance_s and gate_fraction is None:
            out["stamp_veto_withheld"] = (
                f"newest {kind} stamp is {out['stamp_age_over_interval']:.2f}x "
                f"its {interval_s:.0f}s interval, but this task has no delivery "
                "counter to compare against, so a self-gating body cannot be "
                "told from a dead beat — not graded `missing` on a stamp alone"
            )
        elif (
            age > tolerance_s
            and gate_fraction > SELF_GATE_MATERIAL_RATIO
            and newest_delivery_age_s is None
        ):
            out["stamp_veto_withheld"] = (
                f"newest {kind} stamp is {out['stamp_age_over_interval']:.2f}x "
                f"its {interval_s:.0f}s interval and {gate_fraction * 100:.0f}% "
                "of delivered fires self-gate, but no delivery has been stamped "
                "yet, so whether fires are STILL arriving is unknown — not "
                "graded `missing` on a whole-window average alone"
            )
        elif (
            age > tolerance_s
            and gate_fraction > SELF_GATE_MATERIAL_RATIO
            and delivery_fresh
        ):
            out["stamp_veto_withheld"] = (
                f"newest {kind} stamp is {out['stamp_age_over_interval']:.2f}x "
                f"its {interval_s:.0f}s interval, but {gate_fraction * 100:.0f}% "
                "of delivered fires self-gate and a delivery landed "
                f"{newest_delivery_age_s:.0f}s ago, so the stamp measures the "
                "gate and not the beat — the fires are arriving"
            )
        elif age > tolerance_s:
            out["verdict"] = "missing"
            out["reason"] = (
                f"nothing started for {age / 3600.0:.1f}h — newest {kind} stamp "
                f"is {out['stamp_age_over_interval']:.2f}x its {interval_s:.0f}s "
                f"interval, over a {tolerance_s:.0f}s tolerance. The fire count "
                f"still reads {ratio:.2f} because it averages over "
                f"{window_s / 3600.0:.1f}h and cannot see an outage this short"
            )
            # CERT-1943: on a task that DOES self-gate materially, the reader's
            # first objection to `missing` is the one the exemption above
            # exists to answer — "it self-gates, so of course nothing started".
            # The row has to pre-empt it with the fact that overrode it, or
            # this verdict looks like the false positive rather than the catch.
            if (
                gate_fraction is not None
                and gate_fraction > SELF_GATE_MATERIAL_RATIO
                and out["delivery_age_s"] is not None
            ):
                out["reason"] += (
                    f". {gate_fraction * 100:.0f}% of fires self-gate, which "
                    "would normally excuse a stale start stamp — but the last "
                    f"DELIVERY was also {out['delivery_age_s']:.0f}s ago, so "
                    "there is nothing arriving for the gate to decline"
                )
            return out

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
        # LAT-P238: WHICH END, and CERT-1969: DECIDED ON THE BUCKET.
        #
        # A `behind` row used to say only how far behind, and the two ways a
        # beat gets there need opposite fixes — a scheduler that is not
        # publishing versus a broker discarding what it published.
        #
        # 🔴 THE SENTENCE MAY NOT BE INHERITED FROM THIS VERDICT. `ratio` is a
        # 24h average and the bucket is 600 seconds; a beat behind over a day
        # and perfectly healthy right now is an ordinary state, and the first
        # repair printed "the shortfall is at the SCHEDULER" on exactly that
        # row. `bucket_attribution` answers from the bucket's OWN expectation,
        # so the row can say "not in this window" — which is a real answer, and
        # the one that stops this being an alarm.
        #
        # Appended, never substituted: the count-against-schedule sentence is
        # the verdict's evidence and stays first.
        if out["bucket_attribution"]:
            seen = (f". In the last complete {matched_bucket_s:.0f}s bucket "
                    f"{matched_emitted} fires were published against "
                    f"{matched_bucket_s / interval_s:.0f} scheduled, and "
                    f"{matched_delivered} were delivered")
            tail = {
                "broker_or_worker": (
                    f" — {undelivered * 100:.0f}% never reached a worker, so "
                    "the loss is between the broker and the worker, not at the "
                    "scheduler"
                ),
                "scheduler": (
                    " — the messages were never published, so the shortfall is "
                    "at the SCHEDULER"
                ),
                "both": (
                    " — short at BOTH ends: fewer published than scheduled, and "
                    "fewer delivered than published"
                ),
                "current_bucket_healthy": (
                    ", so this window is healthy and the shortfall above "
                    "predates it — this instrument cannot say which end lost it"
                ),
            }[out["bucket_attribution"]]
            out["reason"] += seen + tail
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


def beat_queues(beat_schedule, task_routes=None, default_queue="background"):
    """``task name -> [distinct worker queues its beat entries land on]``.

    LAT-P242 (#3466). The companion to :func:`beat_intervals` and it must get
    the same two shapes right, both of which have already misled readers:

    1. **The beat schedule is keyed by ENTRY name, not by task name.** An entry
       is ``{"task": "app.tasks.foo", "schedule": ..., "options": {...}}`` under
       an arbitrary key. Looking an entry up by task name silently finds
       nothing, and "nothing" here degrades to the default queue — which is
       ``background``, the very queue being sized, so the failure would have
       inflated the number it was built to measure.

    2. **One task can have several entries** (``collapse_snapshots`` has three)
       and they need not agree about the queue. So this returns a LIST, always,
       and never collapses it. A task whose entries disagree cannot have its
       wall time attributed to a queue at all — the counter is per task, not per
       entry — and the caller must report that rather than pick one.

    Precedence within an entry is celery's: ``options["queue"]`` OVERRIDES
    ``task_routes``. The routing block in ``app/tasks/__init__.py`` says so in
    the same words ("beat options override task_routes, so both must agree").
    Getting it backwards would credit the three multi-minute grinders that were
    deliberately pinned to ``heavy`` back to the queue they were moved off.
    """
    task_routes = task_routes or {}
    out: dict = {}
    for entry in (beat_schedule or {}).values():
        task = entry.get("task")
        if not task:
            continue
        options = entry.get("options") or {}
        queue = (
            options.get("queue")
            or (task_routes.get(task) or {}).get("queue")
            or default_queue
        )
        seen = out.setdefault(task, [])
        if queue not in seen:
            seen.append(queue)
    return {t: sorted(q) for t, q in out.items()}


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

    # #3276: WITHIN ``missing``, rank by how many of its own intervals the beat
    # has been silent — not by ``ratio``, which is meaningless for a beat that
    # is not running. Two dead beats sort by the number that says which one is
    # more dead; sorting them by a fire-count average would put a rail silent
    # for 348 intervals below one silent for 5, purely on the shape of their
    # counter windows. Before this arm existed every ``missing`` row came from a
    # beat too slow to have a usable ratio, so the question never arose; now the
    # rate arm produces them too and they all carry a ratio.
    #
    # Non-``missing`` rows contribute a constant here, so the existing relative
    # order — including the ratio tie-break below — is preserved exactly.
    def _key(item):
        _name, g = item
        deadness = (
            -(g.get("stamp_age_over_interval") or 0.0)
            if g["verdict"] == "missing"
            else 0.0
        )
        return (
            0 if g.get("never_completes") else 1,
            order.get(g["verdict"], 2),
            deadness,
            g["ratio"] if g["ratio"] is not None else 99,
        )

    return [
        {"task": name, **g}
        for name, g in sorted(graded.items(), key=_key)
        if g["verdict"] != "on_schedule" or g.get("never_completes")
    ]


# =============================================================================
# LAT-P243 (#3480) — CO-RESIDENCY OF LONG-HOLD BEATS ON A FIXED-SLOT POOL
#
# `beat_intervals` and `beat_queues` answer "how often" and "where". The
# question those two together still cannot answer, and the one that took the
# search box cold every morning, is **"can two of these be resident at the same
# time on a pool that only has two slots?"**
#
# The `background` worker is Standard-1X `--concurrency=2`. Six of its beats
# declare a soft_time_limit of half an hour or more, and five of them could be
# resident simultaneously — a scheduled outage during which every `warm-typeahead`
# fire expired unstarted (`expires: 120`) and the head of the search box went
# cold. Nothing detected it because adherence grades each task against its OWN
# cadence, and every one of those tasks was individually on schedule.
#
# Two properties this must get right, both of which have already misled a reader
# of this schedule:
#
# 1. **Enumerate, do not read the cron by eye.** `crontab(minute=30, hour="*/6")`
#    and `crontab(minute=45, hour="*/6")` look fifteen minutes apart and are, but
#    both tasks declare a 3600s hold, so "fifteen minutes apart" is the reason
#    they collide rather than the reason they do not. The fire times here come
#    from celery's OWN parsed field sets, which are already expanded from the
#    "*/6" string, so a mis-read of the cron syntax cannot enter.
#
# 2. **The window is the DECLARED soft_time_limit, never a sampled duration.**
#    The soft limit is the longest the system PERMITS the task to hold the slot.
#    A bound taken from a measured maximum has been refuted twice in this
#    program by the next sample; a declared limit cannot be, because exceeding
#    it is what the limit prevents.
# =============================================================================

#: A background beat that can hold one of two slots for this long or more is a
#: "long hold": the pool has effectively lost half its capacity for the
#: duration, so two of them overlapping is a total outage rather than a slowdown.
#: 1200s sits in a wide gap in the actual distribution — the long holds declare
#: 1700/1800/3600 and the next beat below declares 900 — so it separates the two
#: populations with margin on both sides rather than cutting through a cluster.
LONG_HOLD_SOFT_LIMIT_S = 1200


def crontab_fire_times(schedule, start, days=7):
    """Every UTC fire instant of one beat ``schedule`` in ``[start, start+days)``.

    Handles the two shapes a long-hold beat can carry: a ``crontab`` (read from
    its OWN parsed field sets, so ``"*/6"`` is already expanded and cannot be
    mis-read here) and a plain interval in seconds or a ``timedelta``.

    Returns ``None`` — not an empty list — for a schedule shape it cannot
    enumerate. An unenumerable schedule is a gap in the check and the caller
    must report it; silently returning "no fires" would render such a beat
    permanently non-overlapping, which is the one answer that is certainly
    wrong.
    """
    from datetime import timedelta

    if isinstance(schedule, bool) or schedule is None:
        return None
    if isinstance(schedule, (int, float)):
        if schedule <= 0:
            return None
        step = timedelta(seconds=float(schedule))
        out, t, end = [], start, start + timedelta(days=days)
        while t < end:
            out.append(t)
            t += step
        return out
    total = getattr(schedule, "total_seconds", None)
    if callable(total):  # timedelta
        secs = total()
        return crontab_fire_times(float(secs), start, days) if secs > 0 else None

    try:
        minutes = sorted(schedule.minute)
        hours = sorted(schedule.hour)
        dows = set(schedule.day_of_week)
        doms = set(schedule.day_of_month)
        moys = set(schedule.month_of_year)
    except (AttributeError, TypeError):
        return None
    if not (minutes and hours and dows and doms and moys):
        return None

    out = []
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    for offset in range(days + 1):
        d = day + timedelta(days=offset)
        # celery's day_of_week is 0=Sunday; python's weekday() is 0=Monday.
        if ((d.weekday() + 1) % 7) not in dows:
            continue
        if d.day not in doms or d.month not in moys:
            continue
        for h in hours:
            for m in minutes:
                t = d + timedelta(hours=h, minutes=m)
                if start <= t < start + timedelta(days=days):
                    out.append(t)
    return sorted(out)


def long_hold_beats(beat_schedule, soft_limits, queues, *, queue="background",
                    long_hold_s=LONG_HOLD_SOFT_LIMIT_S):
    """Beat ENTRY names on ``queue`` whose task declares a long hold.

    ``soft_limits`` and ``queues`` are plain ``task name -> value`` maps so this
    stays importable without celery and testable without the app. ``queues``
    is :func:`beat_queues`' output, i.e. a LIST per task, and a task whose
    entries disagree about the queue is included if ANY of them lands on
    ``queue`` — the pessimistic reading, because one entry on the pool is enough
    to hold one of its slots.
    """
    out = []
    for name, entry in (beat_schedule or {}).items():
        task = entry.get("task")
        if not task:
            continue
        if (soft_limits.get(task) or 0) < long_hold_s:
            continue
        if queue not in (queues.get(task) or []):
            continue
        out.append(name)
    return sorted(out)


def residency_overlaps(beat_schedule, soft_limits, queues, *, start, days=7,
                       queue="background", long_hold_s=LONG_HOLD_SOFT_LIMIT_S):
    """Every pair of long-hold ``queue`` beats whose declared windows overlap.

    A "window" is ``[fire, fire + soft_time_limit]``: the span for which that
    fire may hold one slot. Two overlapping windows mean both slots of a
    two-slot pool can be held by grinders at once, with nothing else able to
    run — which is what the user feels, not as a slow page but as a cold one.

    Returns ``(overlaps, unenumerable)``. ``unenumerable`` carries the entries
    whose schedule shape :func:`crontab_fire_times` could not read, so a gap in
    the check is reported rather than passing as a clean result.
    """
    from datetime import timedelta

    names = long_hold_beats(beat_schedule, soft_limits, queues,
                            queue=queue, long_hold_s=long_hold_s)
    windows, unenumerable = [], []
    for name in names:
        entry = beat_schedule[name]
        fires = crontab_fire_times(entry.get("schedule"), start, days)
        if fires is None:
            unenumerable.append(name)
            continue
        hold = timedelta(seconds=float(soft_limits[entry["task"]]))
        for f in fires:
            windows.append((f, f + hold, name))
    windows.sort()

    overlaps = []
    for i, (s_a, e_a, n_a) in enumerate(windows):
        for (s_b, e_b, n_b) in windows[i + 1:]:
            if s_b >= e_a:
                break  # sorted by start: nothing later can overlap this window
            overlaps.append({
                "a": n_a, "a_fire": s_a.isoformat(), "a_until": e_a.isoformat(),
                "b": n_b, "b_fire": s_b.isoformat(), "b_until": e_b.isoformat(),
                "overlap_s": (min(e_a, e_b) - s_b).total_seconds(),
            })
    return overlaps, unenumerable


# =============================================================================
# LAT-P243 REPAIR (#3480, answering CERT-2045's BLOCK)
#
# `residency_overlaps` asks "can two grinders hold both slots?". CERT-2045 found
# the case it cannot see, and the finding is correct: the first staggered
# schedule put `collapse-winprob-snapshots-daily` (declared 1700s) at 05:15Z
# EXACTLY with `backfill-kalshi-trade-history` (600s) and `poll-polymarket-hourly`
# (540s). Three arrivals, two slots. Two of them hold both slots for 9-10
# minutes, `warm-typeahead`'s message expires at 120s behind them, and the search
# box goes cold by the very mechanism the ship claimed to remove. The pair test
# missed it because it required BOTH sides to exceed 1200s, and 600 and 540 do
# not.
#
# So the invariant is re-derived from the quantity the user actually feels: the
# warmer's own MESSAGE EXPIRY BUDGET. A fire that cannot reach a slot inside that
# budget is not delayed, it is destroyed.
#
# 🔴 THE LITERAL INVARIANT IS NOT SCHEDULABLE, AND SAYING SO IS PART OF THE
# ANSWER. "A slot opportunity within the budget throughout every compaction
# window" cannot be met by moving beats. Measured on this schedule: **59
# background beat entries declare a hold longer than the budget and fire 1,222
# times a day**; by declared windows the median minute of the day has FIVE of
# them resident on a two-slot pool, and only 7 minutes in 1,440 have none. No
# 28-minute window exists anywhere on the clock that satisfies it. Only isolation
# — a queue and a worker the warmer does not share — can, and that is a dyno
# purchase and Alex's call.
#
# What IS schedulable, and what this therefore enforces, is the arrival pattern
# that produced the reproduction: **SIMULTANEOUS arrival.** A compaction beat
# that fires alongside other long-holding work hands both slots away at once and
# puts the warmer behind them; a compaction beat that fires with the budget clear
# on either side leaves the second slot turning over. 335 of 1,440 minutes are
# clear on every day of the week, so this is satisfiable with room.
#
# The residual — a competitor arriving mid-window — is real, is NOT fixed here,
# and is named in the ship's disclosure rather than left for the next grader.
# =============================================================================


def warmer_expiry_budget_s(beat_schedule, warmer_beat="warm-typeahead"):
    """The warmer's own message-expiry bound, READ from the live schedule.

    Never a typed constant. `_EXPIRING_WARMER_BEATS` derives this value (it is
    `_LOCK_TTL_SECONDS`, deliberately a constant rather than a sampled wall) and
    applies it to the beat's `options` at import time. Reading it back here means
    the isolation rule and the expiry it protects can never disagree — change one
    and the other follows.

    Raises rather than defaulting: a missing bound would silently make the
    isolation check vacuous, and a vacuous check on this property is exactly what
    CERT-2045 caught.
    """
    entry = (beat_schedule or {}).get(warmer_beat)
    if not entry:
        raise KeyError(
            f"{warmer_beat!r} is not in the beat schedule, so its expiry budget "
            "cannot be read. If the warmer was renamed, this check must be "
            "re-pointed, not skipped."
        )
    expires = (entry.get("options") or {}).get("expires")
    if not expires or expires <= 0:
        raise ValueError(
            f"{warmer_beat!r} declares no positive `expires`, so there is no "
            "budget to derive an isolation rule from."
        )
    return float(expires)


def fire_isolation_violations(beat_schedule, soft_limits, queues, subjects, *,
                              start, days=7, queue="background",
                              warmer_beat="warm-typeahead"):
    """Subject fires that share their arrival instant with other long-holding work.

    ``subjects`` are the beat ENTRY names being placed (here, the compaction
    beats). A violation is any OTHER beat on ``queue`` whose declared hold
    exceeds the warmer's expiry budget and which fires within that same budget of
    a subject fire — before or after, because either ordering can take the second
    slot first.

    The comparison population is "declared hold > budget", NOT "declared hold >
    some round number". A 540s task and a 1700s task exhaust two slots exactly as
    thoroughly as two 3600s tasks do; the only thing that matters is whether the
    second slot comes back inside the budget, and neither of them does.

    Returns ``(violations, unenumerable)`` with the same contract as
    :func:`residency_overlaps`: a schedule shape that cannot be enumerated is
    REPORTED, never silently treated as non-colliding.
    """
    from datetime import timedelta

    budget = warmer_expiry_budget_s(beat_schedule, warmer_beat)
    unenumerable, competitors = [], []
    for name, entry in (beat_schedule or {}).items():
        task = entry.get("task")
        if not task or name in subjects or name == warmer_beat:
            continue
        if queue not in (queues.get(task) or []):
            continue
        if (soft_limits.get(task) or 0) <= budget:
            continue
        fires = crontab_fire_times(entry.get("schedule"), start, days)
        if fires is None:
            unenumerable.append(name)
            continue
        for f in fires:
            competitors.append((f, name, soft_limits[task]))
    competitors.sort()

    violations = []
    for name in sorted(subjects):
        entry = (beat_schedule or {}).get(name)
        if entry is None:
            continue
        fires = crontab_fire_times(entry.get("schedule"), start, days)
        if fires is None:
            unenumerable.append(name)
            continue
        for f in fires:
            lo, hi = f - timedelta(seconds=budget), f + timedelta(seconds=budget)
            for (cf, cname, chold) in competitors:
                if cf <= lo:
                    continue
                if cf >= hi:
                    break
                violations.append({
                    "subject": name,
                    "subject_fire": f.isoformat(),
                    "competitor": cname,
                    "competitor_fire": cf.isoformat(),
                    "competitor_declared_hold_s": chold,
                    "separation_s": abs((cf - f).total_seconds()),
                    "budget_s": budget,
                })
    return violations, unenumerable


def effective_hold_s(soft_limit, global_hard_limit):
    """The longest a task may hold its slot, from what is DECLARED about it.

    🔴 ``soft_time_limit`` UNSET DOES NOT MEAN ZERO, AND IT DOES NOT MEAN
    UNBOUNDED EITHER. Nine of ``realtime``'s ten beats declare no soft limit, and
    reading that as ``0`` scores the busiest lane in the fleet as the emptiest —
    the arithmetic error that would send the warmer to the one queue measured
    (#3060) to have zero standing headroom. What actually bounds those tasks is
    celery's GLOBAL ``task_time_limit`` (300s here), a hard SIGKILL, so their
    declared hold is 300s and not 0.

    Returns ``None`` only when neither bound exists — genuinely unbounded, which
    is worse than any finite hold and is reported as such rather than defaulted.
    """
    soft = soft_limit or 0
    if soft > 0:
        return float(soft)
    hard = global_hard_limit or 0
    return float(hard) if hard > 0 else None


def unbudgeted_residents(beat_schedule, soft_limits, queues, *, queue,
                         budget_s, global_hard_limit=None,
                         warmer_beat="warm-typeahead"):
    """Beats on ``queue`` that cannot be shown to release a slot inside ``budget_s``.

    Two kinds, and they are reported apart because they argue differently:

    *   ``over_budget`` — a declared hold (soft, else the global hard limit)
        longer than the budget. It may legitimately keep the slot past the point
        the warmer's message expires.
    *   ``unbounded`` — no bound of either kind. Strictly worse, and never folded
        into the first list, because "300s > 120s" and "no answer at all" are
        different findings and a reader is entitled to tell them apart.

    Returns ``(over_budget, unbounded)``, both sorted entry-name lists. The
    warmer itself is excluded — it does not compete with itself for the slot it
    is waiting for.
    """
    over_budget, unbounded = [], []
    for name, entry in (beat_schedule or {}).items():
        task = entry.get("task")
        if not task or name == warmer_beat:
            continue
        if queue not in (queues.get(task) or []):
            continue
        hold = effective_hold_s(soft_limits.get(task), global_hard_limit)
        if hold is None:
            unbounded.append(name)
        elif hold > budget_s:
            over_budget.append(name)
    return sorted(over_budget), sorted(unbounded)


def queues_that_cannot_guarantee_a_slot(beat_schedule, soft_limits, queues, *,
                                        budget_s, slots=None,
                                        global_hard_limit=None,
                                        warmer_beat="warm-typeahead"):
    """Which existing worker queues fail to guarantee a slot inside ``budget_s``.

    🔴 READ THE DIRECTION OF THIS CHECK BEFORE USING ITS ANSWER. It is a
    DISQUALIFIER, not a failure detector. A queue is disqualified when it has at
    least as many residents that cannot be shown to release inside the budget as
    it has slots — i.e. when nothing in the declared schedule rules out every
    slot being held past the budget. That is the condition for *"this queue
    cannot be PROVEN to satisfy the invariant"*, which is the claim the
    dedicated-worker ask rests on. It is deliberately NOT a claim that the queue
    *does* starve the warmer: proving that needs measured occupancy, and this
    module only ever reads declarations.

    Why the weaker claim is the right one to automate: the strong one is
    unfalsifiable from a schedule, and the decision it feeds — "is there anywhere
    to put the warmer that we already pay for?" — is answered by the weak one. A
    queue that survives this check has EARNED a measurement, not a move.

    Returns ``{queue: {"slots": n, "over_budget": [...], "unbounded": [...]}}``
    for the disqualified queues only, so an empty return is the good-news case
    and says an existing lane may now be worth measuring as a home.
    """
    slots = QUEUE_SLOTS if slots is None else slots
    out = {}
    for queue, n_slots in slots.items():
        over, unbounded = unbudgeted_residents(
            beat_schedule, soft_limits, queues,
            queue=queue, budget_s=budget_s,
            global_hard_limit=global_hard_limit, warmer_beat=warmer_beat,
        )
        if len(over) + len(unbounded) >= n_slots:
            out[queue] = {"slots": n_slots, "over_budget": over, "unbounded": unbounded}
    return out
